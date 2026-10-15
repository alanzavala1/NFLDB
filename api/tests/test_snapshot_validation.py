"""Real analytics plus read-only HTTP validation, and deliberately corrupted data."""
import asyncio
import hashlib
from pathlib import Path
import subprocess
import sys

import duckdb
import pytest

from pipeline.reconciliation import (
    count_mismatches, passing_epa_mismatches, impossible_rates, defensive_sack_mismatches,
)
from pipeline.validation import SnapshotValidationError, validate_snapshot


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    import database
    from tests.conftest import _create_schema, _seed
    from tests.test_weekly_columns import _feed_frame
    from pipeline.player_stats import build_player_game_stats
    from pipeline.analytics import prepare_analytics
    from pipeline.awards import load_player_awards

    path = tmp_path / 'prepared.duckdb'
    conn = duckdb.connect(str(path))
    monkeypatch.setattr(database, '_conn', conn)
    _create_schema(conn)
    _seed(conn)
    # The shared mini-league omits situational fields. Supply the actual split
    # inputs here so a successful test cannot rely on builders swallowing gaps.
    import def_splits_builder
    extra = {slot[0]: ('VARCHAR', 'NULL') for slot in def_splits_builder._SLOTS}
    extra.update({
        'down': ('INTEGER', '1'), 'score_differential': ('DOUBLE', '0'),
        'shotgun': ('INTEGER', '0'), 'first_down': ('INTEGER', '0'),
        'posteam_type': ('VARCHAR', "'home'"), 'roof': ('VARCHAR', "'outdoors'"),
        'surface': ('VARCHAR', "'grass'"), 'no_huddle': ('INTEGER', '0'),
        'wp': ('DOUBLE', '0.5'), 'qb_hit': ('INTEGER', '0'),
        'incomplete_pass': ('INTEGER', '0'), 'pass_touchdown': ('INTEGER', '0'),
        'rush_touchdown': ('INTEGER', '0'), 'cpoe': ('DOUBLE', '0'),
        'yards_after_catch': ('DOUBLE', '0'), 'pass_length': ('VARCHAR', "'short'"),
    })
    existing = {r[0] for r in conn.execute('DESCRIBE plays').fetchall()}
    for col, (kind, default) in extra.items():
        if col not in existing:
            conn.execute(f'ALTER TABLE plays ADD COLUMN {col} {kind} DEFAULT {default}')
    # A tiny early-season official feed: volumes are below split admission.
    weekly = _feed_frame(2024).assign(player_id='00-KC-QB1', player_name='Patrick Mahomes',
        game_id='2024_01_DEN_KC', attempts=12, completions=12, passing_yards=60, passing_epa=12)
    conn.register('weekly', weekly)
    conn.execute('CREATE TABLE weekly_player_stats AS SELECT * FROM weekly')
    build_player_game_stats(conn, conn.execute('SELECT * FROM plays').df(), [2024])
    prepare_analytics([2024], log=lambda message: None)
    load_player_awards(conn, log=lambda message: None)
    yield conn, path
    conn.close()


def test_prepared_small_season_allows_legitimate_empty_splits_and_comparables(prepared):
    conn, _ = prepared
    report = validate_snapshot(conn)
    assert report['played_seasons'] == [2024]
    assert report['coverage']['player_splits'].get(2024, 0) == 0
    assert 'career comparables below volume/pool thresholds' in report['allowed_empty']


