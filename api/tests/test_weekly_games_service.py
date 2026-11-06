"""Offline weekly schedule selection and its HTTP missing-data boundary."""
import duckdb
import pytest

from schemas.schedule import Game
from services import schedule


@pytest.fixture
def weekly_games(monkeypatch):
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
             away_score, home_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', [
            ('late', 2024, 'REG', 1, '2024-09-05', '20:00', 'BUF', 'MIA', 21, 14),
            ('early', 2024, 'PRE', 1, '2024-09-08', '13:00', 'KC', 'DEN', None, None),
            ('other-week', 2024, 'REG', 2, None, '13:00', 'BUF', 'DEN', 7, 0),
            ('postseason', 2024, 'SB', 22, None, '18:30', 'BUF', 'KC', 14, 21),
            ('other-year', 2023, 'REG', 1, None, '13:00', 'BUF', 'MIA', 7, 0),
        ])
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def _http_rows(rows):
    # The HTTP schema supplies null records; this endpoint does not annotate them.
    return [Game.model_validate(row).model_dump(mode='json') for row in rows]


def test_seeded_service_and_http_week_match(client):
    rows = schedule.get_games(1, 2024)
    assert {row['game_id'] for row in rows} == {'2024_01_BUF_MIA', '2024_01_DEN_KC'}
    response = client.get('/api/games?week=1&season=2024')
    assert response.status_code == 200
    assert response.json() == _http_rows(rows)


def test_week_year_filter_kickoff_order_types_and_nullable_fields(client, weekly_games):
    rows = schedule.get_games(1, 2024)
    # Kickoff time, rather than calendar date, remains the existing sort policy.
    assert [row['game_id'] for row in rows] == ['early', 'late']
    assert [row['game_type'] for row in rows] == ['PRE', 'REG']
    assert rows[0]['away_score'] is None and rows[0]['home_score'] is None
    assert rows[0]['away_coach'] is None and rows[0]['spread_line'] is None
    assert all('away_record' not in row and 'home_record' not in row for row in rows)
    response = client.get('/api/games?week=1&season=2024')
    assert response.status_code == 200
    assert response.json() == _http_rows(rows)
    assert all(row['away_record'] is None and row['home_record'] is None for row in response.json())


def test_other_year_and_week_22_are_selected_exactly(client, weekly_games):
    for week, season, game_id in [(1, 2023, 'other-year'), (22, 2024, 'postseason')]:
        rows = schedule.get_games(week, season)
        assert [row['game_id'] for row in rows] == [game_id]
        response = client.get('/api/games', params={'week': week, 'season': season})
        assert response.status_code == 200
        assert response.json() == _http_rows(rows)


@pytest.mark.parametrize(('week', 'season'), [(10, 2024), (1, 2022), (1, 0)])
def test_empty_service_result_becomes_exact_http_404(client, weekly_games, week, season):
    assert schedule.get_games(week, season) == []
    response = client.get('/api/games', params={'week': week, 'season': season})
    assert response.status_code == 404
    assert response.json() == {'detail': f'No games found for week {week}, season {season}'}


def test_http_omitted_season_passes_configured_default(client, monkeypatch):
    import config
    import routers.schedule

    calls = []
    def empty(week, season):
        calls.append((week, season))
        return []
    monkeypatch.setattr(routers.schedule, 'query_games', empty)
    response = client.get('/api/games?week=1')
    assert calls == [(1, config.CURRENT_SEASON)]
    assert response.status_code == 404
    assert response.json() == {'detail': f'No games found for week 1, season {config.CURRENT_SEASON}'}


@pytest.mark.parametrize('params', [
    {'season': 2024},
    {'week': 0, 'season': 2024},
    {'week': 23, 'season': 2024},
    {'week': 'banana', 'season': 2024},
    {'week': 1, 'season': 'banana'},
])
def test_invalid_http_parameters_stop_before_sql(client, monkeypatch, params):
    def unexpected_query(*args, **kwargs):
        pytest.fail('invalid HTTP input reached the weekly game query')
    monkeypatch.setattr(schedule, 'query_to_dict', unexpected_query)
    assert client.get('/api/games', params=params).status_code == 422


def test_query_failure_propagates_instead_of_becoming_not_found(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('weekly game storage failed')
    monkeypatch.setattr(schedule, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='weekly game storage failed'):
        schedule.get_games(1, 2024)
    with pytest.raises(RuntimeError, match='weekly game storage failed'):
        client.get('/api/games?week=1&season=2024')
