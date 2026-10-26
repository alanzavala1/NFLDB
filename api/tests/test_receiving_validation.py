"""Source-bound receiving replay and deliberate corruptions of stored results."""
import asyncio
import hashlib
import json

import pytest

import database
import splits_builder
from pipeline.receiving_api_checks import check_receiving_api
from pipeline.receiving_build import PREPARATION_TABLE, REFERENCE_TABLE, TOTALS_TABLE
from pipeline.receiving_validation import validate_receiving
from pipeline.validation import SnapshotValidationError, validate_snapshot
from tests.test_receiving_build import build_case, fake_export


@pytest.fixture
def receiving_case(build_case, monkeypatch):
    def make(year=2024, fault=None):
        conn, inputs = build_case(year, fault)
        # This scoped validator requires a whole loaded catalog. The build
        # fixture's unrelated 1998 preservation row is intentionally not one.
        conn.execute("DELETE FROM player_splits WHERE player_id='older'")
        conn.execute("""CREATE TABLE player_game_stats AS SELECT 'game' AS game_id,
            season,player_id,week,receptions,receiving_yards AS rec_yards,receiving_tds AS rec_tds
            FROM weekly_player_stats""")
        splits_builder.materialize(year, receiving_inputs=inputs)
        monkeypatch.setattr(database, '_conn', conn)
        return conn, inputs
    return make


def change_record(conn, table, edit):
    record = json.loads(conn.execute(f'SELECT record FROM {table}').fetchone()[0])
    edit(record)
    conn.execute(f'UPDATE {table} SET record=?', [json.dumps(record)])


@pytest.mark.parametrize('year,fault', [
    (1999, None), (2004, None), (2006, None), (2009, 'missing_air'), (2024, None), (2026, None),
    (2024, 'partial_context'), (2024, 'unavailable_context'), (2024, 'charting_gap'),
    (2024, 'charting_unavailable'), (2024, 'rush_outlier'), (2024, 'fresh_below_qualification'),
])
def test_replay_accepts_supported_missing_and_partial_populations(receiving_case, monkeypatch, year, fault):
    from pipeline import receiving_preview
    conn, inputs = receiving_case(year, fault)
    monkeypatch.setattr(splits_builder, 'materialize', lambda *a, **kw: pytest.fail('validation attempted builder writes'))
    monkeypatch.setattr(receiving_preview, '_run_export', lambda *a, **kw: pytest.fail('validation attempted R export'))
    result = validate_receiving(conn, inputs)
    assert result['played_seasons'] == [year]
    assert result['status'] == 'passed' and result['publication_ready'] is False
    assert result['seasons'][year]['views'] == 17
    assert asyncio.run(check_receiving_api(conn, [year]))
    # Scoped validation must not silently change the publication contract.
    with pytest.raises(SnapshotValidationError, match='coverage-aware API/UI'):
        validate_snapshot(conn)


@pytest.mark.parametrize('sql', [
    "UPDATE player_splits SET yards=yards+1 WHERE category='receiving' AND split_dim='down'",
    "DELETE FROM player_splits WHERE category='receiving' AND split_dim='down'",
    "UPDATE player_splits SET epa=0 WHERE category='receiving' AND epa IS NOT NULL",
    "UPDATE player_splits SET split_value='unknown' WHERE category='receiving' AND split_dim='down' AND split_value='1'",
    "INSERT INTO player_splits BY NAME SELECT * REPLACE ('not-qualified' AS player_id) FROM player_splits WHERE category='receiving' LIMIT 1",
])
def test_changed_missing_extra_or_misclassified_rows_fail(receiving_case, sql):
    conn, inputs = receiving_case()
    conn.execute(sql)
    with pytest.raises(SnapshotValidationError, match='player_splits.*differs from bound source replay'):
        validate_receiving(conn, inputs)


@pytest.mark.parametrize('year,fault,column', [(2004, None, 'att'), (2004, None, 'yac'), (2009, 'missing_air', 'air_yards')])
def test_unsupported_fields_cannot_be_changed_from_null_to_zero(receiving_case, year, fault, column):
    conn, inputs = receiving_case(year, fault)
    conn.execute(f"UPDATE player_splits SET {column}=0 WHERE category='receiving' AND {column} IS NULL")
    with pytest.raises(SnapshotValidationError, match='differs from bound source replay'):
        validate_receiving(conn, inputs)


@pytest.mark.parametrize('table,edit', [
    (TOTALS_TABLE, lambda record: record['rows'][0].update(epa=14.)),  # raw EPA sum is not EPA/tgt
    (TOTALS_TABLE, lambda record: record['rows'][0]['excluded_counts']['field_zone'].update(cmp=0)),
    (TOTALS_TABLE, lambda record: record.update(metric_policy_applied=1)),
    (REFERENCE_TABLE, lambda record: record['rows'][0].update(receiving_yards=999)),
    (PREPARATION_TABLE, lambda record: record['qualification']['qualifying_plays'].update(receiver=99)),
    (PREPARATION_TABLE, lambda record: record['game_coverage'].update(status='complete')),
    (PREPARATION_TABLE, lambda record: record['dimensions'].pop('quarter')),
])
def test_metadata_is_verified_against_sources_not_its_own_claims(receiving_case, table, edit):
    conn, inputs = receiving_case(fault='partial_context')
    # Make the status edit a real false claim, distinct from missing PBP.
    conn.execute("UPDATE schedules SET home_score=NULL")
    splits_builder.materialize(2024, receiving_inputs=inputs)
    change_record(conn, table, edit)
    with pytest.raises(SnapshotValidationError, match='differs from bound source replay'):
        validate_receiving(conn, inputs)


