"""Canonical receiving replacement, source coherence and coverage persistence."""
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

import splits_builder
from pipeline import receiving_preview
from pipeline.receiving_build import PREPARATION_TABLE, REFERENCE_TABLE, TOTALS_TABLE
from pipeline.receiving_exports import load_receiving_season
from pipeline.source_results import SeasonalFeed, SourceError
from pipeline.validation import SnapshotValidationError, validate_snapshot
from tests.test_receiving_preview import fake_export


class CapturedInputs:
    """Deterministic transport; real typed-bundle guards have separate controls."""
    def __init__(self, directory, plays, weekly):
        self.directory, self.plays, self.weekly = directory, plays, weekly
        self.manifest = json.loads((directory / 'run.json').read_text())
        self.manifest_sha = receiving_preview.file_sha256(directory / 'run.json')

    def load_feeds(self, play_seasons, weekly_seasons):
        return (SeasonalFeed(self.plays.copy(), play_seasons, []),
                SeasonalFeed(self.weekly.copy(), weekly_seasons, []))

    def receiving_run(self, season):
        return self.directory, self.manifest, self.manifest_sha

    def revision(self):
        return 'deterministic captured-input control'


@pytest.fixture
def build_case(tmp_path, fake_export, monkeypatch):
    connections = []
    def make(year=2024, fault=None):
        output = tmp_path / f'exports-{len(connections)}'
        output.mkdir()
        if fault:
            monkeypatch.setenv('PREVIEW_TEST_FAULT', fault)
        else:
            monkeypatch.delenv('PREVIEW_TEST_FAULT', raising=False)
        receiving_preview._run_export(Path('unused'), tmp_path, output, [year], 'build-control')
        plays = pd.read_csv(output / f'context-{year}.csv').assign(
            week=1, first_down=1, pass_attempt=1, passer_player_id='quarterback', sack=0,
            play_type='pass', passing_yards=10, qb_epa=.5, cpoe=0., yards_after_catch=7,
            receiving_yards=10, pass_touchdown=0, success=1, rush_attempt=1,
            rusher_player_id='runner', run_gap='guard', run_location='left', rushing_yards=3,
            rush_touchdown=0)
        weekly = pd.read_csv(output / f'weekly-{year}.csv')
        conn = duckdb.connect(':memory:')
        connections.append(conn)
        conn.register('input_plays', plays)
        conn.execute('CREATE TABLE plays AS SELECT * FROM input_plays')
        conn.register('input_weekly', weekly)
        conn.execute('CREATE TABLE weekly_player_stats AS SELECT * FROM input_weekly')
        conn.execute('''CREATE TABLE schedules (season INTEGER,game_id VARCHAR,game_type VARCHAR,
                                               home_score INTEGER,away_score INTEGER)''')
        conn.execute("INSERT INTO schedules VALUES (?,'game','REG',20,10)", [year])
        splits_builder.ensure_table(conn)
        conn.execute("""INSERT INTO player_splits(player_id,season,category,split_dim,split_value,att,cmp,yards,td)
                         VALUES ('old',?,'receiving','down','1',1,1,999,1),
                                ('older',1998,'receiving','down','1',1,1,12,0)""", [year])
        monkeypatch.setattr(splits_builder, 'get_connection', lambda: conn)
        return conn, CapturedInputs(output, plays, weekly)
    yield make
    for conn in connections:
        conn.close()


def snapshot(conn):
    return conn.execute('SELECT * FROM player_splits ORDER BY ALL').fetchall()


