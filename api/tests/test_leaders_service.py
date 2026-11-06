"""Offline checks for season totals and their HTTP/assistant consumers."""
import json

import duckdb
import pytest

from services import leaders
from sql_helpers import STAT_COLS


@pytest.fixture
def leaders_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('CREATE TABLE schedules (game_id VARCHAR, game_type VARCHAR)')
        conn.execute('''CREATE TABLE rosters (
            player_id VARCHAR, season INTEGER, week INTEGER, team VARCHAR,
            position VARCHAR, jersey_number INTEGER, headshot_url VARCHAR
        )''')
        stat_columns = ', '.join(f'{column} DOUBLE DEFAULT 0' for column in STAT_COLS)
        conn.execute(f'''CREATE TABLE player_game_stats (
            player_id VARCHAR, player_name VARCHAR, game_id VARCHAR, season INTEGER,
            {stat_columns}
        )''')
        conn.execute('''INSERT INTO schedules VALUES
            ('reg-1', 'REG'), ('reg-2', 'REG'), ('playoff', 'POST'),
            ('preseason', 'PRE'), ('old-season', 'REG')
        ''')
        conn.execute('''INSERT INTO rosters VALUES
            ('known', 2024, 1, 'BUF', 'QB', 1, 'old.png'),
            ('known', 2024, 4, 'SEA', 'QB', 1, 'tie.png'),
            ('known', 2024, 4, 'NYJ', 'QB', 1, 'latest.png'),
            ('known', 2024, NULL, 'ARI', 'QB', 1, 'undated.png'),
            ('known', 2025, 99, 'LAC', 'QB', 1, 'other-season.png')
        ''')
        conn.execute('''INSERT INTO player_game_stats
            (player_id, player_name, game_id, season, pass_yards, pass_tds, pass_epa)
            VALUES
            ('known', 'Known Player', 'reg-1', 2024, 100, 1, 1.5),
            ('known', 'Known Player', 'reg-1', 2024, 25, 0, 0.25),
            ('known', 'Known Player', 'reg-2', 2024, 25, 1, 0.25),
            ('known', 'Known Player', 'playoff', 2024, 2000, 20, 100),
            ('known', 'Known Player', 'preseason', 2024, 1000, 10, 50),
            ('known', 'Known Player', 'no-schedule', 2024, 500, 5, 25),
            ('known', 'Known Player', 'old-season', 2023, 200, 2, 10),
            ('missing', 'Missing Roster', 'reg-1', 2024, 80, 1, 0.5)
        ''')
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def test_http_and_service_preserve_seeded_season_totals(client):
    expected = {row['player_id']: row for row in leaders.get_leaders(2024)}
    response = client.get('/api/leaders?season=2024')
    assert response.status_code == 200
    assert {row['player_id']: row for row in response.json()} == expected
    allen = expected['00-BUF-QB1']
    assert allen['pass_yards'] == 880
    assert allen['games_played'] == 3


def test_regular_season_totals_use_distinct_games_and_one_season_roster(client, leaders_data):
    rows = {row['player_id']: row for row in leaders.get_leaders(2024)}
    assert set(rows) == {'known', 'missing'}
    known = rows['known']
    assert (known['pass_yards'], known['pass_tds'], known['pass_epa'], known['games_played']) == (150, 2, 2, 2)
    assert (known['team'], known['position'], known['headshot_url']) == ('NYJ', 'QB', 'latest.png')
    assert rows['missing']['pass_yards'] == 80
    assert (rows['missing']['team'], rows['missing']['position'], rows['missing']['headshot_url']) == (None, None, None)
    response = client.get('/api/leaders?season=2024')
    assert response.status_code == 200
    assert {row['player_id']: row for row in response.json()} == rows


@pytest.mark.parametrize(('limit', 'clamped'), [(0, 1), (1, 1), (100, 25)])
def test_assistant_ranks_shared_totals_and_keeps_limits_and_provenance(leaders_data, limit, clamped):
    import llm

    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_leaders')
    raw = tool.func(stat=' PASS_YARDS ', season=2024, limit=limit)
    expected = [
        {'rank': 1, 'player': 'Known Player', 'team': 'NYJ', 'position': 'QB', 'pass_yards': 150, 'games_played': 2},
        {'rank': 2, 'player': 'Missing Roster', 'team': None, 'position': None, 'pass_yards': 80, 'games_played': 1},
    ][:clamped]
    assert json.loads(raw) == expected
    assert ctx.calls == [{'tool': 'get_leaders', 'args': {'stat': 'pass_yards', 'season': 2024, 'limit': clamped}}]
    assert ctx.data == expected
    assert ctx.raw_results == [raw]


def test_default_season_invalid_http_input_and_explicit_empty_year(client, monkeypatch):
    import llm

    monkeypatch.setattr(leaders, 'CURRENT_SEASON', 2024)
    expected = {row['player_id']: row for row in leaders.get_leaders(2024)}
    assert {row['player_id']: row for row in leaders.get_leaders()} == expected
    assert {row['player_id']: row for row in leaders.get_leaders(None)} == expected
    assert {row['player_id']: row for row in client.get('/api/leaders').json()} == expected
    assert leaders.get_leaders(0) == []
    assert client.get('/api/leaders?season=0').json() == []
    assert client.get('/api/leaders?season=banana').status_code == 422
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_leaders')
    assert tool.func(stat='pass_yards', season=0) == 'No leaders found for pass_yards in 0.'


def test_invalid_assistant_stat_is_rejected_before_querying(monkeypatch):
    import llm

    def unexpected_query(*args, **kwargs):
        pytest.fail('an invalid stat reached the leaders query')

    monkeypatch.setattr(llm, '_leaders_query', unexpected_query)
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_leaders')
    assert tool.func(stat='not_a_stat', season=2024).startswith("Invalid stat 'not_a_stat'.")
    assert ctx.calls == [{'tool': 'get_leaders', 'args': {'stat': 'not_a_stat', 'season': 2024, 'limit': 10}}]


def test_query_failure_propagates_instead_of_becoming_empty_data(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('leaders storage failed')

    monkeypatch.setattr(leaders, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='leaders storage failed'):
        leaders.get_leaders(2024)