@pytest.mark.parametrize('sql,error', [
    ('DROP TABLE team_power_rankings', 'missing prepared table'),
    ('ALTER TABLE player_game_ratings DROP COLUMN rating', 'expected DOUBLE'),
    ('DELETE FROM team_splits', 'team_splits\\[2024\\]'),
    ('DELETE FROM weekly_player_stats', 'weekly_player_stats\\[2024\\]'),
    ('DELETE FROM player_awards', 'no prepared rows'),
    ('DROP INDEX idx_player_game_stats_player_id', 'missing lookup index'),
    ('UPDATE player_game_ratings SET rating = 999', 'invalid rating'),
    ('''CREATE OR REPLACE TABLE team_power_rankings AS SELECT * FROM team_power_rankings
        UNION ALL SELECT * FROM team_power_rankings''', 'duplicate lookup keys'),
    ('''CREATE OR REPLACE TABLE team_power_rankings AS
        SELECT * REPLACE (NULL::VARCHAR AS team) FROM team_power_rankings''', 'null lookup key'),
])
def test_schema_coverage_indexes_and_rating_faults_fail(prepared, sql, error):
    conn, _ = prepared
    conn.execute(sql)
    with pytest.raises(SnapshotValidationError, match=error):
        validate_snapshot(conn)


@pytest.mark.parametrize('other_player_present', [False, True])
def test_qualifying_players_cannot_disappear_from_split_category(prepared, other_player_present):
    conn, _ = prepared
    conn.execute("""INSERT INTO plays BY NAME SELECT p.* FROM plays p CROSS JOIN range(5)
                    WHERE passer_player_id = '00-KC-QB1'""")
    if other_player_present:
        conn.execute("""INSERT INTO player_splits (player_id, season, category, split_dim, split_value)
                        VALUES ('somebody-else', 2024, 'passing', 'down', '1')""")
    with pytest.raises(SnapshotValidationError, match='qualifying players missing'):
        validate_snapshot(conn)


def test_historical_gap_fails_even_when_newest_season_is_prepared(prepared):
    conn, _ = prepared
    conn.execute('INSERT INTO plays BY NAME SELECT * REPLACE (2023 AS season) FROM plays LIMIT 1')
    with pytest.raises(SnapshotValidationError, match=r'schedules\[2023\]'):
        validate_snapshot(conn)


def test_two_point_attempt_does_not_make_low_volume_runner_eligible(prepared):
    conn, _ = prepared
    for count, two_point in ((24, 0), (1, 1)):
        conn.execute(f'''INSERT INTO plays BY NAME SELECT p.* REPLACE (
            'trick-runner' AS rusher_player_id, NULL::VARCHAR AS passer_player_id,
            NULL::VARCHAR AS receiver_player_id, 0 AS complete_pass, 0 AS incomplete_pass,
            0 AS interception,
            1 AS rush_attempt, 0 AS pass_attempt, {two_point} AS two_point_attempt)
            FROM (SELECT * FROM plays LIMIT 1) p CROSS JOIN range({count})''')
    assert validate_snapshot(conn)['played_seasons'] == [2024]


