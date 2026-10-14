"""Offline snap joins, scoring, averages and lineup HTTP absence handling."""
from itertools import groupby

import duckdb
import pytest

import game_ratings_builder
from schemas.lineup import GameLineup
from services import game_lineup
from tests.conftest import _create_schema, _seed

GAME_ID = '2024_01_BUF_MIA'


@pytest.fixture
def league(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        _create_schema(conn)
        _seed(conn)
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


@pytest.fixture
def joined_players(league, monkeypatch):
    for table in ('snap_counts', 'rosters', 'id_map', 'player_game_stats', 'plays'):
        league.execute(f'DELETE FROM {table}')
    game_ratings_builder.ensure_table(league)
    league.executemany('''INSERT INTO rosters
        (player_id, season, week, team, position, jersey_number, player_name, football_name, pfr_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', [
        ('direct', 2024, 3, 'BUF', 'QB', 7, 'Canonical Direct', None, 'p1'),
        ('direct', 2024, 1, 'BUF', 'QB', 4, 'Old Direct', None, 'p1'),
        ('wrong-team', 2024, 99, 'MIA', 'QB', 9, 'Wrong Team', None, 'p1'),
        ('wrong-year', 2025, 99, 'BUF', 'QB', 99, 'Wrong Year', None, 'p1'),
        ('mapped', 2024, 2, 'BUF', 'WR', 18, 'Canonical Mapped', None, None),
        ('football', 2024, 2, 'BUF', 'WR', 20, 'Nicholas Receiver', 'Nick Receiver', None),
        ('normal', 2024, 2, 'BUF', 'DL', 90, 'Alpha Defender', None, None),
    ])
    league.execute("INSERT INTO id_map VALUES ('p2', 'mapped', 'Mapped Fallback', 'WR', 'BUF', 2024)")
    league.executemany('''INSERT INTO snap_counts
        (game_id, season, week, player, pfr_player_id, position, team,
         offense_snaps, offense_pct, defense_snaps, defense_pct, st_snaps, st_pct)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', [
        (GAME_ID, 2024, 'Direct Snap', 'p1', 'QB', 'BUF', 60, 1, 0, 0, 0, 0),
        (GAME_ID, 2024, 'Mapped Snap', 'p2', 'WR', 'BUF', 50, 0.8, 0, 0, 0, 0),
        (GAME_ID, 2024, 'Nick Receiver', 'p3', 'WR', 'BUF', 45, 0.7, 0, 0, 0, 0),
        (GAME_ID, 2024, 'Alpha! Defender', 'p4', 'DE', 'BUF', 0, 0, 50, 0.9, 0, 0),
        (GAME_ID, 2024, 'Mystery Tackle', 'p5', 'T', 'BUF', 40, 0.6, 0, 0, 0, 0),
        (GAME_ID, 2024, 'No Pfr Identity', None, 'K', 'BUF', 0, 0, 0, 0, 5, 0.2),
        (GAME_ID, 2023, 'Wrong Season', 'p1', 'QB', 'BUF', 99, 1, 0, 0, 0, 0),
        (GAME_ID, 2024, 'Wrong Game Team', 'p1', 'QB', 'NYJ', 99, 1, 0, 0, 0, 0),
        ('other-game', 2024, 'Wrong Game', 'p1', 'QB', 'BUF', 99, 1, 0, 0, 0, 0),
    ])
    league.executemany('''INSERT INTO player_game_ratings
        (player_id, game_id, season, week, team, position_group, rating, plays_counted)
        VALUES (?, ?, 2024, 1, 'BUF', ?, ?, ?)''', [
        ('direct', GAME_ID, 'QB', 6, 30), ('mapped', GAME_ID, 'WR', 8, 10),
        ('normal', GAME_ID, 'DEF', 7, 5),
    ])
    league.executemany('''INSERT INTO player_game_stats
        (player_id, player_name, game_id, season, week, team, pass_yards)
        VALUES ('direct', 'Stats Direct', ?, 2024, 1, 'BUF', ?)''', [(GAME_ID, 40), (GAME_ID, 60)])
    league.executemany('''INSERT INTO plays
        (play_id, game_id, season, qtr, game_seconds_remaining, posteam, td_team,
         td_player_id, touchdown, field_goal_result, kicker_player_id, kicker_player_name,
         kick_distance, extra_point_result, "desc")
        VALUES (?, ?, 2024, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', [
        (1, GAME_ID, 3000, 'BUF', 'BUF', 'direct', 1, None, None, None, None, None, 'Direct TD'),
        (2, GAME_ID, 2000, 'MIA', 'BUF', 'normal', 1, None, None, None, None, None, 'Defensive TD'),
        (3, GAME_ID, 1000, 'BUF', None, None, 0, 'made', 'kick', 'Unmapped Kicker', 45, None, 'Made FG'),
        (4, GAME_ID, 999, 'BUF', None, None, 0, None, 'kick', 'Unmapped Kicker', None, 'good', 'PAT'),
        (5, GAME_ID, 998, 'BUF', None, None, 0, 'missed', 'kick', 'Unmapped Kicker', 50, None, 'Missed FG'),
        (6, 'other-game', 3500, 'BUF', 'BUF', 'direct', 1, None, None, None, None, None, 'Other game TD'),
    ])
    monkeypatch.setattr(game_lineup.game_ratings_builder, 'read_or_materialize', lambda game_id: [{}])
    monkeypatch.setattr(game_lineup.ol_grades_builder, 'read_or_materialize', lambda game_id: {'BUF': {'grade': 6.5}})
    return league


def _http_lineup(lineup):
    return GameLineup.model_validate(lineup).model_dump(mode='json')


def _rotation_ties(lineup):
    # SQL and the selector leave exact rotation priority ties unordered.
    # Normalize only adjacent tied runs; preserve distinct priorities and all other lists.
    def priority(player):
        return (player['rating'] is not None, player['rating'] or -1, player['snaps'])
    return {**lineup, 'teams': [{**team, 'rotation': [
        player for _, tied in groupby(team['rotation'], priority)
        for player in sorted(tied, key=lambda row: (row['player_id'] or '', row['pfr_player_id'] or ''))
    ]} for team in lineup['teams']]}


def test_seeded_service_http_and_real_lazy_builders_match(client, league):
    lineup = game_lineup.get_game_lineup('2024_01_DEN_KC')
    assert lineup['join_match_rate'] == 1
    kc = lineup['teams'][1]
    assert kc['team'] == 'KC' and len(kc['offense']) == len(kc['defense']) == 11
    assert league.execute('SELECT COUNT(*) FROM player_game_ratings').fetchone()[0] > 0
    assert league.execute('SELECT COUNT(*) FROM team_game_ol_grades').fetchone()[0] > 0
    response = client.get('/api/games/2024_01_DEN_KC/lineup')
    assert response.status_code == 200
    assert _rotation_ties(response.json()) == _rotation_ties(_http_lineup(lineup))


def test_identity_paths_scopes_unmatched_rows_averages_and_http_parity(client, joined_players):
    lineup = game_lineup.get_game_lineup(GAME_ID)
    assert lineup['join_match_rate'] == 0.8
    away, home = lineup['teams']
    assert (away['side'], home['side']) == ('away', 'home')
    players = {row['player_id']: row for row in away['offense'] + away['defense']}
    direct = players['direct']
    assert (direct['player_name'], direct['jersey_number'], direct['snaps'], direct['plays_counted']) == ('Canonical Direct', 7, 60, 30)
    assert players['mapped']['player_name'] == 'Canonical Mapped'
    assert players['football']['player_name'] == 'Nicholas Receiver'
    assert players['normal']['position'] == 'DL' and players['normal']['scored_td'] is True
    assert players[None]['player_name'] == 'Mystery Tackle'
    assert players[None]['rating'] is None and players[None]['jersey_number'] is None
    assert (away['avg_rating'], away['offense_avg'], away['defense_avg'], away['ol_grade']) == (7, 7, 7, 6.5)
    assert home['offense'] == home['defense'] == home['rotation'] == []
    assert home['avg_rating'] is None and home['ol_grade'] is None
    assert [row['player_name'] for row in away['rotation']] == ['Mystery Tackle', 'No Pfr Identity']
    response = client.get(f'/api/games/{GAME_ID}/lineup')
    assert response.status_code == 200 and response.json() == _http_lineup(lineup)


def test_scoring_order_defensive_attribution_and_name_fallbacks(joined_players):
    scoring = game_lineup.get_game_lineup(GAME_ID)['scoring']
    assert [(row['kind'], row['team'], row['player_name']) for row in scoring] == [
        ('TD', 'BUF', 'Stats Direct'), ('TD', 'BUF', 'Alpha Defender'), ('FG', 'BUF', 'Unmapped Kicker'),
    ]
    assert scoring[-1]['distance'] == 45
    assert [row['desc'] for row in scoring] == ['Direct TD', 'Defensive TD', 'Made FG']


def test_historical_franchise_snap_abbreviation_is_mapped(client, joined_players):
    joined_players.execute('''INSERT INTO schedules
        (game_id, season, game_type, week, away_team, home_team)
        VALUES ('historical', 2014, 'REG', 1, 'STL', 'BUF')''')
    joined_players.execute('''INSERT INTO snap_counts
        (game_id, season, week, player, pfr_player_id, team, position, offense_snaps)
        VALUES ('historical', 2014, 1, 'Historic Tackle', 'historic-pfr', 'LA', 'T', 40)''')
    lineup = game_lineup.get_game_lineup('historical')
    assert lineup['teams'][0]['offense'][0]['team'] == 'STL'
    assert lineup['teams'][0]['offense'][0]['player_name'] == 'Historic Tackle'
    assert lineup['join_match_rate'] == 0
    response = client.get('/api/games/historical/lineup')
    assert response.status_code == 200 and response.json() == _http_lineup(lineup)


def test_known_game_without_snaps_stays_valid_with_null_match_rate(client, joined_players):
    joined_players.execute('DELETE FROM snap_counts')
    lineup = game_lineup.get_game_lineup(GAME_ID)
    assert lineup['join_match_rate'] is None
    assert all(team['offense'] == team['defense'] == team['rotation'] == [] for team in lineup['teams'])
    assert all(team['avg_rating'] is None for team in lineup['teams'])
    assert len(lineup['scoring']) == 3
    response = client.get(f'/api/games/{GAME_ID}/lineup')
    assert response.status_code == 200 and response.json() == _http_lineup(lineup)


@pytest.mark.parametrize('game_id', ['missing', '2024_01_MIA_BUF'])
def test_missing_game_preserves_404_and_short_circuits(client, league, monkeypatch, game_id):
    original = game_lineup.query_to_dict
    calls = []
    def schedule_only(sql, params):
        calls.append(params)
        assert len(params) == 1
        return original(sql, params)
    def unexpected_builder(*args):
        pytest.fail('missing game reached a builder')
    monkeypatch.setattr(game_lineup, 'query_to_dict', schedule_only)
    monkeypatch.setattr(game_lineup.game_ratings_builder, 'read_or_materialize', unexpected_builder)
    monkeypatch.setattr(game_lineup.ol_grades_builder, 'read_or_materialize', unexpected_builder)
    assert game_lineup.get_game_lineup(game_id) is None
    response = client.get(f'/api/games/{game_id}/lineup')
    assert response.status_code == 404 and response.json() == {'detail': f'Game {game_id} not found'}
    assert calls == [[game_id], [game_id]]


def test_scoring_query_failure_keeps_logged_empty_fallback(client, joined_players, caplog):
    joined_players.execute('DROP TABLE player_game_stats')
    lineup = game_lineup.get_game_lineup(GAME_ID)
    assert lineup['scoring'] == [] and lineup['teams'][0]['offense']
    assert 'safe_query failed, returning []' in caplog.text
    response = client.get(f'/api/games/{GAME_ID}/lineup')
    assert response.status_code == 200 and response.json() == _http_lineup(lineup)


@pytest.mark.parametrize('stage', [1, 2])
def test_required_query_errors_propagate(client, joined_players, monkeypatch, stage):
    original = game_lineup.query_to_dict
    for action in [lambda: game_lineup.get_game_lineup(GAME_ID), lambda: client.get(f'/api/games/{GAME_ID}/lineup')]:
        calls = []
        def fail_at(sql, params):
            calls.append(sql)
            if len(calls) == stage:
                raise RuntimeError('lineup storage failed')
            return original(sql, params)
        monkeypatch.setattr(game_lineup, 'query_to_dict', fail_at)
        with pytest.raises(RuntimeError, match='lineup storage failed'):
            action()


def test_missing_plays_table_is_a_required_snap_join_error(client, joined_players):
    joined_players.execute('DROP TABLE plays')
    with pytest.raises(duckdb.CatalogException):
        game_lineup.get_game_lineup(GAME_ID)
    with pytest.raises(duckdb.CatalogException):
        client.get(f'/api/games/{GAME_ID}/lineup')


@pytest.mark.parametrize('builder', ['game_ratings_builder', 'ol_grades_builder'])
def test_uncaught_builder_errors_propagate(client, joined_players, monkeypatch, builder):
    def fail(*args):
        raise RuntimeError('lineup builder failed')
    monkeypatch.setattr(getattr(game_lineup, builder), 'read_or_materialize', fail)
    with pytest.raises(RuntimeError, match='lineup builder failed'):
        game_lineup.get_game_lineup(GAME_ID)
    with pytest.raises(RuntimeError, match='lineup builder failed'):
        client.get(f'/api/games/{GAME_ID}/lineup')
