"""Offline profile assembly and missing-data mapping for HTTP and Ask."""
import json

import duckdb
import pytest

from services import team_profile
from sql_helpers import STAT_COLS


def _ordered_leaders(profile):
    # GROUP BY leader queries have no row-order contract; schedule order is kept.
    return {
        **profile,
        'leaders': sorted(profile['leaders'], key=lambda row: row['player_id']),
        'playoff_leaders': sorted(profile['playoff_leaders'], key=lambda row: row['player_id']),
    }


@pytest.fixture
def profile_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE schedules (
            game_id VARCHAR, season INTEGER, game_type VARCHAR, week INTEGER,
            gameday VARCHAR, gametime VARCHAR, away_team VARCHAR, home_team VARCHAR,
            away_score INTEGER, home_score INTEGER, stadium VARCHAR, roof VARCHAR,
            surface VARCHAR, temp INTEGER, wind INTEGER
        )''')
        conn.executemany('''INSERT INTO schedules
            (game_id, season, game_type, week, away_team, home_team, away_score, home_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', [
            ('pre', 2024, 'PRE', 0, 'BUF', 'MIA', 7, 0),
            ('reg1', 2024, 'REG', 1, 'BUF', 'MIA', 14, 7),
            ('reg2', 2024, 'REG', 2, 'KC', 'BUF', 21, 21),
            ('future', 2024, 'REG', 3, 'BUF', 'DEN', None, None),
            ('post', 2024, 'POST', 19, 'BUF', 'SF', 10, 20),
            ('old', 2023, 'REG', 1, 'BUF', 'NE', 4, 0),
            ('other', 2024, 'REG', 1, 'MIA', 'SF', 9, 0),
        ])
        conn.execute('''CREATE TABLE rosters (
            player_id VARCHAR, season INTEGER, week INTEGER, team VARCHAR,
            position VARCHAR, jersey_number INTEGER, headshot_url VARCHAR
        )''')
        conn.execute('''INSERT INTO rosters VALUES
            ('known', 2024, 1, 'BUF', 'QB', 7, 'old.png'),
            ('known', 2024, 4, 'NYJ', 'QB', 9, 'latest.png'),
            ('known', 2024, 4, 'SEA', 'QB', 99, 'tie.png'),
            ('known', 2025, 99, 'LAC', 'WR', 10, 'future.png')
        ''')
        columns = ', '.join(f'{column} DOUBLE DEFAULT 0' for column in STAT_COLS)
        conn.execute(f'''CREATE TABLE player_game_stats (
            player_id VARCHAR, player_name VARCHAR, game_id VARCHAR, season INTEGER,
            team VARCHAR, {columns}
        )''')
        conn.executemany('''INSERT INTO player_game_stats
            (player_id, player_name, game_id, season, team, pass_yards, pass_tds)
            VALUES (?, ?, ?, ?, ?, ?, ?)''', [
            ('known', 'Short', 'pre', 2024, 'BUF', 100, 1),
            ('known', 'Longer Player Name', 'reg1', 2024, 'BUF', 100, 1),
            ('known', 'Short', 'reg1', 2024, 'BUF', 25, 0),
            ('known', 'Short', 'reg2', 2024, 'BUF', 50, 1),
            ('missing', 'Missing Roster', 'reg1', 2024, 'BUF', 40, 0),
            ('known', 'Short', 'post', 2024, 'BUF', 200, 2),
            ('known', 'Other Team', 'reg1', 2024, 'MIA', 800, 8),
            ('known', 'Old Season', 'old', 2023, 'BUF', 900, 9),
            ('known', 'No Schedule', 'orphan', 2024, 'BUF', 600, 6),
        ])
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def _overview(monkeypatch):
    import llm

    monkeypatch.setattr(llm, 'CURRENT_SEASON', 2024)
    monkeypatch.setattr(llm, '_team_depth_query', lambda *args: [])
    monkeypatch.setattr(llm, '_team_injuries_query', lambda *args: [])
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_team_overview')
    return ctx, tool


def test_seeded_profile_and_http_match(client):
    profile = team_profile.get_team_profile('BUF', 2024)
    response = client.get('/api/teams/BUF?season=2024')
    assert response.status_code == 200
    assert _ordered_leaders(response.json()) == _ordered_leaders(profile)
    assert len(profile['games']) == 3
    assert next(row for row in profile['leaders'] if row['player_name'] == 'Josh Allen')['pass_yards'] == 880


