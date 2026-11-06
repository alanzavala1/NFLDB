"""Physical read-only mode, real startup and cold requests cannot repair data."""
import hashlib
import importlib
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from tests.conftest import _create_schema, _seed


BUILDERS = ['splits_builder', 'def_splits_builder', 'team_splits_builder', 'team_analytics_builder',
            'power_rankings_builder', 'game_ratings_builder', 'ol_grades_builder', 'comparables_builder']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_startup_and_cold_requests_leave_file_and_schema_unchanged(tmp_path, monkeypatch):
    import database
    import pipeline.awards
    from main import app
    path = tmp_path / 'published.duckdb'
    with duckdb.connect(str(path)) as conn:
        _create_schema(conn)
        _seed(conn)
        tables = conn.execute('SHOW TABLES').fetchall()
    before = digest(path)
    monkeypatch.setattr(database, '_conn', None)
    monkeypatch.setattr(database, 'DB_PATH', str(path))
    monkeypatch.delenv('NFL_DB_READ_ONLY', raising=False)
    monkeypatch.setenv('ADMIN_TOKEN', 'test-token')
    def forbidden(*args, **kwargs): raise AssertionError('Serving attempted offline preparation')
    monkeypatch.setattr(database, 'ensure_indexes', forbidden)
    monkeypatch.setattr(pipeline.awards, 'load_player_awards', forbidden)
    for name in BUILDERS:
        monkeypatch.setattr(importlib.import_module(name), 'materialize', forbidden)
    try:
        with TestClient(app) as client:
            for url in ['/api/health', '/api/seasons', '/api/players/00-BUF-QB1/splits',
                        '/api/players/absent/splits', '/api/players/absent/def-splits',
                        '/api/players/00-BUF-QB1/comparables', '/api/teams/BUF/splits?season=2024',
                        '/api/team-analytics?season=2024', '/api/power-rankings?season=2024',
                        '/api/games/2024_01_BUF_MIA/ratings']:
                response = client.get(url)
                assert response.status_code == 200, (url, response.text)
            # Required join dependencies are unavailable, never built or leaked.
            response = client.get('/api/games/2024_01_BUF_MIA/lineup')
            assert response.status_code == 503
            assert response.json()['detail'] == 'Published data is unavailable for this view. Please try again later.'
            for headers in [{}, {'x-admin-token': 'test-token'}]:
                assert client.post('/api/seasons/2024/load?force=true', headers=headers).status_code == 410
                assert client.get('/api/seasons/2024/progress', headers=headers).status_code == 410
            conn = database.get_connection()
            with pytest.raises(duckdb.InvalidInputException, match='read-only'):
                conn.execute('CREATE TABLE forbidden_write (value INTEGER)')
            assert conn.execute('SHOW TABLES').fetchall() == tables
    finally:
        database.close_connection()
    assert digest(path) == before
    assert not Path(str(path)+'.wal').exists()


def test_default_reader_does_not_create_a_missing_database_or_directory(tmp_path, monkeypatch):
    import database
    path = tmp_path / 'missing' / 'missing.duckdb'
    monkeypatch.setattr(database, '_conn', None)
    monkeypatch.setattr(database, 'DB_PATH', str(path))
    monkeypatch.delenv('NFL_DB_READ_ONLY', raising=False)
    with pytest.raises(duckdb.IOException): database.get_connection()
    assert not path.parent.exists()


def test_legacy_offline_refresh_cannot_silently_open_serving_database(monkeypatch, tmp_path):
    from jobs.refresh import cmd_ingest
    monkeypatch.delenv('NFL_DB_READ_ONLY', raising=False)
    with pytest.raises(RuntimeError, match='requires NFL_DB_READ_ONLY=0'):
        cmd_ingest(str(tmp_path / 'watermarks.json'))
    assert not (tmp_path / 'watermarks.json').exists()


def test_offline_writer_opt_in_cannot_be_used_by_app_startup(tmp_path, monkeypatch):
    import database
    from main import app
    monkeypatch.setattr(database, '_conn', None)
    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path / 'candidate.duckdb'))
    monkeypatch.setenv('NFL_DB_READ_ONLY', '0')
    try:
        database.get_connection().execute('CREATE TABLE offline_result (value INTEGER)')
        with pytest.raises(RuntimeError, match='read-only snapshot'):
            with TestClient(app): pass
    finally:
        database.close_connection()
