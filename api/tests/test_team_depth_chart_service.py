"""Offline checks for current team snapshots and HTTP/assistant consumers."""
import json

import duckdb
import pytest

from services import team_depth_chart


@pytest.fixture
def depth_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE depth_charts (
            dt VARCHAR, team VARCHAR, player_name VARCHAR, gsis_id VARCHAR,
            pos_grp VARCHAR, pos_abb VARCHAR, pos_slot INTEGER, pos_rank INTEGER
        )''')
        conn.executemany('INSERT INTO depth_charts VALUES (?, ?, ?, ?, ?, ?, ?, ?)', [
            ('2025-01-12T07:00:00Z', 'KC', 'Starter QB', 'qb1', '3WR 1TE', 'QB', 9, 1),
            ('2025-01-12T07:00:00Z', 'KC', 'Backup QB', 'qb2', '3WR 1TE', 'QB', 9, 2),
            ('2025-01-12T07:00:00Z', 'KC', 'Starting RB', 'rb1', '3WR 1TE', 'RB', 2, 1),
            ('2025-01-12T07:00:00Z', 'KC', 'Defender', 'de1', 'Base 4-3 D', 'LDE', 1, 1),
            ('2025-01-12T07:00:00Z', 'KC', 'Kicker', 'k1', 'Special Teams', 'PK', 1, 1),
            ('2025-01-11T07:00:00Z', 'KC', 'Starter QB', 'qb1', '3WR 1TE', 'QB', 9, 2),
            ('2025-01-11T07:00:00Z', 'BUF', 'Older Team QB', 'old', '3WR 1TE', 'QB', 9, 1),
        ])
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def test_ordinary_default_matches_the_http_snapshot_without_a_season_guess(client):
    rows = team_depth_chart.get_team_depth_chart('KC')
    assert len(rows) == 5
    response = client.get('/api/teams/KC/depth-chart')
    assert response.status_code == 200
    assert response.json() == rows
    assert {row['season'] for row in rows} == {2024}


def test_projection_order_latest_snapshot_and_january_season(client, depth_data):
    rows = team_depth_chart.get_team_depth_chart('KC', 2024)
    assert [row['full_name'] for row in rows] == ['Starting RB', 'Starter QB', 'Backup QB', 'Defender', 'Kicker']
    assert [row['formation'] for row in rows] == ['Offense', 'Offense', 'Offense', 'Defense', 'Special Teams']
    assert rows[1] == {
        'season': 2024, 'week': None, 'team': 'KC', 'formation': 'Offense',
        'depth_position': 'QB', 'depth_team': '1', 'gsis_id': 'qb1',
        'full_name': 'Starter QB', 'position': 'QB', 'jersey_number': None,
    }
    assert rows[2]['depth_team'] == '2'
    assert all(row['week'] is None and row['jersey_number'] is None for row in rows)
    response = client.get('/api/teams/KC/depth-chart?season=2024')
    assert response.status_code == 200
    assert response.json() == rows


@pytest.mark.parametrize('week', [-1, 0, 9, 999])
def test_integer_week_is_accepted_but_does_not_select_history(client, depth_data, week):
    expected = team_depth_chart.get_team_depth_chart('KC', 2024)
    assert team_depth_chart.get_team_depth_chart('KC', 2024, week) == expected
    response = client.get('/api/teams/KC/depth-chart', params={'season': 2024, 'week': week})
    assert response.status_code == 200
    assert response.json() == expected


def test_old_team_rows_unknown_teams_and_mismatched_seasons_stay_empty(client, depth_data):
    assert team_depth_chart.get_team_depth_chart('BUF', 2024) == []
    assert team_depth_chart.get_team_depth_chart('ZZZ') == []
    assert team_depth_chart.get_team_depth_chart('KC', 2025) == []
    for team, season in [('BUF', 2024), ('ZZZ', 2024), ('KC', 2025)]:
        response = client.get(f'/api/teams/{team}/depth-chart', params={'season': season})
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.parametrize(('snapshot', 'season'), [
    ('2025-08-31T07:00:00Z', 2024), ('2025-09-01T07:00:00Z', 2025),
])
def test_existing_snapshot_season_rule_crosses_at_september(depth_data, snapshot, season):
    depth_data.execute('UPDATE depth_charts SET dt = ? WHERE dt = (SELECT MAX(dt) FROM depth_charts)', [snapshot])
    rows = team_depth_chart.get_team_depth_chart('KC')
    assert len(rows) == 5
    assert {row['season'] for row in rows} == {season}


def test_team_overview_uses_shared_current_starters_and_skips_historical_depth(client, depth_data, monkeypatch):
    import llm

    monkeypatch.setattr(llm, 'CURRENT_SEASON', 2024)
    monkeypatch.setattr(llm, '_team_query', lambda team, season: {'games': []})
    monkeypatch.setattr(llm, '_standings_query', lambda season: [])
    monkeypatch.setattr(llm, '_schedule_query', lambda season: [])
    monkeypatch.setattr(llm, '_team_injuries_query', lambda *args: [])
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_team_overview')
    raw = tool.func(team='kc', season=2024)
    result = json.loads(raw)
    assert result['offensive_starters'] == [
        {'name': 'Starting RB', 'position': 'RB'}, {'name': 'Starter QB', 'position': 'QB'},
    ]
    assert ctx.calls == [{'tool': 'get_team_overview', 'args': {'team': 'KC', 'season': 2024}}]
    assert ctx.data == [result]
    assert ctx.raw_results == [raw]

    def unexpected_depth(*args, **kwargs):
        pytest.fail('historical team overview requested current depth data')
    monkeypatch.setattr(llm, '_team_depth_query', unexpected_depth)
    historical = json.loads(tool.func(team='KC', season=2023))
    assert 'offensive_starters' not in historical


@pytest.mark.parametrize('parameter', ['season', 'week'])
def test_invalid_http_integer_is_rejected_before_querying(client, monkeypatch, parameter):
    def unexpected_query(*args, **kwargs):
        pytest.fail('invalid HTTP input reached the depth query')
    monkeypatch.setattr(team_depth_chart, 'safe_query', unexpected_query)
    assert client.get('/api/teams/KC/depth-chart', params={parameter: 'banana'}).status_code == 422


def test_missing_depth_table_retains_logged_empty_fallback(client, depth_data, caplog):
    depth_data.execute('DROP TABLE depth_charts')
    assert team_depth_chart.get_team_depth_chart('KC', 2024) == []
    response = client.get('/api/teams/KC/depth-chart?season=2024')
    assert response.status_code == 200
    assert response.json() == []
    assert 'safe_query failed, returning []' in caplog.text