def test_internally_conserved_wrong_counts_still_fail_bound_replay(receiving_case):
    conn, inputs = receiving_case()
    # Add one yard to a bucket in EACH view and to its whole/exclusion records.
    # API conservation alone can still pass; the independent source replay must fail.
    conn.execute("""UPDATE player_splits SET yards=yards+1 WHERE category='receiving'
        AND (split_dim,split_value) IN (SELECT split_dim,MIN(split_value) FROM player_splits
                                      WHERE category='receiving' GROUP BY split_dim)""")
    change_record(conn, TOTALS_TABLE, lambda record: record['rows'][0].update(yards=281))
    change_record(conn, REFERENCE_TABLE, lambda record: record['rows'][0].update(receiving_yards=281))
    def edit_report(record):
        for dimension in record['dimensions'].values():
            for population in ('classified', 'overall'):
                dimension['coverage']['qualified_production'][population]['receiving_yards'] += 1
    change_record(conn, PREPARATION_TABLE, edit_report)
    assert asyncio.run(check_receiving_api(conn, [2024]))
    with pytest.raises(SnapshotValidationError, match='differs from bound source replay'):
        validate_receiving(conn, inputs)


@pytest.mark.parametrize('change', ['plays', 'weekly', 'export'])
def test_stale_core_rows_or_changed_export_bytes_fail(receiving_case, change):
    conn, inputs = receiving_case()
    if change == 'plays':
        conn.execute('UPDATE plays SET epa=123 WHERE play_id=0')
    elif change == 'weekly':
        conn.execute('UPDATE weekly_player_stats SET receptions=999')
    else:
        with (inputs.directory / 'field_zone-2024.csv').open('ab') as stream:
            stream.write(b'\n')
    with pytest.raises(SnapshotValidationError, match='Receiving validation failed'):
        validate_receiving(conn, inputs)


@pytest.mark.parametrize('sql,error', [
    ('DROP TABLE receiving_season_totals', 'missing prepared table'),
    ('DELETE FROM receiving_build_preparation', 'every loaded REG season'),
    ('CREATE OR REPLACE TABLE receiving_whole_reference AS SELECT * FROM receiving_whole_reference UNION ALL SELECT * FROM receiving_whole_reference', 'exactly once'),
    ('ALTER TABLE receiving_season_totals ALTER COLUMN record TYPE VARCHAR', 'expected JSON'),
    ('ALTER TABLE player_splits ALTER COLUMN yac TYPE BIGINT', 'expected INTEGER'),
    ("UPDATE receiving_season_totals SET record='[]'", 'record must be an object'),
    ("INSERT INTO plays BY NAME SELECT * REPLACE (2023 AS season) FROM plays LIMIT 1", 'every loaded REG season'),
    ("INSERT INTO player_splits(player_id,season,category,split_dim,split_value) VALUES ('orphan',2023,'receiving','down','1')", 'outside loaded regular seasons'),
])
def test_schema_and_whole_catalog_coverage_fail_closed(receiving_case, sql, error):
    conn, inputs = receiving_case()
    conn.execute(sql)
    with pytest.raises(SnapshotValidationError, match=error):
        validate_receiving(conn, inputs)


def test_edited_http_response_is_detected_after_stored_data_passes(receiving_case, monkeypatch):
    from routers import players
    conn, inputs = receiving_case()
    assert validate_receiving(conn, inputs)['status'] == 'passed'
    original = players.read_player_receiving
    def bad_response(player):
        response = original(player)
        response.seasons[0].overall.yards = 999
        return response
    monkeypatch.setattr(players, 'read_player_receiving', bad_response)
    with pytest.raises(SnapshotValidationError, match='whole response differs'):
        asyncio.run(check_receiving_api(conn, [2024]))


def test_below_threshold_game_log_counts_cannot_disappear(receiving_case):
    conn, inputs = receiving_case(fault='fresh_below_qualification')
    assert conn.execute("SELECT COUNT(*) FROM player_splits WHERE category='receiving'").fetchone()[0] == 0
    conn.execute("UPDATE player_game_stats SET rec_yards=0 WHERE player_id='receiver'")
    with pytest.raises(SnapshotValidationError, match='player_game_receiving_yards'):
        validate_receiving(conn, inputs)


@pytest.mark.parametrize('corrupt', [False, True])
def test_validation_command_is_readonly_even_on_failure(receiving_case, monkeypatch, tmp_path, capsys, corrupt):
    from jobs.validate_receiving import main
    from pipeline import receiving_core_collection
    conn, inputs = receiving_case(fault='partial_context')
    if corrupt:
        conn.execute("UPDATE player_splits SET yards=999 WHERE category='receiving'")
    path = tmp_path / 'receiving.duckdb'
    escaped = str(path).replace("'", "''")
    conn.execute(f"ATTACH '{escaped}' AS candidate")
    conn.execute('COPY FROM DATABASE memory TO candidate')
    conn.execute('DETACH candidate')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(database, 'DB_PATH', str(path))
    monkeypatch.setattr(database, '_conn', None)
    monkeypatch.setattr(receiving_core_collection, 'open_core_inputs', lambda directory: inputs)
    for key in ('NFL_DB_PATH', 'NFL_DB_READ_ONLY', 'NFL_TEST_MODE'):
        monkeypatch.setenv(key, '')  # Track/restore the CLI's environment changes.
    arguments = ['--database', str(path), '--core-inputs', str(inputs.directory)]
    if corrupt:
        with pytest.raises(SnapshotValidationError, match='differs from bound source replay'):
            main(arguments)
    else:
        main(arguments)
        result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert result['status'] == 'passed' and result['publication_ready'] is False
        assert result['api_requests'] == ['/api/players/receiver/receiving-splits']
    assert database._conn is None
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not path.with_suffix('.duckdb.wal').exists()
