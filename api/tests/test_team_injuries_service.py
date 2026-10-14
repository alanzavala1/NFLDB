"""Offline team injury-report selection and HTTP/assistant checks."""
import json

import duckdb
import pytest

from services import team_injuries


@pytest.fixture
def injury_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE injuries (
            season INTEGER, week INTEGER, team VARCHAR,
            report_primary_injury VARCHAR, report_secondary_injury VARCHAR,
            report_status VARCHAR, practice_primary_injury VARCHAR,
            practice_status VARCHAR, full_name VARCHAR, position VARCHAR, gsis_id VARCHAR
        )''')
        conn.executemany('INSERT INTO injuries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [
            (2024, 4, 'KC', 'Ankle', None, 'Out', 'Ankle', 'Did Not Participate', 'Zoe Out', 'WR', 'zoe'),
            (2024, 4, 'KC', 'Knee', 'Foot', 'Out', 'Knee', 'Did Not Participate', 'Ada Out', 'QB', 'ada'),
            (2024, 4, 'KC', 'Shoulder', None, 'Doubtful', 'Shoulder', 'Limited', 'Dan Doubtful', 'RB', 'dan'),
            (2024, 4, 'KC', 'Calf', None, 'Questionable', 'Calf', 'Limited', 'Quinn Questionable', 'TE', 'quinn'),
            (2024, 4, 'KC', 'Wrist', None, 'Probable', 'Wrist', 'Full', 'Pat Probable', 'WR', 'pat'),
            (2024, 4, 'KC', None, None, None, None, None, 'Nora NoStatus', None, None),
            (2024, 4, 'KC', None, None, 'Other', None, None, 'Una Unknown', 'LB', 'una'),
            (2024, 2, 'KC', 'Hip', None, 'Questionable', None, 'Limited', 'Older Report', 'QB', 'older'),
            (2024, 9, 'BUF', 'Ankle', None, 'Out', None, None, 'Other Team', 'WR', 'other'),
            (2025, 12, 'KC', 'Knee', None, 'Out', None, None, 'Other Season', 'QB', 'future'),
        ])
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def test_latest_team_season_report_order_projection_and_http_parity(client, injury_data):
    rows = team_injuries.get_team_injuries('KC', 2024)
    assert [row['full_name'] for row in rows] == [
        'Ada Out', 'Zoe Out', 'Dan Doubtful', 'Quinn Questionable',
        'Pat Probable', 'Nora NoStatus', 'Una Unknown',
    ]
    assert {row['week'] for row in rows} == {4}
    assert rows[0] == {
        'season': 2024, 'week': 4, 'team': 'KC', 'report_primary_injury': 'Knee',
        'report_secondary_injury': 'Foot', 'report_status': 'Out',
        'practice_primary_injury': 'Knee', 'practice_status': 'Did Not Participate',
        'full_name': 'Ada Out', 'position': 'QB', 'gsis_id': 'ada',
    }
    assert rows[-2]['report_status'] is None
    assert rows[-2]['gsis_id'] is None
    response = client.get('/api/teams/KC/injuries?season=2024')
    assert response.status_code == 200
    assert response.json() == rows


def test_explicit_week_selects_the_report_instead_of_the_latest(client, injury_data):
    rows = team_injuries.get_team_injuries('KC', 2024, 2)
    assert len(rows) == 1
    assert rows[0]['full_name'] == 'Older Report'
    assert rows[0]['week'] == 2
    response = client.get('/api/teams/KC/injuries?season=2024&week=2')
    assert response.status_code == 200
    assert response.json() == rows


@pytest.mark.parametrize('week', [-1, 0, 3, 999])
def test_missing_requested_week_does_not_fall_back(client, injury_data, week):
    assert team_injuries.get_team_injuries('KC', 2024, week) == []
    response = client.get('/api/teams/KC/injuries', params={'season': 2024, 'week': week})
    assert response.status_code == 200
    assert response.json() == []


def test_default_season_and_team_season_isolation(client, injury_data, monkeypatch):
    monkeypatch.setattr(team_injuries, 'CURRENT_SEASON', 2024)
    expected = team_injuries.get_team_injuries('KC', 2024)
    assert team_injuries.get_team_injuries('KC') == expected
    assert team_injuries.get_team_injuries('KC', None) == expected
    assert client.get('/api/teams/KC/injuries').json() == expected
    assert team_injuries.get_team_injuries('BUF', 2024)[0]['week'] == 9
    assert team_injuries.get_team_injuries('KC', 2025)[0]['week'] == 12
    assert team_injuries.get_team_injuries('KC', 2023) == []
    assert team_injuries.get_team_injuries('ZZZ', 2024) == []


def _overview(monkeypatch):
    import llm

    monkeypatch.setattr(llm, 'CURRENT_SEASON', 2024)
    monkeypatch.setattr(llm, '_team_query', lambda team, season: {'games': []})
    monkeypatch.setattr(llm, '_standings_query', lambda season: [])
    monkeypatch.setattr(llm, '_schedule_query', lambda season: [])
    monkeypatch.setattr(llm, '_team_depth_query', lambda *args: [])
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_team_overview')
    return ctx, tool


def test_assistant_current_report_projection_provenance_and_historical_skip(injury_data, monkeypatch):
    import llm

    ctx, tool = _overview(monkeypatch)
    raw = tool.func(team='kc', season=2024)
    result = json.loads(raw)
    assert len(result['current_injuries']) == 7
    assert result['current_injuries'][0] == {
        'name': 'Ada Out', 'position': 'QB', 'injury': 'Knee', 'status': 'Out',
        'practice_status': 'Did Not Participate', 'week': 4,
    }
    assert result['current_injuries'][-2] == {'name': 'Nora NoStatus', 'week': 4}
    assert ctx.calls == [{'tool': 'get_team_overview', 'args': {'team': 'KC', 'season': 2024}}]
    assert ctx.data == [result]
    assert ctx.raw_results == [raw]
    def unexpected_injuries(*args, **kwargs):
        pytest.fail('historical team overview requested a current injury report')
    monkeypatch.setattr(llm, '_team_injuries_query', unexpected_injuries)
    assert 'current_injuries' not in json.loads(tool.func(team='KC', season=2023))


def test_assistant_keeps_twenty_entry_cap_and_service_order(injury_data, monkeypatch):
    injury_data.executemany('INSERT INTO injuries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [
        (2024, 4, 'KC', 'Ankle', None, 'Out', None, None, f'Cap {i:02}', 'WR', f'cap-{i}')
        for i in range(25)
    ])
    _, tool = _overview(monkeypatch)
    injuries = json.loads(tool.func(team='KC', season=2024))['current_injuries']
    assert len(injuries) == 20
    assert [row['name'] for row in injuries] == ['Ada Out'] + [f'Cap {i:02}' for i in range(19)]


@pytest.mark.parametrize('parameter', ['season', 'week'])
def test_invalid_http_integer_is_rejected_before_querying(client, monkeypatch, parameter):
    def unexpected_query(*args, **kwargs):
        pytest.fail('invalid HTTP input reached the injury query')
    monkeypatch.setattr(team_injuries, 'safe_query', unexpected_query)
    assert client.get('/api/teams/KC/injuries', params={parameter: 'banana'}).status_code == 422


def test_unexpected_query_failure_propagates(client, injury_data, monkeypatch):
    import sql_helpers

    def fail(*args, **kwargs):
        raise RuntimeError('injury storage failed')
    monkeypatch.setattr(sql_helpers, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='injury storage failed'):
        team_injuries.get_team_injuries('KC', 2024)
    with pytest.raises(RuntimeError, match='injury storage failed'):
        client.get('/api/teams/KC/injuries?season=2024')
