"""Candidate lifecycle checks use real files/processes, with synthetic source data."""
import hashlib
import json
from pathlib import Path
import subprocess

import duckdb
import pytest

from pipeline import snapshots


# Run the real worker and connection lifecycle in a fresh interpreter. Replace
# only ingestion with deterministic writes so these checks need no downloads.
WORKER_FIXTURE = '''
import os
import sys
import types
from pipeline.source_results import SourceOutcome

def ingest(seasons, log):
    import database
    conn = database.get_connection()
    outcomes = []
    mode = os.environ.get('CANDIDATE_TEST_MODE', 'played')
    for season in seasons:
        tables = ['schedules'] if mode == 'unplayed' else [
            'schedules', 'plays', 'rosters', 'weekly_player_stats', 'player_game_stats']
        for table in tables:
            conn.execute(f'INSERT INTO {table} VALUES (?, ?)', [season, 99])
            if table != 'player_game_stats':
                outcomes.append(SourceOutcome(table, season, 'loaded', 1))
        if mode == 'unplayed':
            outcomes.append(SourceOutcome('plays', season, 'not_found'))
        if mode == 'fail':
            raise RuntimeError('failure after partial database writes')
        if mode == 'bad_count':
            conn.execute('INSERT INTO plays VALUES (?, 100)', [season])
        outcomes.append(SourceOutcome('snap_counts', season, 'failed', detail='remote timeout'))
    return outcomes

sys.modules['ingest'] = types.SimpleNamespace(run_ingest=ingest)
import database
database.ensure_indexes = lambda **kwargs: None
import pipeline.awards
pipeline.awards.load_player_awards = lambda conn: None
from jobs.prepare_worker import prepare
prepare([int(s) for s in sys.argv[1:]])
'''


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'published.duckdb'
    conn = duckdb.connect(str(path))
    try:
        for table in ('schedules', 'plays', 'rosters', 'weekly_player_stats', 'player_game_stats'):
            conn.execute(f'CREATE TABLE {table} (season INTEGER, total INTEGER)')
            conn.execute(f'INSERT INTO {table} VALUES (2023, 42)')
    finally:
        conn.close()
    return path


@pytest.fixture
def synthetic_worker(monkeypatch):
    popen = subprocess.Popen

    def start(command, **kwargs):
        # Preserve _run_worker's actual interpreter, cwd and NFL_DB_PATH binding.
        return popen([command[0], '-c', WORKER_FIXTURE, *command[4:]], **kwargs)

    monkeypatch.setattr(snapshots.subprocess, 'Popen', start)
    # These lifecycle fixtures have only core columns. Full contracts/statistics
    # and the real HTTP process are exercised in test_snapshot_validation.py.
    monkeypatch.setattr(snapshots, '_run_validation', lambda candidate: None)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_success_keeps_published_bytes_and_history_and_records_coverage(
    source, synthetic_worker, tmp_path, monkeypatch,
):
    candidate = tmp_path / 'prepared.duckdb'
    before = digest(source)
    # An inherited DB override must not redirect the isolated worker's writes.
    monkeypatch.setenv('NFL_DB_PATH', str(source))
    snapshots.prepare_candidate(source, candidate, [2026, 2024, 2026])
    assert digest(source) == before
    conn = duckdb.connect(str(candidate), read_only=True)
    try:
        assert conn.execute('SELECT * FROM player_game_stats ORDER BY season').fetchall() == [
            (2023, 42), (2024, 99), (2026, 99),
        ]
        seasons, outcomes = conn.execute(
            'SELECT requested_seasons, source_outcomes FROM snapshot_preparation'
        ).fetchone()
        assert json.loads(seasons) == [2024, 2026]
        assert any(o['source'] == 'snap_counts' and o['status'] == 'failed'
                   for o in json.loads(outcomes))
    finally:
        conn.close()
    assert not Path(f'{candidate}.wal').exists()


@pytest.mark.parametrize('mode,error', [
    ('fail', subprocess.CalledProcessError), ('bad_count', snapshots.CandidateError),
])
def test_partial_build_and_failed_validation_remove_candidate_preserve_source(
    source, synthetic_worker, tmp_path, monkeypatch, mode, error,
):
    monkeypatch.setenv('CANDIDATE_TEST_MODE', mode)
    candidate = tmp_path / 'failed.duckdb'
    before = digest(source)
    with pytest.raises(error):
        snapshots.prepare_candidate(source, candidate, [2026])
    assert digest(source) == before
    assert not candidate.exists()
    assert not Path(f'{candidate}.wal').exists()


def test_schedule_only_new_season_is_allowed(source, synthetic_worker, tmp_path, monkeypatch):
    monkeypatch.setenv('CANDIDATE_TEST_MODE', 'unplayed')
    snapshots.prepare_candidate(source, tmp_path / 'future.duckdb', [2027])


def test_missing_plays_cannot_relabel_existing_season_unplayed(
    source, synthetic_worker, tmp_path, monkeypatch,
):
    monkeypatch.setenv('CANDIDATE_TEST_MODE', 'unplayed')
    # Existing schedule rows are replaced in production; clear this one here to
    # reach the stored-play guard instead of the earlier row-count guard.
    conn = duckdb.connect(str(source))
    conn.execute('DELETE FROM schedules WHERE season = 2023')
    conn.close()
    with pytest.raises(snapshots.CandidateError, match='cannot treat stored plays'):
        snapshots.prepare_candidate(source, tmp_path / 'stale.duckdb', [2023])


