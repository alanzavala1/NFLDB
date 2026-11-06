"""Offline roster selection and HTTP missing-data boundary checks."""
import duckdb
import pytest

from services import team_roster


@pytest.fixture
def roster_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE rosters (
            player_id VARCHAR, season INTEGER, week INTEGER, team VARCHAR,
            player_name VARCHAR, position VARCHAR, jersey_number INTEGER, headshot_url VARCHAR
        )''')
        conn.executemany('INSERT INTO rosters VALUES (?, ?, ?, ?, ?, ?, ?, ?)', [
            ('shared', 2024, 1, 'BUF', 'Zed QB', 'QB', 7, 'zed.png'),
            ('shared', 2024, 8, 'BUF', 'Zed QB', 'QB', 7, 'zed.png'),
            ('alpha', 2024, 2, 'BUF', 'Alpha QB', 'QB', 8, None),
            ('receiver', 2024, 2, 'BUF', 'Wide Receiver', 'WR', 80, 'receiver.png'),
            ('other', 2024, 2, 'BUF', 'Other Position', 'ZZ', None, None),
            ('null', 2024, 2, 'BUF', 'No Position', None, None, None),
            ('shared', 2024, 9, 'MIA', 'Other Team QB', 'QB', 99, 'mia.png'),
            ('shared', 2023, 9, 'BUF', 'Older QB', 'QB', 10, 'older.png'),
        ])
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def test_seeded_service_and_http_rosters_match(client):
    rows = team_roster.get_team_roster('BUF', 2024)
    assert [row['player_name'] for row in rows] == ['Josh Allen', 'Stefon Diggs']
    response = client.get('/api/teams/BUF/roster?season=2024')
    assert response.status_code == 200
    assert response.json() == rows


def test_deduplication_order_projection_and_nullable_fields(client, roster_data):
    rows = team_roster.get_team_roster('BUF', 2024)
    assert [row['player_id'] for row in rows] == ['alpha', 'shared', 'receiver', 'other', 'null']
    assert rows[1] == {
        'player_id': 'shared', 'player_name': 'Zed QB', 'position': 'QB',
        'jersey_number': 7, 'headshot_url': 'zed.png',
    }
    assert rows[-1] == {
        'player_id': 'null', 'player_name': 'No Position', 'position': None,
        'jersey_number': None, 'headshot_url': None,
    }
    response = client.get('/api/teams/BUF/roster?season=2024')
    assert response.status_code == 200
    assert response.json() == rows


def test_team_and_season_filters_preserve_their_own_roster(client, roster_data):
    for team, season, name in [('MIA', 2024, 'Other Team QB'), ('BUF', 2023, 'Older QB')]:
        rows = team_roster.get_team_roster(team, season)
        assert len(rows) == 1
        assert rows[0]['player_name'] == name
        response = client.get(f'/api/teams/{team}/roster', params={'season': season})
        assert response.status_code == 200
        assert response.json() == rows


@pytest.mark.parametrize(('team', 'season'), [('ZZZ', 2024), ('BUF', 2022), ('BUF', 0)])
def test_empty_service_result_becomes_the_same_http_404(client, roster_data, team, season):
    assert team_roster.get_team_roster(team, season) == []
    response = client.get(f'/api/teams/{team}/roster', params={'season': season})
    assert response.status_code == 404
    assert response.json() == {'detail': f'No roster found for {team} in {season}'}


def test_http_default_passes_the_resolved_year_to_the_service(client, roster_data, monkeypatch):
    import routers.teams

    monkeypatch.setattr(routers.teams, 'CURRENT_SEASON', 2024)
    expected = team_roster.get_team_roster('BUF', 2024)
    response = client.get('/api/teams/BUF/roster')
    assert response.status_code == 200
    assert response.json() == expected
    missing = client.get('/api/teams/ZZZ/roster')
    assert missing.status_code == 404
    assert missing.json() == {'detail': 'No roster found for ZZZ in 2024'}


def test_invalid_http_season_is_rejected_before_querying(client, monkeypatch):
    def unexpected_query(*args, **kwargs):
        pytest.fail('invalid HTTP input reached the roster query')
    monkeypatch.setattr(team_roster, 'query_to_dict', unexpected_query)
    assert client.get('/api/teams/BUF/roster?season=banana').status_code == 422


def test_query_failure_propagates_instead_of_becoming_not_found(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('roster storage failed')
    monkeypatch.setattr(team_roster, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='roster storage failed'):
        team_roster.get_team_roster('BUF', 2024)
    with pytest.raises(RuntimeError, match='roster storage failed'):
        client.get('/api/teams/BUF/roster?season=2024')
