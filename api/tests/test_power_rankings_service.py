"""Offline checks for ranking response assembly and its two consumers."""
import json

import duckdb
import pytest

from services import power_rankings


@pytest.fixture
def rankings_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE schedules (
            season INTEGER, week INTEGER, game_type VARCHAR, away_team VARCHAR,
            home_team VARCHAR, away_score INTEGER, home_score INTEGER
        )''')
        conn.execute('''INSERT INTO schedules VALUES
            (2024, 1, 'REG', 'BUF', 'MIA', 17, 24),
            (2024, 2, 'REG', 'KC', 'BUF', 21, 21),
            (2024, 3, 'REG', 'BUF', 'DEN', 30, 24),
            (2024, 2, 'REG', 'KC', 'MIA', NULL, NULL),
            (2024, 2, 'REG', 'BUF', 'MIA', 50, NULL),
            (2024, 2, 'PRE', 'MIA', 'BUF', 1000, 0),
            (2024, 2, 'POST', 'MIA', 'BUF', 999, 0),
            (2023, 1, 'REG', 'BUF', 'MIA', 17, 14)
        ''')
        calls = []

        def read(season, week=None):
            calls.append((season, week))
            chosen = week if week is not None else 2
            return [
                {'week': chosen, 'rank': '1', 'team': 'BUF', 'net_epa_play': 0.12, 'movement': 2},
                {'week': chosen, 'rank': '2', 'team': 'MIA', 'net_epa_play': 0.08, 'movement': None},
                {'week': chosen, 'rank': '3', 'team': 'KC', 'net_epa_play': None, 'movement': -1},
                {'week': chosen, 'rank': '4', 'team': 'SEA', 'net_epa_play': 0, 'movement': 0},
            ]

        monkeypatch.setattr(database, '_conn', conn)
        monkeypatch.setattr(power_rankings.power_rankings_builder, 'read_or_materialize', read)
        yield calls


def test_latest_published_week_records_match_http_and_assistant(client, rankings_data):
    import llm

    expected = [
        {'rank': 1, 'team': 'BUF', 'record': '0-1-1', 'net_epa_play': 0.12, 'movement': 2},
        {'rank': 2, 'team': 'MIA', 'record': '1-0', 'net_epa_play': 0.08, 'movement': None},
        {'rank': 3, 'team': 'KC', 'record': '0-0-1', 'net_epa_play': None, 'movement': -1},
        {'rank': 4, 'team': 'SEA', 'record': '0-0', 'net_epa_play': 0, 'movement': 0},
    ]
    assert power_rankings.get_power_rankings(2024) == expected
    response = client.get('/api/power-rankings?season=2024')
    assert response.status_code == 200
    assert response.json() == expected
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_power_rankings')
    raw = tool.func(season=2024, week=0)
    projection = [{key: value for key, value in row.items() if value is not None} for row in expected]
    assert json.loads(raw) == {'season': 2024, 'week': 'latest', 'rankings': projection}
    assert ctx.calls == [{'tool': 'get_power_rankings', 'args': {'season': 2024, 'week': 0}}]
    assert ctx.data == projection
    assert ctx.raw_results == [raw]
    assert rankings_data == [(2024, None)] * 3


@pytest.mark.parametrize(('week', 'buf_record'), [(1, '0-1'), (2, '0-1-1'), (3, '1-1-1')])
def test_explicit_week_limits_records_and_preserves_assistant_week(client, rankings_data, week, buf_record):
    import llm

    rows = power_rankings.get_power_rankings(2024, week)
    assert rows[0]['record'] == buf_record
    assert rows[1]['record'] == '1-0'  # Unfinished, preseason and playoff games do not count.
    response = client.get('/api/power-rankings', params={'season': 2024, 'week': week})
    assert response.status_code == 200
    assert response.json() == rows
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_power_rankings')
    payload = json.loads(tool.func(season=2024, week=week))
    assert payload['week'] == week
    assert payload['rankings'][0]['record'] == buf_record
    assert rankings_data == [(2024, week)] * 3


def test_default_season_and_empty_rankings_do_not_query_schedule(client, monkeypatch):
    import config
    import llm

    calls = []
    def empty(season, week):
        calls.append((season, week))
        return []
    def unexpected_query(*args, **kwargs):
        pytest.fail('empty rankings should not query schedule records')
    monkeypatch.setattr(power_rankings.power_rankings_builder, 'read_or_materialize', empty)
    monkeypatch.setattr(power_rankings, 'query_to_dict', unexpected_query)
    assert power_rankings.get_power_rankings() == []
    assert client.get('/api/power-rankings').json() == []
    assert calls == [(config.CURRENT_SEASON, None)] * 2
    assert client.get('/api/power-rankings?season=0&week=22').json() == []
    assert calls[-1] == (0, 22)
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_power_rankings')
    assert tool.func(season=0) == 'No power rankings available for 0.'


@pytest.mark.parametrize('week', [-1, 0, 23, 'banana'])
def test_http_rejects_invalid_weeks_before_builder_work(client, monkeypatch, week):
    def unexpected_read(*args, **kwargs):
        pytest.fail('invalid HTTP input reached the ranking builder')
    monkeypatch.setattr(power_rankings.power_rankings_builder, 'read_or_materialize', unexpected_read)
    assert client.get('/api/power-rankings', params={'season': 2024, 'week': week}).status_code == 422
    assert client.get('/api/power-rankings?season=banana').status_code == 422


def test_record_query_failures_propagate(client, rankings_data, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('ranking record query failed')
    monkeypatch.setattr(power_rankings, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='ranking record query failed'):
        power_rankings.get_power_rankings(2024)
