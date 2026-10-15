"""Player-game writes have a narrow create fallback and preserve other seasons."""
import duckdb
import pandas as pd
import pytest

from pipeline.storage import store_player_game_stats


def test_create_then_replace_one_season_preserves_other_stored_season():
    with duckdb.connect(':memory:') as conn:
        frame = pd.DataFrame({'season': [2023, 2024], 'player_id': ['p', 'p'], 'attempts': [10, 20]})
        store_player_game_stats(conn, frame, [2023, 2024])
        replacement = pd.DataFrame({'season': [2024], 'player_id': ['p'], 'attempts': [30]})
        store_player_game_stats(conn, replacement, [2024])
        assert conn.execute('SELECT season, attempts FROM player_game_stats ORDER BY season').fetchall() == [(2023, 10), (2024, 30)]


@pytest.mark.parametrize('stage', ['SELECT 1', 'DELETE', 'DESCRIBE', 'INSERT'])
def test_faults_do_not_trigger_create_fallback(stage):
    statements = []

    class FailedWriter:
        def register(self, *args):
            pass

        def execute(self, sql, *args):
            statements.append(sql)
            if sql.startswith(stage):
                raise RuntimeError('original storage fault')
            return self

        def fetchall(self):
            return [('season',)]

        def fetchone(self):
            return (1,)

    with pytest.raises(RuntimeError, match='original storage fault'):
        store_player_game_stats(FailedWriter(), pd.DataFrame({'season': [2024]}), [2024])
    assert not any(sql.startswith('CREATE') for sql in statements)


def test_real_insert_conversion_error_is_not_masked_by_table_already_exists():
    with duckdb.connect(':memory:') as conn:
        conn.execute('CREATE TABLE player_game_stats (season INTEGER, attempts INTEGER)')
        with pytest.raises(duckdb.ConversionException):
            store_player_game_stats(conn, pd.DataFrame({'season': [2024], 'attempts': ['invalid']}), [2024])


def test_broken_view_dependency_is_not_mistaken_for_absent_player_stats():
    with duckdb.connect(':memory:') as conn:
        conn.execute('CREATE TABLE plays (season INTEGER)')
        conn.execute('CREATE VIEW player_game_stats AS SELECT * FROM plays')
        conn.execute('DROP TABLE plays')
        with pytest.raises(duckdb.CatalogException, match='Table with name plays does not exist'):
            store_player_game_stats(conn, pd.DataFrame({'season': [2024]}), [2024])


def test_player_composition_uses_official_totals_and_keeps_other_seasons():
    from pipeline.player_stats import build_player_game_stats
    from tests.conftest import _create_schema, _seed
    from tests.test_weekly_columns import _feed_frame

    with duckdb.connect(':memory:') as conn:
        _create_schema(conn)
        _seed(conn)
        weekly = _feed_frame(2024).assign(
            game_id='2024_01_DEN_KC', player_id='00-KC-QB1', player_name='Patrick Mahomes',
            attempts=25, passing_yards=321, passing_tds=3, passing_epa=7.5,
        )
        conn.register('weekly', weekly)
        conn.execute('CREATE TABLE weekly_player_stats AS SELECT * FROM weekly')
        conn.execute("""INSERT INTO player_game_stats (game_id, season, week, team, player_id, player_name)
                        VALUES ('historical', 2023, 1, 'KC', 'old', 'Historical')""")
        plays = conn.execute('SELECT * FROM plays').df()
        build_player_game_stats(conn, plays, [2024])
        assert conn.execute("""SELECT attempts, pass_yards, pass_tds, pass_epa FROM player_game_stats
                               WHERE player_id = '00-KC-QB1'""").fetchone() == (25, 321, 3, 7.5)
        assert conn.execute("SELECT fg_made FROM player_game_stats WHERE player_id = '00-KC-K1'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM player_game_stats WHERE season = 2023").fetchone()[0] == 1
