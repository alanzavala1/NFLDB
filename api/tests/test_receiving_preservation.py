"""Independent receiving totals survive missing targets and low split volume."""
import duckdb
import pytest

from pipeline.reconciliation import receiving_total_checks


@pytest.fixture
def receiving():
    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE weekly_player_stats (player_id VARCHAR, season INTEGER,
            week INTEGER, season_type VARCHAR, targets DOUBLE, receptions DOUBLE,
            receiving_yards DOUBLE, receiving_tds DOUBLE)''')
        conn.execute('''CREATE TABLE player_game_stats (player_id VARCHAR, game_id VARCHAR,
            season INTEGER, week INTEGER, targets DOUBLE, receptions DOUBLE,
            rec_yards DOUBLE, rec_tds DOUBLE)''')
        conn.execute('''CREATE TABLE schedules (game_id VARCHAR, game_type VARCHAR)''')
        conn.execute("INSERT INTO schedules VALUES ('week1','REG'),('week2','REG'),('playoff','WC')")
        # Ordinary receiver, lateral recipient with no catch, negative yardage.
        conn.execute('''INSERT INTO weekly_player_stats VALUES
            ('receiver',2004,1,'REG',0,4,52,1), ('lateral',2004,1,'REG',0,0,20,1),
            ('negative',2004,1,'REG',0,1,-3,0)''')
        conn.execute('''INSERT INTO player_game_stats VALUES
            ('receiver','week1',2004,1,0,4,52,1), ('lateral','week1',2004,1,0,0,20,1),
            ('negative','week1',2004,1,0,1,-3,0)''')
        yield conn


def counts(conn):
    return {name: count for name, (count, _) in receiving_total_checks(conn, 2004).items()}


def test_receiving_counts_are_preserved_without_targets_or_split_tables(receiving):
    assert counts(receiving) == {
        'player_game_receptions': 0, 'player_game_receiving_yards': 0, 'player_game_receiving_tds': 0,
    }
    # The check must not acquire a target dependency as coverage handling evolves.
    receiving.execute('ALTER TABLE weekly_player_stats DROP COLUMN targets')
    receiving.execute('ALTER TABLE player_game_stats DROP COLUMN targets')
    assert all(count == 0 for count in counts(receiving).values())


@pytest.mark.parametrize('column,check', [
    ('receptions', 'player_game_receptions'), ('rec_yards', 'player_game_receiving_yards'),
    ('rec_tds', 'player_game_receiving_tds'),
])
def test_each_corrupt_count_fails_even_for_zero_target_player(receiving, column, check):
    receiving.execute(f"UPDATE player_game_stats SET {column} = {column} - 1 WHERE player_id='receiver'")
    assert counts(receiving)[check] == 1


def test_missing_low_volume_player_or_invented_output_cannot_hide_in_other_rows(receiving):
    receiving.execute("DELETE FROM player_game_stats WHERE player_id='lateral'")
    assert counts(receiving)['player_game_receiving_yards'] == 1
    assert counts(receiving)['player_game_receiving_tds'] == 1
    receiving.execute("INSERT INTO player_game_stats VALUES ('invented','week1',2004,1,0,1,9,0)")
    assert counts(receiving)['player_game_receptions'] == 1
    assert counts(receiving)['player_game_receiving_yards'] == 2


def test_wrong_week_fails_even_when_season_total_is_unchanged(receiving):
    receiving.execute("UPDATE player_game_stats SET week=2,game_id='week2' WHERE player_id='receiver'")
    assert counts(receiving) == {
        'player_game_receptions': 2, 'player_game_receiving_yards': 2, 'player_game_receiving_tds': 2,
    }


@pytest.mark.parametrize('value', ['NULL', "'NaN'::DOUBLE", "'Infinity'::DOUBLE"])
def test_missing_or_nonfinite_prepared_yards_are_rejected(receiving, value):
    receiving.execute(f"UPDATE player_game_stats SET rec_yards={value} WHERE player_id='receiver'")
    assert counts(receiving)['player_game_receiving_yards'] == 1


def test_other_seasons_and_postseason_do_not_change_regular_season_check(receiving):
    receiving.execute("INSERT INTO weekly_player_stats VALUES ('other',2005,1,'REG',0,3,30,1),('post',2004,18,'POST',0,3,30,1)")
    receiving.execute("INSERT INTO player_game_stats VALUES ('other','week1',2005,1,0,999,999,99),('post','playoff',2004,18,0,999,999,99)")
    assert all(count == 0 for count in counts(receiving).values())


def test_unidentified_source_rows_follow_loader_identity_boundary(receiving):
    receiving.execute("INSERT INTO weekly_player_stats VALUES (NULL,2004,1,'REG',0,3,30,1)")
    assert all(count == 0 for count in counts(receiving).values())