@pytest.mark.parametrize('existing', ['candidate', 'wal', 'same_path'])
def test_preexisting_files_never_overwritten(source, tmp_path, existing):
    candidate = source if existing == 'same_path' else tmp_path / 'candidate.duckdb'
    target = Path(f'{candidate}.wal') if existing == 'wal' else candidate
    if existing != 'same_path':
        target.write_bytes(b'keep this file')
    before, source_before = target.read_bytes(), digest(source)
    with pytest.raises((FileExistsError, snapshots.CandidateError)):
        snapshots.prepare_candidate(source, candidate, [2026])
    assert target.read_bytes() == before
    assert digest(source) == source_before


def test_source_with_pending_writes_is_not_copied(source, tmp_path):
    conn = duckdb.connect(str(source))
    try:
        conn.execute('INSERT INTO plays VALUES (2026, 1)')
        candidate = tmp_path / 'unsafe.duckdb'
        with pytest.raises(snapshots.CandidateError, match='WAL'):
            snapshots.prepare_candidate(source, candidate, [2026])
        assert not candidate.exists()
    finally:
        conn.close()


def test_copy_failure_cleans_only_new_file(source, tmp_path, monkeypatch):
    before = digest(source)
    candidate = tmp_path / 'partial.duckdb'

    def fail(origin, target):
        target.write(b'partial copy')
        raise OSError('disk full')

    monkeypatch.setattr(snapshots.shutil, 'copyfileobj', fail)
    with pytest.raises(OSError, match='disk full'):
        snapshots.prepare_candidate(source, candidate, [2026])
    assert not candidate.exists()
    assert digest(source) == before


@pytest.mark.parametrize('seasons', [[], [1998], ['2026']])
def test_invalid_seasons_do_not_create_files(source, tmp_path, seasons):
    candidate = tmp_path / 'invalid.duckdb'
    with pytest.raises(ValueError):
        snapshots.prepare_candidate(source, candidate, seasons)
    assert not candidate.exists()


def test_worker_closes_connection_on_failure(source, monkeypatch):
    import database
    import ingest
    from jobs.prepare_worker import prepare

    conn = duckdb.connect(str(source))
    monkeypatch.setenv('NFL_DB_PATH', str(source))
    monkeypatch.setattr(database, 'DB_PATH', str(source))
    monkeypatch.setattr(database, '_conn', conn)

    def fail(*args, **kwargs):
        conn.execute('INSERT INTO plays VALUES (2026, 7)')
        raise RuntimeError('build failed')

    monkeypatch.setattr(ingest, 'run_ingest', fail)
    with pytest.raises(RuntimeError, match='build failed'):
        prepare([2026])
    assert database._conn is None
    with pytest.raises(duckdb.ConnectionException, match='closed'):
        conn.execute('SELECT 1')
    assert not Path(f'{source}.wal').exists()


def test_worker_has_no_default_database_fallback(monkeypatch):
    from jobs.prepare_worker import prepare
    monkeypatch.delenv('NFL_DB_PATH', raising=False)
    with pytest.raises(RuntimeError, match='requires NFL_DB_PATH'):
        prepare([2026])


def test_worker_rejects_preimported_database_with_different_path(source, monkeypatch):
    import database
    from jobs.prepare_worker import prepare

    monkeypatch.setenv('NFL_DB_PATH', str(source))
    monkeypatch.setattr(database, 'DB_PATH', str(source.parent / 'other.duckdb'))
    with pytest.raises(RuntimeError, match='imported before the candidate path'):
        prepare([2026])


def test_worker_interruption_stops_child_before_candidate_cleanup(source, tmp_path, monkeypatch):
    calls = []
    candidate = tmp_path / 'cancelled.duckdb'

    class InterruptedProcess:
        def wait(self):
            calls.append('wait')
            assert candidate.exists()
            if len(calls) == 1:
                raise KeyboardInterrupt()

        def kill(self):
            calls.append('kill')
            assert candidate.exists()

    monkeypatch.setattr(snapshots.subprocess, 'Popen', lambda *a, **k: InterruptedProcess())
    with pytest.raises(KeyboardInterrupt):
        snapshots.prepare_candidate(source, candidate, [2026])
    assert calls == ['wait', 'kill', 'wait']
    assert not candidate.exists()


def test_no_preparation_record_fails_even_if_copied_tables_exist(source, tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, '_run_worker', lambda *a: None)
    candidate = tmp_path / 'unprepared.duckdb'
    with pytest.raises(snapshots.CandidateError, match='no preparation record'):
        snapshots.prepare_candidate(source, candidate, [2023])
    assert not candidate.exists()


def test_failed_analytics_validation_removes_candidate(source, synthetic_worker, tmp_path, monkeypatch):
    candidate = tmp_path / 'invalid-analytics.duckdb'
    before = digest(source)

    def fail(candidate):
        raise RuntimeError('analytics failed validation')

    monkeypatch.setattr(snapshots, '_run_validation', fail)
    with pytest.raises(RuntimeError, match='analytics failed validation'):
        snapshots.prepare_candidate(source, candidate, [2026])
    assert not candidate.exists()
    assert digest(source) == before
