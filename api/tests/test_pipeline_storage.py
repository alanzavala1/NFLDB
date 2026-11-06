"""Player-game writes have a narrow create fallback and preserve other seasons."""
import duckdb
import pandas as pd
import pytest

from pipeline.storage import store_player_game_stats, upsert_by_season


def test_create_then_replace_one_season_preserves_other_stored_season():
    with duckdb.connect(':memory:') as conn:
        frame = pd.DataFrame({'season': [2023, 2024], 'player_id': ['p', 'p'], 'attempts': [10, 20]})
        store_player_game_stats(conn, frame, [2023, 2024])
        replacement = pd.DataFrame({'season': [2024], 'player_id': ['p'], 'attempts': [30]})
        store_player_game_stats(conn, replacement, [2024])
        assert conn.execute('SELECT season, attempts FROM player_game_stats ORDER BY season').fetchall() == [(2023, 10), (2024, 30)]


def test_captured_plays_can_add_missing_typed_columns_without_discarding_history():
    with duckdb.connect(':memory:') as conn:
        conn.execute("CREATE TABLE plays AS SELECT 2023 AS season, 'historical' AS game_id")
        fresh = pd.DataFrame({'season':[2024], 'game_id':['fresh'], 'ydstogo':[7.]})
        upsert_by_season(conn, 'plays', fresh, [2024], evolve_schema=True)
        assert conn.execute('SELECT season,game_id,ydstogo FROM plays ORDER BY season').fetchall() == [(2023,'historical',None),(2024,'fresh',7.)]
        assert conn.execute('DESCRIBE plays').fetchall()[-1][1] == 'DOUBLE'


def test_default_feed_storage_still_uses_existing_columns():
    with duckdb.connect(':memory:') as conn:
        conn.execute('CREATE TABLE feed (season INTEGER)')
        upsert_by_season(conn, 'feed', pd.DataFrame({'season':[2024], 'optional':[7]}), [2024])
        assert conn.execute('SELECT * FROM feed').fetchall() == [(2024,)]


def test_captured_plays_widen_old_numeric_id_columns_instead_of_silently_nulling_ids():
    with duckdb.connect(':memory:') as conn:
        conn.execute('CREATE TABLE plays (season INTEGER,tackle_for_loss_2_player_id INTEGER,epa INTEGER)')
        conn.execute('INSERT INTO plays VALUES (1999,NULL,1)')
        fresh = pd.DataFrame({'season':[2001], 'tackle_for_loss_2_player_id':['00-0015106'], 'epa':[.25]})
        upsert_by_season(conn, 'plays', fresh, [2001], evolve_schema=True)
        assert conn.execute('SELECT * FROM plays ORDER BY season').fetchall() == [(1999,None,1.),(2001,'00-0015106',.25)]


@pytest.mark.parametrize('table', ['pfr_pass', 'pfr_rush', 'pfr_rec', 'pfr_def', 'qbr_season', 'qbr_weekly'])
def test_new_vendor_write_targets_are_created_without_optional_read_registry(table):
    with duckdb.connect(':memory:') as conn:
        upsert_by_season(conn, table, pd.DataFrame({'season': [2025], 'value': [7]}), [2025])
        assert conn.execute(f'SELECT * FROM {table}').fetchall() == [(2025, 7)]


def test_missing_view_dependency_does_not_trigger_new_vendor_table_creation():
    with duckdb.connect(':memory:') as conn:
        conn.execute('CREATE TABLE plays (season INTEGER)')
        conn.execute('CREATE VIEW pfr_pass AS SELECT * FROM plays')
        conn.execute('DROP TABLE plays')
        with pytest.raises(duckdb.CatalogException, match='Table with name plays does not exist'):
            upsert_by_season(conn, 'pfr_pass', pd.DataFrame({'season': [2025]}), [2025])


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


def test_receiving_composition_preserves_production_when_target_credits_are_zero():
    from pipeline.player_stats import build_player_game_stats
    from pipeline.reconciliation import receiving_total_checks
    from tests.conftest import _create_schema, _seed
    from tests.test_weekly_columns import _feed_frame

    with duckdb.connect(':memory:') as conn:
        _create_schema(conn)
        _seed(conn)
        weekly = pd.concat([
            _feed_frame(2024).assign(game_id='2024_01_BUF_MIA', player_id=player,
                player_name=player, targets=0, receptions=catches, receiving_yards=yards,
                receiving_tds=tds)
            for player, catches, yards, tds in (
                ('receiver', 4, 52, 1), ('lateral', 0, 20, 1), ('negative', 1, -3, 0))
        ], ignore_index=True)
        conn.register('weekly', weekly)
        conn.execute('CREATE TABLE weekly_player_stats AS SELECT * FROM weekly')
        build_player_game_stats(conn, conn.execute('SELECT * FROM plays').df(), [2024])
        assert conn.execute('''SELECT player_id, receptions, rec_yards, rec_tds
            FROM player_game_stats WHERE player_id IN ('receiver','lateral','negative')
            ORDER BY player_id''').fetchall() == [
                ('lateral', 0, 20, 1), ('negative', 1, -3, 0), ('receiver', 4, 52, 1)]
        assert all(count == 0 for count, _ in receiving_total_checks(conn, 2024).values())
