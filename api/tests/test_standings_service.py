"""Offline checks for the shared standings query and its two consumers."""
import json

import duckdb
import pytest

from services import standings


def test_http_and_assistant_preserve_the_shared_standings(client):
    import llm

    divisions = standings.get_standings(2024)
    response = client.get('/api/standings?season=2024')
    assert response.status_code == 200
    assert response.json() == divisions
    rows = {row['team']: row for division in divisions for row in division['teams']}
    assert rows['BUF'] == {
        'team': 'BUF', 'w': 1, 'l': 1, 't': 1, 'pct': 0.5,
        'pf': 68, 'pa': 69, 'home': '0-0-1', 'away': '1-1',
        'div': '0-1', 'strk': 'W1', 'gb': '1',
    }
    assert rows['MIA']['w'] == 2  # Its unfinished third game does not count.

    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_standings')
    raw = tool.func(season=2024)
    projected = json.loads(raw)
    assert projected == [
        {
            'division': division['division'], 'team': row['team'],
            'w': row['w'], 'l': row['l'], 't': row['t'], 'pct': row['pct'],
            'pf': row['pf'], 'pa': row['pa'], 'div': row['div'], 'streak': row['strk'],
        }
        for division in divisions for row in division['teams']
    ]
    assert ctx.calls == [{'tool': 'get_standings', 'args': {'season': 2024}}]
    assert ctx.data == projected
    assert ctx.raw_results == [raw]


def test_plain_default_and_http_default_use_the_current_season(client, monkeypatch):
    monkeypatch.setattr(standings, 'CURRENT_SEASON', 2024)
    expected = standings.get_standings(2024)
    assert standings.get_standings() == expected
    assert standings.get_standings(None) == expected
    assert client.get('/api/standings').json() == expected
    # An explicit year without games must not silently substitute the default.
    assert all(not division['teams'] for division in standings.get_standings(0))
    assert client.get('/api/standings?season=banana').status_code == 422


def test_team_overview_uses_the_same_record_even_without_profile_games(client, monkeypatch):
    import llm

    monkeypatch.setattr(llm, '_team_query', lambda team, season: {'games': []})
    monkeypatch.setattr(llm, 'CURRENT_SEASON', 2026)
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_team_overview')
    result = json.loads(tool.func(team='buf', season=2024))
    assert result == {
        'team': 'BUF', 'season': 2024, 'record': '1-1-1', 'regular_season_games': 3,
        'standing': {
            'division': 'AFC East', 'pct': 0.5, 'points_for': 68,
            'points_against': 69, 'division_record': '0-1', 'streak': 'W1',
        },
    }
    assert ctx.data == [result]


def test_unplayed_regular_games_include_zero_records_but_playoffs_do_not(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE schedules (
            season INTEGER, week INTEGER, game_type VARCHAR,
            away_team VARCHAR, home_team VARCHAR, away_score INTEGER, home_score INTEGER
        )''')
        conn.execute('''INSERT INTO schedules VALUES
            (2024, 1, 'REG', 'BUF', 'MIA', NULL, NULL),
            (2024, 19, 'WC', 'DEN', 'KC', 7, 28)
        ''')
        monkeypatch.setattr(database, '_conn', conn)
        divisions = standings.get_standings(2024)
        rows = {row['team']: row for division in divisions for row in division['teams']}
        assert set(rows) == {'BUF', 'MIA'}
        assert len(divisions) == 8
        for row in rows.values():
            assert (row['w'], row['l'], row['t'], row['pf'], row['pa'], row['pct']) == (0, 0, 0, 0, 0, 0)
            assert (row['home'], row['away'], row['div'], row['strk'], row['gb']) == ('0-0', '0-0', '0-0', '—', '—')


def test_unexpected_query_failure_is_not_an_empty_standings_result(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('standings storage failed')

    monkeypatch.setattr(standings, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='standings storage failed'):
        standings.get_standings(2024)
