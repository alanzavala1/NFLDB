"""Offline WPA definitions, qualification and HTTP-contract checks."""
import duckdb
import pytest

from schemas.leaders import WpaLeaders
from services import wpa_leaders


CATEGORIES = {
    'passing': ('passer', 'air_wpa', 50, 'attempts', 1.0),
    'rushing': ('rusher', 'wpa', 50, 'carries', 1.5),
    'receiving': ('receiver', 'yac_wpa', 20, 'receptions', 0.8),
}
EMPTY = {'passing': [], 'rushing': [], 'receiving': []}


@pytest.fixture
def wpa_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE plays (
            season INTEGER, season_type VARCHAR, game_id VARCHAR,
            passer_player_id VARCHAR, passer_player_name VARCHAR,
            rusher_player_id VARCHAR, rusher_player_name VARCHAR,
            receiver_player_id VARCHAR, receiver_player_name VARCHAR,
            pass_attempt INTEGER, rush_attempt INTEGER, complete_pass INTEGER,
            air_wpa DOUBLE, wpa DOUBLE, yac_wpa DOUBLE
        )''')
        conn.execute('''CREATE TABLE rosters (
            player_id VARCHAR, season INTEGER, week INTEGER, team VARCHAR,
            position VARCHAR, jersey_number INTEGER, headshot_url VARCHAR
        )''')
        conn.execute('''INSERT INTO rosters VALUES
            ('passing-high', 2024, 1, 'BUF', 'QB', 1, 'old.png'),
            ('passing-high', 2024, 4, 'SEA', 'QB', 1, 'tie.png'),
            ('passing-high', 2024, 4, 'KC', 'QB', 1, 'latest.png'),
            ('passing-high', 2025, 99, 'NYJ', 'QB', 1, 'other-year.png')
        ''')

        def add(category, player, count, *, season=2024, season_type='REG', complete=1, metric=None, null=False):
            role, column, *_ = CATEGORIES[category]
            metrics = {'air_wpa': 0.020001, 'wpa': 0.030001, 'yac_wpa': 0.040001}
            if metric is not None:
                metrics[column] = metric
            if null:
                metrics = {key: None for key in metrics}
            rows = []
            for i in range(count):
                row = {
                    'season': season, 'season_type': season_type, 'game_id': f'game-{i % 2}',
                    'passer_player_id': None, 'passer_player_name': None,
                    'rusher_player_id': None, 'rusher_player_name': None,
                    'receiver_player_id': None, 'receiver_player_name': None,
                    'pass_attempt': int(category != 'rushing'),
                    'rush_attempt': int(category == 'rushing'), 'complete_pass': complete,
                    **metrics,
                }
                row[f'{role}_player_id'] = player
                row[f'{role}_player_name'] = f'{player or "Unknown"} Name'
                rows.append(list(row.values()))
            conn.executemany('INSERT INTO plays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)

        for category, (_, _, threshold, _, _) in CATEGORIES.items():
            add(category, f'{category}-high', threshold)
            add(category, f'{category}-null', threshold, null=True)
            add(category, f'{category}-low', threshold - 1)
            add(category, f'{category}-low', 10, season_type='POST', metric=10)
            add(category, f'{category}-low', 10, season_type='PRE', metric=10)
            add(category, f'{category}-low', 10, season=2023, metric=10)
            add(category, None, threshold, metric=10)
        add('receiving', 'receiving-high', 5, complete=0, metric=10)
        add('receiving', 'receiving-low', 5, complete=0, metric=10)
        monkeypatch.setattr(database, '_conn', conn)
        yield conn, add


def test_wpa_definitions_qualification_roster_join_and_http_shape(client, wpa_data):
    result = wpa_leaders.get_wpa_leaders(2024)
    for category, (_, _, threshold, volume, expected_wpa) in CATEGORIES.items():
        high, zero = result[category]
        assert high['player_id'] == f'{category}-high'
        assert high['wpa'] == expected_wpa
        assert high[volume] == threshold
        assert high['games_played'] == 2
        assert zero['player_id'] == f'{category}-null'
        assert zero['wpa'] == 0
        assert (zero['team'], zero['position'], zero['headshot_url']) == (None, None, None)
    assert (result['passing'][0]['team'], result['passing'][0]['headshot_url']) == ('KC', 'latest.png')
    response = client.get('/api/wpa-leaders?season=2024')
    assert response.status_code == 200
    assert response.json() == WpaLeaders.model_validate(result).model_dump()
    for category, (_, _, _, volume, _) in CATEGORIES.items():
        row = response.json()[category][0]
        assert all(row[key] is None for key in ('attempts', 'carries', 'receptions') if key != volume)


@pytest.mark.parametrize('category', CATEGORIES)
def test_each_wpa_list_sorts_descending_and_stops_at_30(wpa_data, category):
    _, add = wpa_data
    threshold = CATEGORIES[category][2]
    for i in range(35):
        add(category, f'cap-{i:02}', threshold, metric=i + 1)
    rows = wpa_leaders.get_wpa_leaders(2024)[category]
    assert len(rows) == 30
    assert [row['player_id'] for row in rows] == [f'cap-{i:02}' for i in range(34, 4, -1)]
    assert [row['wpa'] for row in rows] == sorted([row['wpa'] for row in rows], reverse=True)


def test_default_season_and_explicit_empty_or_invalid_year(client, wpa_data, monkeypatch):
    monkeypatch.setattr(wpa_leaders, 'CURRENT_SEASON', 2024)
    expected = wpa_leaders.get_wpa_leaders(2024)
    assert wpa_leaders.get_wpa_leaders() == expected
    assert wpa_leaders.get_wpa_leaders(None) == expected
    assert client.get('/api/wpa-leaders').json() == WpaLeaders.model_validate(expected).model_dump()
    assert wpa_leaders.get_wpa_leaders(0) == EMPTY
    assert client.get('/api/wpa-leaders?season=0').json() == EMPTY
    assert client.get('/api/wpa-leaders?season=banana').status_code == 422


def test_missing_plays_retains_logged_empty_list_fallback(client, wpa_data, caplog):
    conn, _ = wpa_data
    conn.execute('DROP TABLE plays')
    assert wpa_leaders.get_wpa_leaders(2024) == EMPTY
    response = client.get('/api/wpa-leaders?season=2024')
    assert response.status_code == 200
    assert response.json() == EMPTY
    assert 'safe_query failed, returning []' in caplog.text


def test_one_failed_category_preserves_the_other_two(client, wpa_data, caplog):
    conn, _ = wpa_data
    expected = wpa_leaders.get_wpa_leaders(2024)
    conn.execute('ALTER TABLE plays DROP COLUMN air_wpa')
    expected['passing'] = []
    assert wpa_leaders.get_wpa_leaders(2024) == expected
    response = client.get('/api/wpa-leaders?season=2024')
    assert response.status_code == 200
    assert response.json() == WpaLeaders.model_validate(expected).model_dump()
    assert 'safe_query failed, returning []' in caplog.text