@pytest.mark.parametrize('year', [2004, 2024])
def test_official_rows_replace_old_receiving_preserve_other_year_and_metric_masks(build_case, year):
    conn, inputs = build_case(year)
    splits_builder.materialize(year, receiving_inputs=inputs)
    assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td) FROM player_splits WHERE season=? AND category='receiving' AND split_dim='down'", [year]).fetchone() == (None if year==2004 else 28, 28, 280, 0)
    assert conn.execute("SELECT yards FROM player_splits WHERE player_id='older'").fetchone()[0] == 12
    assert conn.execute("SELECT COUNT(*) FROM player_splits WHERE player_id='old'").fetchone()[0] == 0
    report = json.loads(conn.execute(f'SELECT record FROM {PREPARATION_TABLE}').fetchone()[0])
    assert report['status'] == 'offline_integration_only' and not report['publication_ready']
    assert report['game_coverage']['status'] == 'complete'
    assert len(report['dimensions']) == 17 and report['qualification']['qualifying_plays'] == {'receiver':28}
    reference = json.loads(conn.execute(f'SELECT record FROM {REFERENCE_TABLE}').fetchone()[0])
    assert reference['rows'][0]['receptions'] == 28 and not reference['serving_ready']
    if year==2004:
        assert conn.execute("SELECT COUNT(*) FROM player_splits WHERE season=? AND category='receiving' AND (att IS NOT NULL OR yac IS NOT NULL OR air_yards IS NOT NULL OR epa IS NOT NULL)", [year]).fetchone()[0] == 0
    with pytest.raises(SnapshotValidationError, match='coverage-aware API/UI'):
        validate_snapshot(conn)


def test_passing_rushing_sql_unchanged_and_old_receiving_sql_bypassed(build_case, monkeypatch):
    conn, inputs = build_case()
    splits_builder.materialize(2024)
    expected = conn.execute("SELECT * FROM player_splits WHERE category IN ('passing','rushing') ORDER BY ALL").fetchall()
    assert any(row[2]=='rushing' for row in expected)
    original, calls = splits_builder._category_sql, []
    def category_sql(category, *args):
        calls.append(category)
        assert category != 'receiving', 'legacy receiving calculation must not run'
        return original(category, *args)
    monkeypatch.setattr(splits_builder, '_category_sql', category_sql)
    splits_builder.materialize(2024, receiving_inputs=inputs)
    actual = conn.execute("SELECT * FROM player_splits WHERE category IN ('passing','rushing') ORDER BY ALL").fetchall()
    assert actual == expected and calls == ['passing','rushing']


@pytest.mark.parametrize('fault', ['partial_context','unavailable_context','charting_gap','rush_outlier'])
def test_context_gaps_preserve_other_views_and_record_excluded_production(build_case, fault):
    conn, inputs = build_case(fault=fault)
    splits_builder.materialize(2024, receiving_inputs=inputs)
    report = json.loads(conn.execute(f'SELECT record FROM {PREPARATION_TABLE}').fetchone()[0])
    dimension = 'field_zone' if 'context' in fault else 'play_action' if fault=='charting_gap' else 'blitz'
    coverage = report['dimensions'][dimension]['coverage']
    assert coverage['status'] in ('partial','unavailable')
    assert coverage['qualified_production']['excluded']['receptions'] > 0
    assert conn.execute("SELECT SUM(cmp),SUM(yards) FROM player_splits WHERE season=2024 AND category='receiving' AND split_dim='down'").fetchone() == (28,280)


def test_game_gaps_and_unconfirmed_final_scores_are_explicit(build_case):
    conn, inputs = build_case()
    conn.execute("INSERT INTO schedules VALUES (2024,'missing','REG',21,10)")
    conn.execute("UPDATE schedules SET home_score=NULL WHERE game_id='game'")
    splits_builder.materialize(2024, receiving_inputs=inputs)
    coverage = json.loads(conn.execute(f'SELECT record FROM {PREPARATION_TABLE}').fetchone()[0])['game_coverage']
    assert coverage['missing_game_ids'] == ['missing'] and coverage['unconfirmed_game_ids'] == ['game']
    assert coverage['status'] == 'partial'


@pytest.mark.parametrize('change', ['plays','weekly','export'])
def test_mismatched_or_corrupt_inputs_cannot_replace_existing_rows(build_case, change):
    conn, inputs = build_case()
    before = snapshot(conn)
    if change=='plays':
        conn.execute('UPDATE plays SET epa=123 WHERE play_id=0')
    elif change=='weekly':
        conn.execute('UPDATE weekly_player_stats SET receptions=123')
    else:
        with (inputs.directory / 'field_zone-2024.csv').open('ab') as stream:
            stream.write(b'\n')
    with pytest.raises((SourceError, RuntimeError)):
        splits_builder.materialize(2024, receiving_inputs=inputs)
    assert snapshot(conn) == before
    assert PREPARATION_TABLE not in {row[0] for row in conn.execute('SHOW TABLES').fetchall()}