def test_real_validation_command_reads_only_and_checks_http_responses(prepared):
    conn, path = prepared
    # Include a historical and newest season, using the actual builders for
    # both seasonal tables and the global rating calibration.
    for table in ('plays', 'schedules', 'weekly_player_stats', 'player_game_stats', 'rosters'):
        replacements = "2023 AS season"
        if table != 'rosters':
            replacements += ", REPLACE(game_id, '2024_', '2023_') AS game_id"
        conn.execute(f'INSERT INTO {table} BY NAME SELECT * REPLACE ({replacements}) FROM {table}')
    from pipeline.analytics import prepare_analytics
    prepare_analytics([2023, 2024], log=lambda message: None)
    conn.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = subprocess.run([sys.executable, '-m', 'jobs.validate', '--database', str(path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '/api/leaders?season=2024' in result.stdout
    assert '/api/leaders?season=2023' in result.stdout
    assert '/api/games/2024_01_BUF_MIA/ratings' in result.stdout
    assert '/api/games/2023_01_BUF_MIA/ratings' in result.stdout
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not Path(f'{path}.wal').exists()


def test_api_check_fails_when_request_tries_to_rebuild(prepared, monkeypatch):
    import database
    from pipeline.api_checks import check_api
    conn, path = prepared
    conn.execute('DELETE FROM team_power_rankings')
    conn.close()
    readonly = duckdb.connect(str(path), read_only=True)
    monkeypatch.setattr(database, '_conn', readonly)
    try:
        with pytest.raises(Exception, match='read-only'):
            asyncio.run(check_api(readonly, [2024]))
    finally:
        readonly.close()


def test_validation_command_rejects_invalid_api_response_without_repair(prepared):
    conn, path = prepared
    conn.execute('UPDATE player_game_stats SET player_name = NULL')
    conn.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = subprocess.run([sys.executable, '-m', 'jobs.validate', '--database', str(path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'ResponseValidationError' in result.stderr and 'player_name' in result.stderr
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_missing_defender_is_detected_only_after_event_admission(prepared):
    conn, _ = prepared
    conn.execute("UPDATE plays SET solo_tackle_1_player_id = 'defender' WHERE play_id <= 20")
    conn.execute("UPDATE plays SET sack_player_id = 'defender' WHERE play_id <= 6")
    assert defensive_sack_mismatches(conn, 2024) == 1
    conn.execute("""INSERT INTO defense_splits (player_id, season, split_dim, split_value, sacks)
                    VALUES ('defender', 2024, 'down', '1', 6)""")
    assert defensive_sack_mismatches(conn, 2024) == 0
    conn.execute('DELETE FROM defense_splits')
    conn.execute('UPDATE plays SET solo_tackle_1_player_id = NULL')
    assert defensive_sack_mismatches(conn, 2024) == 0  # six events, below the admission threshold


@pytest.fixture
def reconciled():
    conn = duckdb.connect(':memory:')
    conn.execute('''CREATE TABLE weekly_player_stats (
        season INTEGER, season_type VARCHAR, player_id VARCHAR, attempts INTEGER, passing_epa DOUBLE)''')
    conn.execute('''CREATE TABLE player_splits (
        season INTEGER, player_id VARCHAR, category VARCHAR, split_dim VARCHAR,
        att INTEGER, epa DOUBLE, yards INTEGER, success_pct DOUBLE)''')
    conn.execute('''CREATE TABLE plays (season INTEGER, season_type VARCHAR, down INTEGER,
        pass_attempt INTEGER, sack INTEGER, passer_player_id VARCHAR, qb_epa DOUBLE)''')
    conn.execute("INSERT INTO weekly_player_stats VALUES (2024, 'REG', 'qb', 100, 20)")
    conn.execute("INSERT INTO player_splits VALUES (2024, 'qb', 'passing', 'down', 100, 0.2, 500, 50)")
    yield conn
    conn.close()


def test_reconciliation_detects_corrupt_counts_and_entirely_missing_players(reconciled):
    conn = reconciled
    assert count_mismatches(conn, 2024, 'passing', 'att', 'attempts', 100) == 0
    conn.execute('UPDATE player_splits SET att = 99')
    assert count_mismatches(conn, 2024, 'passing', 'att', 'attempts', 100) == 1
    conn.execute('DELETE FROM player_splits')
    assert count_mismatches(conn, 2024, 'passing', 'att', 'attempts', 100) == 1
    assert passing_epa_mismatches(conn, 2024) == 1


def test_passing_epa_new_feed_adjustment_and_failure(reconciled):
    conn = reconciled
    conn.execute('ALTER TABLE weekly_player_stats ADD COLUMN sacks_suffered DOUBLE')
    conn.execute("INSERT INTO plays VALUES (2024, 'REG', NULL, 1, 0, 'qb', 2)")
    conn.execute('UPDATE weekly_player_stats SET passing_epa = 22')
    assert passing_epa_mismatches(conn, 2024) == 0
    conn.execute('UPDATE weekly_player_stats SET passing_epa = 23')
    assert passing_epa_mismatches(conn, 2024) == 1


@pytest.mark.parametrize('value', ["'NaN'::DOUBLE", '101', '-1'])
def test_impossible_success_percentages_fail(reconciled, value):
    reconciled.execute(f'UPDATE player_splits SET success_pct = {value}')
    assert impossible_rates(reconciled) == 1
