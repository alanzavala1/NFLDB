"""Only expected optional schema gaps may become empty statistical data."""
import importlib

import duckdb
import pytest

from services import seasons, play_queries, game_detail
from sql_helpers import safe_query


@pytest.fixture
def minimal_db(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('CREATE TABLE plays (season INTEGER)')
        conn.execute('CREATE TABLE schedules (season INTEGER)')
        conn.execute('INSERT INTO schedules VALUES (2024)')
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def test_expected_table_and_column_gaps_remain_logged_empty_data(minimal_db, caplog):
    assert safe_query('SELECT * FROM ngs_passing') == []
    assert safe_query('SELECT home_wp FROM plays') == []
    assert 'safe_query failed, returning []' in caplog.text


@pytest.mark.parametrize('sql', [
    'SELECT FROM plays',
    'SELECT * FROM typo_feed',
    'SELECT nonexistent_function(season) FROM plays',
    'SELECT missing_alias.season FROM plays',
    'WITH p AS (SELECT 1 AS good) SELECT p.bad FROM p',
    'SELECT typo_metric FROM plays',
])
def test_query_bugs_do_not_become_empty_data(minimal_db, sql):
    with pytest.raises(duckdb.Error):
        safe_query(sql)


def test_season_feeds_are_independent_and_schedules_stay_visible(minimal_db):
    minimal_db.execute('DROP TABLE plays')
    assert seasons.get_season_coverage() == (set(), {2024})


def test_storage_errors_propagate_through_seasons_and_optional_query(monkeypatch):
    import sql_helpers

    def fail(*args):
        raise RuntimeError('storage unavailable')
    monkeypatch.setattr(sql_helpers, 'query_to_dict', fail)
    for action in [lambda: safe_query('SELECT * FROM plays'), seasons.get_season_coverage]:
        with pytest.raises(RuntimeError, match='storage unavailable'):
            action()


@pytest.mark.parametrize('name,args', [
    ('game_ratings_builder', ('game',)), ('ol_grades_builder', ('game',)),
    ('power_rankings_builder', (2024,)), ('comparables_builder', ('player',)),
    ('splits_builder', ('player',)), ('def_splits_builder', ('player',)),
    ('team_splits_builder', ('BUF', 2024)), ('team_analytics_builder', (2024,)),
])
def test_builder_read_failure_is_not_an_empty_dataset(monkeypatch, name, args):
    module = importlib.import_module(name)
    def fail(*args):
        raise RuntimeError('builder read failed')
    monkeypatch.setattr(module, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='builder read failed'):
        module.read(*args)


def test_play_metadata_failure_does_not_poison_availability_cache(monkeypatch):
    monkeypatch.setattr(play_queries, '_plays_columns_cache', None)
    monkeypatch.setattr(play_queries, '_plays_seasons_cache', None)
    def fail(*args):
        raise RuntimeError('metadata storage failed')
    monkeypatch.setattr(play_queries, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='metadata storage failed'):
        play_queries._plays_metadata()
    assert play_queries._plays_columns_cache is None
    assert play_queries._plays_seasons_cache is None


def test_quarter_assembly_does_not_swallow_query_bug(client, monkeypatch):
    def fail(*args):
        raise RuntimeError('quarter query failed')
    monkeypatch.setattr(game_detail, 'safe_query', fail)
    with pytest.raises(RuntimeError, match='quarter query failed'):
        client.get('/api/games/2024_01_BUF_MIA')


def test_comparables_write_failure_rolls_back_before_propagating(monkeypatch):
    import comparables_builder as builder

    statements = []

    class FailedWriter:
        def execute(self, sql, *args):
            statements.append(sql)
            if sql.startswith('DELETE'):
                raise RuntimeError('write failed')

    monkeypatch.setattr(builder, 'ensure_tables', lambda: None)
    monkeypatch.setattr(builder, 'get_connection', lambda: FailedWriter())
    monkeypatch.setattr(builder, 'query_to_dict', lambda *args: [
        {'position': 'QB', 'att': 1, 'carries': 0, 'targets': 0},
    ])
    monkeypatch.setattr(builder, '_filter_pool', lambda *args: [])
    monkeypatch.setattr(builder, '_compute_neighbors', lambda *args: [])
    with pytest.raises(RuntimeError, match='write failed'):
        builder._materialize_locked()
    assert statements == ['BEGIN', 'DELETE FROM player_career_summary', 'ROLLBACK']