@pytest.mark.parametrize('already_official', [False, True])
def test_failure_after_row_and_metadata_writes_rolls_back_everything(build_case, monkeypatch, already_official):
    from pipeline import receiving_build
    conn, inputs = build_case()
    if already_official:
        splits_builder.materialize(2024, receiving_inputs=inputs)
    before = snapshot(conn)
    metadata = {table: conn.execute(f'SELECT record FROM {table}').fetchall()
                for table in (PREPARATION_TABLE, REFERENCE_TABLE, TOTALS_TABLE)} if already_official else None
    original = receiving_build.store_receiving
    def fail(*args):
        original(*args)
        conn.execute("UPDATE player_splits SET yards=999 WHERE season=2024 AND category='receiving'")
        conn.execute(f"UPDATE {PREPARATION_TABLE} SET record='{{\"invalid\":true}}'")
        raise RuntimeError('failure after metadata writes')
    monkeypatch.setattr(receiving_build, 'store_receiving', fail)
    with pytest.raises(RuntimeError, match='after metadata'):
        splits_builder.materialize(2024, receiving_inputs=inputs)
    assert snapshot(conn) == before
    if already_official:
        for table, records in metadata.items():
            assert conn.execute(f'SELECT record FROM {table}').fetchall() == records
    else:
        assert not {PREPARATION_TABLE, REFERENCE_TABLE, TOTALS_TABLE} & {
            row[0] for row in conn.execute('SHOW TABLES').fetchall()}


def test_legacy_request_or_maintenance_rebuild_cannot_overwrite_official_rows(build_case):
    conn, inputs = build_case()
    splits_builder.materialize(2024, receiving_inputs=inputs)
    before = snapshot(conn)
    for year in (2024, 2025):
        with pytest.raises(RuntimeError, match='captured offline inputs'):
            splits_builder.materialize(year)
    assert snapshot(conn) == before


def test_legacy_ingestion_is_refused_before_any_source_refresh(build_case, monkeypatch):
    import ingest
    conn, inputs = build_case()
    splits_builder.materialize(2024, receiving_inputs=inputs)
    before = snapshot(conn)
    monkeypatch.setattr(ingest, 'get_connection', lambda: conn)
    monkeypatch.setattr(ingest, 'load_and_store_raw', lambda *a, **k: pytest.fail('source refresh must not start'))
    with pytest.raises(RuntimeError, match='before any source refresh'):
        ingest.run_ingest([2025])
    assert snapshot(conn) == before


def test_rebuild_is_repeatable_and_metadata_has_one_record_per_season(build_case):
    conn, inputs = build_case()
    splits_builder.materialize(2024, receiving_inputs=inputs)
    before = snapshot(conn)
    splits_builder.materialize(2024, receiving_inputs=inputs)
    assert snapshot(conn) == before
    assert conn.execute(f'SELECT COUNT(*) FROM {PREPARATION_TABLE}').fetchone()[0] == 1


def test_early_season_without_qualified_receivers_is_a_valid_empty_population(build_case):
    conn, inputs = build_case(fault='fresh_below_qualification')
    splits_builder.materialize(2024, receiving_inputs=inputs)
    assert conn.execute("SELECT COUNT(*) FROM player_splits WHERE season=2024 AND category='receiving'").fetchone()[0] == 0
    report = json.loads(conn.execute(f'SELECT record FROM {PREPARATION_TABLE}').fetchone()[0])
    assert report['qualification']['players'] == 0 and len(report['dimensions']) == 17


def test_older_table_column_order_cannot_shift_receiving_metrics(build_case):
    conn, inputs = build_case()
    conn.execute('''CREATE TABLE reordered AS SELECT player_id,season,category,split_dim,split_value,sort_order,
                   att,cmp,yards,td,interceptions,air_yards,yac,epa,success_pct,cpoe,first_downs FROM player_splits''')
    conn.execute('DROP TABLE player_splits')
    conn.execute('ALTER TABLE reordered RENAME TO player_splits')
    splits_builder.materialize(2024, receiving_inputs=inputs)
    assert conn.execute("SELECT SUM(first_downs),MIN(epa),MIN(success_pct),COUNT(cpoe) FROM player_splits WHERE season=2024 AND category='receiving' AND split_dim='down'").fetchone() == (28,.5,100.,0)
