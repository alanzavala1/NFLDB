"""Offline schedule listing and its HTTP/assistant consumers."""
import json

import duckdb
import pytest

from services import schedule


@pytest.fixture
def schedule_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE schedules (
            game_id VARCHAR, season INTEGER, game_type VARCHAR, week INTEGER,
            gameday VARCHAR, gametime VARCHAR, away_team VARCHAR, home_team VARCHAR,
            away_score INTEGER, home_score INTEGER, away_qb_name VARCHAR, home_qb_name VARCHAR,
            spread_line DOUBLE, total_line DOUBLE, roof VARCHAR, surface VARCHAR,
            temp INTEGER, wind INTEGER, stadium VARCHAR, overtime INTEGER, div_game INTEGER,
            away_coach VARCHAR, home_coach VARCHAR
        )''')
        conn.executemany('''INSERT INTO schedules
            (game_id, season, game_type, week, gameday, gametime, away_team, home_team,
             away_score, home_score, overtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', [
            ('late', 2024, 'REG', 1, '2024-09-08', '16:25', 'KC', 'BUF', 21, 21, 1),
            ('pre', 2024, 'PRE', 0, None, '19:00', 'BUF', 'NE', 7, 0, 0),
            ('post', 2024, 'WC', 19, None, '20:00', 'BUF', 'KC', 20, 24, 0),
            ('early', 2024, 'REG', 1, '2024-09-08', '13:00', 'MIA', 'DEN', 24, 14, 0),
            ('future', 2024, 'REG', 2, None, '13:00', 'BUF', 'MIA', None, None, None),
            ('other-season', 2023, 'REG', 1, None, '13:00', 'BUF', 'MIA', 7, 0, 0),
        ])
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def _tool(name):
    import llm

    ctx = llm._Ctx()
    return ctx, next(tool for tool in llm._build_tools(ctx) if tool.name == name)


def test_seeded_listing_matches_http(client):
    groups = schedule.get_schedule(2024)
    response = client.get('/api/schedule?season=2024')
    assert response.status_code == 200
    assert response.json() == groups
    assert [group['week'] for group in groups] == [1, 2, 3]


def test_grouping_kickoff_order_game_types_records_and_nullable_fields(client, schedule_data):
    groups = schedule.get_schedule(2024)
    assert [group['week'] for group in groups] == [0, 1, 2, 19]
    assert [game['game_id'] for game in groups[1]['games']] == ['early', 'late']
    assert groups[0]['games'][0]['game_type'] == 'PRE'
    assert groups[-1]['games'][0]['game_type'] == 'WC'
    assert groups[1]['games'][1]['home_record'] == '1-0'
    future = groups[2]['games'][0]
    assert (future['away_record'], future['home_record']) == ('1-0-1', '1-0')
    assert future['away_score'] is None and future['home_score'] is None
    assert future['away_coach'] is None
    response = client.get('/api/schedule?season=2024')
    assert response.status_code == 200
    assert response.json() == groups


def test_assistant_filter_projection_overtime_and_provenance(schedule_data):
    ctx, tool = _tool('find_games')
    raw = tool.func(season=2024, team=' buf ', week=1)
    result = json.loads(raw)
    assert result['matched'] == 1 and result['truncated'] is False
    assert result['games'] == [{
        'game_id': 'late', 'week': 1, 'game_type': 'REG', 'gameday': '2024-09-08',
        'away_team': 'KC', 'home_team': 'BUF', 'away_score': 21, 'home_score': 21, 'overtime': True,
    }]
    assert ctx.calls == [{'tool': 'find_games', 'args': {'season': 2024, 'team': 'BUF', 'week': 1}}]
    assert ctx.data == result['games']
    assert ctx.raw_results == [raw]


def test_capped_assistant_preview_keeps_nonregular_games_discoverable(schedule_data):
    schedule_data.executemany('''INSERT INTO schedules
        (game_id, season, game_type, week, gametime, away_team, home_team, away_score, home_score)
        VALUES (?, 2024, 'REG', ?, '13:00', 'BUF', 'MIA', 7, 0)''', [
        (f'cap-{i}', i % 17 + 1) for i in range(30)
    ])
    _, tool = _tool('find_games')
    result = json.loads(tool.func(season=2024))
    assert result['matched'] == 35 and result['truncated'] is True
    assert len(result['games']) == 25
    assert [row['game_id'] for row in result['games'][:2]] == ['pre', 'post']
    assert all('gameday' not in row and 'overtime' not in row for row in result['games'])
    assert 'Showing 25 compact results' in result['note']


def test_team_overview_fallback_uses_shared_schedule_game_types(schedule_data, monkeypatch):
    import llm

    monkeypatch.setattr(llm, 'CURRENT_SEASON', 2026)
    monkeypatch.setattr(llm, '_standings_query', lambda season: [])
    monkeypatch.setattr(llm, '_team_query', lambda team, season: {'games': [
        {'game_id': 'pre', 'away_team': 'BUF', 'home_team': 'NE', 'away_score': 7, 'home_score': 0},
        {'game_id': 'late', 'away_team': 'KC', 'home_team': 'BUF', 'away_score': 21, 'home_score': 21},
        {'game_id': 'post', 'away_team': 'BUF', 'home_team': 'KC', 'away_score': 20, 'home_score': 24},
    ]})
    _, tool = _tool('get_team_overview')
    result = json.loads(tool.func(team='BUF', season=2024))
    assert result['record'] == '0-0-1'


def test_empty_year_keeps_http_success_and_assistant_no_match_message(client, schedule_data):
    assert schedule.get_schedule(0) == []
    response = client.get('/api/schedule?season=0')
    assert response.status_code == 200 and response.json() == []
    ctx, tool = _tool('find_games')
    raw = tool.func(season=0)
    assert raw == 'No games found for those filters in 0.'
    assert ctx.calls == [{'tool': 'find_games', 'args': {'season': 0, 'team': '', 'week': 0}}]
    assert ctx.raw_results == [raw]


def test_http_omitted_season_passes_configured_default(client, monkeypatch):
    import config
    import routers.schedule

    calls = []
    def empty(season):
        calls.append(season)
        return []
    monkeypatch.setattr(routers.schedule, 'query_schedule', empty)
    response = client.get('/api/schedule')
    assert response.status_code == 200 and response.json() == []
    assert calls == [config.CURRENT_SEASON]


def test_invalid_http_season_stops_before_querying(client, monkeypatch):
    def unexpected_query(*args, **kwargs):
        pytest.fail('invalid HTTP input reached the schedule query')
    monkeypatch.setattr(schedule, 'query_to_dict', unexpected_query)
    assert client.get('/api/schedule?season=banana').status_code == 422


def test_query_failures_propagate_through_service_http_and_assistant(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('schedule storage failed')
    monkeypatch.setattr(schedule, 'query_to_dict', fail)
    _, tool = _tool('find_games')
    for action in [
        lambda: schedule.get_schedule(2024),
        lambda: client.get('/api/schedule?season=2024'),
        lambda: tool.func(season=2024),
    ]:
        with pytest.raises(RuntimeError, match='schedule storage failed'):
            action()
