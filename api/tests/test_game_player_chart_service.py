"""Offline chart statistics, roles/events and two HTTP missing-data mappings."""
import duckdb
import pytest

import game_ratings_builder
from schemas.lineup import PlayerChart
from services import game_player_chart
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
def chart_data(league, monkeypatch):
    for table in ('rosters', 'snap_counts', 'player_game_stats', 'plays'):
        league.execute(f'DELETE FROM {table}')
    game_ratings_builder.ensure_table(league)
    league.executemany('''INSERT INTO rosters
        (player_id, player_name, season, week, team, position, pfr_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)''', [
        ('mixed', 'Old Roster Name', 2024, 1, 'BUF', 'WR', 'old-pfr'),
        ('mixed', 'Latest Roster Name', 2024, 8, 'NYJ', 'RB', 'latest-pfr'),
        ('mixed', 'Wrong Year', 2025, 99, 'SEA', 'TE', 'wrong-year'),
        ('defender', 'Roster Defender', 2024, 1, 'BUF', 'DE', 'def-pfr'),
        ('kicker', 'Roster Kicker', 2024, 1, 'BUF', 'K', None),
        ('roster-only', 'Unused Quarterback', 2024, 1, 'NE', 'QB', None),
    ])
    league.executemany('''INSERT INTO player_game_stats
        (player_id, player_name, game_id, season, week, team, attempts, completions,
         pass_yards, targets, receptions, rec_yards, carries, rush_yards,
         pass_epa, rush_epa, solo_tackles, assist_tackles, sacks, def_interceptions)
        VALUES ('mixed', 'Stats Mixed', ?, 2024, 1, 'BUF', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', [
        (GAME_ID, 2, 1, 100, 2, 1, 10, 1, 4, -1, -0.25, 1, 1, 1, 1),
        (GAME_ID, 2, 2, 50, 1, 1, 20, 1, 6, 0.5, 0.5, 2, 2, 0.5, 0),
        ('other-game', 99, 99, 9999, 99, 99, 9999, 99, 9999, 99, 99, 99, 99, 99, 99),
    ])
    league.execute('''INSERT INTO player_game_stats
        (player_id, player_name, game_id, season, week, team, pass_yards)
        VALUES ('stats-only', 'Stats Only', '2024_01_BUF_MIA', 2024, 1, 'MIA', 7)''')
    league.execute('''INSERT INTO player_game_ratings
        (player_id, game_id, season, week, team, position_group, rating)
        VALUES ('mixed', '2024_01_BUF_MIA', 2024, 1, 'BUF', 'QB', 8.4)''')
    league.executemany('''INSERT INTO snap_counts
        (game_id, season, pfr_player_id, team, offense_pct, defense_pct, st_pct)
        VALUES (?, 2024, ?, 'BUF', ?, ?, ?)''', [
        (GAME_ID, 'old-pfr', 0.2, 0.65, 0.9),
        (GAME_ID, 'latest-pfr', 1, 0, 0),
        ('other-game', 'old-pfr', 1, 1, 1),
    ])
    plays = [
        dict(play_id=1, seconds=3500, receiver_player_id='mixed', pass_location='left',
             air_yards=10, receiving_yards=12, complete_pass=1, epa=0.1),
        dict(play_id=2, seconds=3000, receiver_player_id='mixed', pass_location='right',
             air_yards=18, receiving_yards=20, touchdown=1, epa=1),
        dict(play_id=3, seconds=2000, passer_player_id='mixed', pass_location='right',
             air_yards=9, passing_yards=15, complete_pass=1, epa=0.5),
        dict(play_id=4, seconds=1000, passer_player_id='mixed', passing_yards=0, interception=1),
        dict(play_id=5, seconds=500, rusher_player_id='mixed', run_location='left',
             run_gap='tackle', rushing_yards=8, touchdown=1, epa=1.2),
        dict(play_id=6, seconds=400, rusher_player_id='mixed', run_location='middle',
             rushing_yards=-2, fumble_lost=1, epa=-0.8),
    ]
    for play in plays:
        row = {'game_id': GAME_ID, 'qtr': 1, 'game_seconds_remaining': play.pop('seconds'), **play}
        names = ', '.join(f'"{name}"' for name in row)
        placeholders = ', '.join('?' for _ in row)
        league.execute(f'INSERT INTO plays ({names}) VALUES ({placeholders})', list(row.values()))
    league.execute('''INSERT INTO plays (game_id, play_id, game_seconds_remaining, passer_player_id)
        VALUES ('other-game', 999, 9999, 'mixed')''')
    monkeypatch.setattr(game_player_chart.game_ratings_builder, 'read_or_materialize', lambda game_id: [{}])
    return league


def _http_chart(chart):
    return PlayerChart.model_validate(chart).model_dump(mode='json')


def test_seeded_chart_matches_http_and_real_lazy_ratings(client, league):
    chart = game_player_chart.get_game_player_chart('2024_01_DEN_KC', '00-KC-OFF3')
    assert chart['role'] == 'receiver' and chart['snap_pct'] == 1
    assert chart['events'][0]['outcome'] == 'TD'
    assert league.execute('SELECT COUNT(*) FROM player_game_ratings').fetchone()[0] > 0
    response = client.get('/api/games/2024_01_DEN_KC/players/00-KC-OFF3/chart')
    assert response.status_code == 200 and response.json() == _http_chart(chart)


def test_stat_aggregation_metadata_snap_priority_and_http_parity(client, chart_data):
    chart = game_player_chart.get_game_player_chart(GAME_ID, 'mixed')
    assert (chart['player_name'], chart['team'], chart['position'], chart['rating']) == ('Stats Mixed', 'BUF', 'RB', 8.4)
    assert chart['snap_pct'] == 0.9
    assert chart['stats'] == {
        'attempts': 4, 'completions': 3, 'pass_yards': 150, 'pass_tds': 0,
        'interceptions_thrown': 0, 'targets': 3, 'receptions': 2, 'rec_yards': 30,
        'rec_tds': 0, 'carries': 2, 'rush_yards': 10, 'rush_tds': 0,
        'pass_epa': -0.5, 'rec_epa': 0, 'rush_epa': 0.25, 'sacks': 1.5,
        'tackles': 6, 'def_interceptions': 1,
    }
    response = client.get(f'/api/games/{GAME_ID}/players/mixed/chart')
    assert response.status_code == 200 and response.json() == _http_chart(chart)


def test_play_count_ties_event_roles_lanes_yards_and_outcomes(chart_data):
    chart = game_player_chart.get_game_player_chart(GAME_ID, 'mixed')
    assert chart['role'] == 'passer'  # two pass, two target and two rush plays
    events = chart['events']
    assert [event['play_id'] for event in events] == [1, 2, 3, 4, 5, 6]
    assert [event['role'] for event in events] == ['receiver', 'receiver', 'passer', 'passer', 'rusher', 'rusher']
    assert [event['outcome'] for event in events] == ['Complete', 'TD', 'Complete', 'INT', 'TD', 'FUM']
    assert [event['yards'] for event in events] == [12, 20, 15, 0, 8, -2]
    assert events[4]['lane'] == 'left tackle' and events[5]['lane'] == 'middle'
    assert events[3]['lane'] is None and events[3]['air_yards'] is None


def test_role_uses_all_plays_and_null_time_event_sorts_last(chart_data):
    chart_data.execute('''INSERT INTO plays (game_id, play_id, qtr, receiver_player_id)
        VALUES ('2024_01_BUF_MIA', 7, 1, 'mixed')''')
    chart = game_player_chart.get_game_player_chart(GAME_ID, 'mixed')
    assert chart['role'] == 'receiver'
    assert chart['events'][-1]['play_id'] == 7
    assert chart['events'][-1]['outcome'] == 'Incomplete'


def test_event_cap_retains_chronological_order_and_play_id_tiebreaker(chart_data):
    chart_data.executemany('''INSERT INTO plays
        (game_id, play_id, qtr, game_seconds_remaining, passer_player_id)
        VALUES ('2024_01_BUF_MIA', ?, 1, 100, 'mixed')''', [(i,) for i in range(100, 190)])
    chart = game_player_chart.get_game_player_chart(GAME_ID, 'mixed')
    assert chart['role'] == 'passer' and len(chart['events']) == 80
    assert [event['play_id'] for event in chart['events'][:6]] == [1, 2, 3, 4, 5, 6]
    assert [event['play_id'] for event in chart['events'][6:]] == list(range(100, 174))


@pytest.mark.parametrize(('player_id', 'role', 'name', 'position'), [
    ('defender', 'defender', 'Roster Defender', 'DE'),
    ('kicker', 'kicker', 'Roster Kicker', 'K'),
    ('roster-only', 'player', 'Unused Quarterback', 'QB'),
    ('stats-only', 'player', 'Stats Only', None),
])
def test_roster_only_or_stats_only_profile_stays_valid_with_no_events(client, chart_data, player_id, role, name, position):
    chart = game_player_chart.get_game_player_chart(GAME_ID, player_id)
    assert (chart['role'], chart['player_name'], chart['position']) == (role, name, position)
    assert chart['events'] == [] and chart['rating'] is None and chart['snap_pct'] is None
    assert chart['stats']['pass_yards'] == (7 if player_id == 'stats-only' else 0)
    response = client.get(f'/api/games/{GAME_ID}/players/{player_id}/chart')
    assert response.status_code == 200 and response.json() == _http_chart(chart)


def test_missing_game_error_short_circuits_builder_and_keeps_http_message(client, league, monkeypatch):
    def unexpected_builder(*args):
        pytest.fail('missing game reached the ratings builder')
    monkeypatch.setattr(game_player_chart.game_ratings_builder, 'read_or_materialize', unexpected_builder)
    with pytest.raises(game_player_chart.GameNotFoundError):
        game_player_chart.get_game_player_chart('missing', 'mixed')
    response = client.get('/api/games/missing/players/mixed/chart')
    assert response.status_code == 404 and response.json() == {'detail': 'Game missing not found'}


def test_missing_player_error_stops_before_play_queries_and_keeps_http_message(client, chart_data, monkeypatch):
    original = game_player_chart.query_to_dict
    calls = []
    def profile_only(sql, params):
        calls.append(sql)
        assert 'FROM plays' not in sql
        return original(sql, params)
    monkeypatch.setattr(game_player_chart, 'query_to_dict', profile_only)
    with pytest.raises(game_player_chart.PlayerNotFoundError):
        game_player_chart.get_game_player_chart(GAME_ID, 'missing')
    response = client.get(f'/api/games/{GAME_ID}/players/missing/chart')
    assert response.status_code == 404
    assert response.json() == {'detail': f'Player missing not found for game {GAME_ID}'}
    assert len(calls) == 4


def test_missing_snap_table_keeps_logged_nullable_fallback(client, chart_data, caplog):
    chart_data.execute('DROP TABLE snap_counts')
    chart = game_player_chart.get_game_player_chart(GAME_ID, 'mixed')
    assert chart['snap_pct'] is None and len(chart['events']) == 6
    assert 'safe_query failed, returning []' in caplog.text
    response = client.get(f'/api/games/{GAME_ID}/players/mixed/chart')
    assert response.status_code == 200 and response.json() == _http_chart(chart)


@pytest.mark.parametrize('stage', [1, 2, 3, 4])
def test_required_query_failures_propagate(client, chart_data, monkeypatch, stage):
    original = game_player_chart.query_to_dict
    for action in [
        lambda: game_player_chart.get_game_player_chart(GAME_ID, 'mixed'),
        lambda: client.get(f'/api/games/{GAME_ID}/players/mixed/chart'),
    ]:
        calls = []
        def fail_at(sql, params):
            calls.append(sql)
            if len(calls) == stage:
                raise RuntimeError('chart storage failed')
            return original(sql, params)
        monkeypatch.setattr(game_player_chart, 'query_to_dict', fail_at)
        with pytest.raises(RuntimeError, match='chart storage failed'):
            action()


def test_uncaught_builder_error_propagates(client, chart_data, monkeypatch):
    def fail(*args):
        raise RuntimeError('chart builder failed')
    monkeypatch.setattr(game_player_chart.game_ratings_builder, 'read_or_materialize', fail)
    with pytest.raises(RuntimeError, match='chart builder failed'):
        game_player_chart.get_game_player_chart(GAME_ID, 'mixed')
    with pytest.raises(RuntimeError, match='chart builder failed'):
        client.get(f'/api/games/{GAME_ID}/players/mixed/chart')
