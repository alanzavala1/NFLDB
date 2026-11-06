"""Explicit whole-catalog analytics scope and shared charting input coherence."""
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pipeline.receiving_inputs import verify_stored_ftn
from pipeline.source_results import RawLoad, SourceError, SourceOutcome
from tests.test_receiving_inputs import prepare, fixture


@pytest.mark.parametrize('captured', [False, True])
def test_full_rebuild_refreshes_advanced_history_without_redownloading_historical_core(monkeypatch, captured):
    import ingest
    with duckdb.connect(':memory:') as conn:
        conn.execute("CREATE TABLE plays AS SELECT * FROM (VALUES (1999,'REG'),(2025,'POST'),(2026,'REG')) t(season,season_type)")
        monkeypatch.setattr(ingest, 'get_connection', lambda: conn)
        inputs = object() if captured else None
        refreshed = pd.DataFrame({'season': [2026]})
        calls = []
        def raw(connection, seasons, log, **options):
            assert seasons == [2026] and options == ({'core_inputs': inputs} if captured else {})
            calls.append(('raw', seasons))
            return RawLoad(refreshed, [SourceOutcome('plays', 2026, 'loaded', 1)])
        monkeypatch.setattr(ingest, 'load_and_store_raw', raw)
        monkeypatch.setattr(ingest, 'build_player_game_stats', lambda connection, plays, seasons, log: calls.append(('player_stats', seasons)))
        monkeypatch.setattr(ingest, 'load_advanced_stats', lambda connection, seasons, log: calls.append(('advanced', seasons)) or [])
        monkeypatch.setattr(ingest, 'load_supplemental_data', lambda connection, seasons, log: calls.append(('supplemental', seasons)) or [])
        monkeypatch.setattr(ingest, 'verify_stored_ftn', lambda connection, owner, seasons: calls.append(('charting_check', seasons)))
        monkeypatch.setattr(ingest, 'prepare_analytics', lambda seasons, log, **options: calls.append(('analytics', seasons)))
        ingest.run_ingest([2026], log=lambda _: None, core_inputs=inputs, rebuild_all_analytics=True)
        expected = [('raw', [2026]), ('player_stats', [2026]), ('advanced', [1999, 2026]), ('supplemental', [2026])]
        if captured:
            expected.append(('charting_check', [1999, 2026]))
        assert calls == [*expected, ('analytics', [1999, 2026])]


def test_charting_coherence_failure_stops_before_any_analytics(monkeypatch):
    import ingest
    with duckdb.connect(':memory:') as conn:
        conn.execute("CREATE TABLE plays AS SELECT 2026 AS season,'REG' AS season_type")
        monkeypatch.setattr(ingest, 'get_connection', lambda: conn)
        monkeypatch.setattr(ingest, 'load_and_store_raw', lambda *a, **k: RawLoad(pd.DataFrame({'season': [2026]}), []))
        monkeypatch.setattr(ingest, 'build_player_game_stats', lambda *a, **k: None)
        monkeypatch.setattr(ingest, 'load_advanced_stats', lambda *a, **k: [])
        monkeypatch.setattr(ingest, 'load_supplemental_data', lambda *a, **k: [])
        def fail(*args):
            raise SourceError('ftn_charting', 2026, 'different capture')
        monkeypatch.setattr(ingest, 'verify_stored_ftn', fail)
        monkeypatch.setattr(ingest, 'prepare_analytics', lambda *a, **k: pytest.fail('analytics must not start'))
        with pytest.raises(SourceError, match='different capture'):
            ingest.run_ingest([2026], core_inputs=object(), rebuild_all_analytics=True)


@pytest.mark.parametrize('fault', [None, 'flag', 'rush_count', 'missing', 'duplicate', 'absent_table', 'retained_after_outage'])
def test_stored_charting_matches_the_bound_projection(tmp_path, monkeypatch, fault):
    from pipeline.source_results import VendorFeed
    if fault == 'retained_after_outage':
        monkeypatch.setattr('pipeline.vendor_sources.fetch_vendor', lambda *a: VendorFeed('ftn_charting', None,
            [SourceOutcome('ftn_charting', 2024, 'not_found')]))
        from pipeline.receiving_inputs import prepare_receiving_inputs
        from pipeline.receiving_preview import file_sha256
        prepare_receiving_inputs(tmp_path, [2024])
        manifest = {'files': {p.name: file_sha256(p) for p in tmp_path.iterdir()}}
    else:
        manifest, _ = prepare(tmp_path, monkeypatch)
    class Inputs:
        def receiving_run(self, season):
            return tmp_path, manifest, 'unused completion digest'
    with duckdb.connect(':memory:') as conn:
        conn.register('source', fixture().assign(n_defense_box=6))
        if fault != 'absent_table':
            conn.execute('CREATE TABLE ftn_charting AS SELECT * FROM source')
            if fault == 'flag': conn.execute('UPDATE ftn_charting SET is_play_action=true')
            if fault == 'rush_count': conn.execute('UPDATE ftn_charting SET n_pass_rushers=5')
            if fault == 'missing': conn.execute('DELETE FROM ftn_charting')
            if fault == 'duplicate': conn.execute('INSERT INTO ftn_charting SELECT * FROM source')
        if fault is None:
            verify_stored_ftn(conn, Inputs(), [2024])  # Additional full-feed fields survive.
        else:
            with pytest.raises(SourceError, match='stored fields differ'):
                verify_stored_ftn(conn, Inputs(), [2024])


def test_candidate_cli_and_worker_forward_the_explicit_scope(monkeypatch):
    from jobs import prepare as command
    from pipeline import snapshots
    calls = []
    monkeypatch.setattr(command, 'prepare_candidate', lambda *args, **options: calls.append((args, options)))
    command.main(['--source', 'source.duckdb', '--candidate', 'new.duckdb', '--seasons', '2026',
                  '--core-inputs', 'bundle', '--rebuild-all-analytics'])
    assert calls[0][1] == {'core_inputs': Path('bundle'), 'rebuild_all_analytics': True}
    calls.clear()
    monkeypatch.setattr(snapshots, '_run_job', lambda *args: calls.append(args))
    snapshots._run_worker(Path('candidate'), [2026], core_inputs=Path('bundle'), rebuild_all_analytics=True)
    assert calls == [(Path('candidate'), 'jobs.prepare_worker',
                      ['--seasons', '2026', '--core-inputs', 'bundle', '--rebuild-all-analytics'])]