def test_profile_keeps_schedule_history_and_separate_leader_buckets(client, profile_data):
    profile = team_profile.get_team_profile('BUF', 2024)
    assert [game['game_id'] for game in profile['games']] == ['pre', 'reg1', 'reg2', 'future', 'post']
    assert [game['game_type'] for game in profile['games']] == ['PRE', 'REG', 'REG', 'REG', 'POST']
    # Existing annotation scope includes the supplied preseason result.
    assert profile['games'][1]['away_record'] == '1-0'
    assert profile['games'][3]['away_record'] == '2-0-1'
    regular = {row['player_id']: row for row in profile['leaders']}
    assert set(regular) == {'known', 'missing'}
    known = regular['known']
    assert (known['pass_yards'], known['pass_tds'], known['games_played']) == (175, 2, 2)
    assert (known['player_name'], known['jersey_number'], known['headshot_url']) == ('Longer Player Name', 9, 'latest.png')
    assert regular['missing']['position'] is None
    assert regular['missing']['jersey_number'] is None
    assert regular['missing']['headshot_url'] is None
    assert len(profile['playoff_leaders']) == 1
    non_regular = profile['playoff_leaders'][0]
    assert (non_regular['pass_yards'], non_regular['pass_tds'], non_regular['games_played']) == (300, 3, 2)
    response = client.get('/api/teams/BUF?season=2024')
    assert response.status_code == 200
    assert _ordered_leaders(response.json()) == _ordered_leaders(profile)


def test_assistant_uses_shared_profile_with_regular_standing_and_provenance(profile_data, monkeypatch):
    ctx, tool = _overview(monkeypatch)
    raw = tool.func(team=' buf ', season=2024)
    result = json.loads(raw)
    assert (result['team'], result['season'], result['record'], result['regular_season_games']) == ('BUF', 2024, '1-0-1', 2)
    assert result['standing']['pct'] == 0.75
    assert ctx.calls == [{'tool': 'get_team_overview', 'args': {'team': 'BUF', 'season': 2024}}]
    assert ctx.data == [result]
    assert ctx.raw_results == [raw]


@pytest.mark.parametrize(('team', 'season'), [('ZZZ', 2024), ('BUF', 0)])
def test_domain_absence_preserves_http_404_and_assistant_message(client, profile_data, monkeypatch, team, season):
    assert team_profile.get_team_profile(team, season) is None
    response = client.get(f'/api/teams/{team}', params={'season': season})
    assert response.status_code == 404
    assert response.json() == {'detail': f'No games found for {team} in {season}'}
    ctx, tool = _overview(monkeypatch)
    raw = tool.func(team=team, season=season)
    assert raw == f'No team profile found for {team} in {season}.'
    assert ctx.calls == [{'tool': 'get_team_overview', 'args': {'team': team, 'season': season}}]
    assert ctx.data == []
    assert ctx.raw_results == [raw]


def test_http_default_season_keeps_profile_selection(client, monkeypatch):
    import config
    import routers.teams

    calls = []
    def missing(team, season):
        calls.append((team, season))
        return None
    monkeypatch.setattr(routers.teams, 'query_team_profile', missing)
    response = client.get('/api/teams/BUF')
    assert calls == [('BUF', config.CURRENT_SEASON)]
    assert response.status_code == 404
    assert response.json() == {'detail': f'No games found for BUF in {config.CURRENT_SEASON}'}


def test_scheduled_games_with_no_player_stats_are_a_valid_profile(client, profile_data):
    profile_data.execute('''INSERT INTO schedules
        (game_id, season, game_type, week, away_team, home_team)
        VALUES ('scheduled-only', 2024, 'REG', 4, 'CHI', 'GB')''')
    profile = team_profile.get_team_profile('CHI', 2024)
    assert len(profile['games']) == 1
    assert profile['games'][0]['away_score'] is None
    assert profile['games'][0]['away_record'] == '0-0'
    assert profile['leaders'] == profile['playoff_leaders'] == []
    response = client.get('/api/teams/CHI?season=2024')
    assert response.status_code == 200
    assert response.json() == profile


def test_missing_schedule_stops_before_leader_queries(monkeypatch):
    calls = []
    def empty(sql, params):
        calls.append(params)
        assert len(calls) == 1
        return []
    monkeypatch.setattr(team_profile, 'query_to_dict', empty)
    assert team_profile.get_team_profile('ZZZ', 2024) is None
    assert calls == [[2024, 'ZZZ', 'ZZZ']]


def test_invalid_http_season_is_rejected_before_querying(client, monkeypatch):
    def unexpected_query(*args, **kwargs):
        pytest.fail('invalid HTTP input reached the profile query')
    monkeypatch.setattr(team_profile, 'query_to_dict', unexpected_query)
    assert client.get('/api/teams/BUF?season=banana').status_code == 422


@pytest.mark.parametrize('stage', [1, 2, 3])
def test_profile_query_failures_propagate_at_each_consumer(client, profile_data, monkeypatch, stage):
    original = team_profile.query_to_dict
    _, tool = _overview(monkeypatch)
    actions = [
        lambda: team_profile.get_team_profile('BUF', 2024),
        lambda: client.get('/api/teams/BUF?season=2024'),
        lambda: tool.func(team='BUF', season=2024),
    ]
    for action in actions:
        calls = []
        def fail_at(sql, params):
            calls.append(sql)
            if len(calls) == stage:
                raise RuntimeError('profile storage failed')
            return original(sql, params)
        monkeypatch.setattr(team_profile, 'query_to_dict', fail_at)
        with pytest.raises(RuntimeError, match='profile storage failed'):
            action()
