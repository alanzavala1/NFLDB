"""Offline rating assembly, shared player totals and HTTP absence handling."""
import duckdb
import pytest

import game_ratings_builder
from database import query_to_dict
from schemas.ratings import GamePlayerRating
from services import game_ratings
from sql_helpers import PGS_GAME_CTE
from tests.conftest import _create_schema, _seed

GAME_ID = '2024_01_BUF_MIA'


@pytest.fixture
def ratings_data(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        _create_schema(conn)
        _seed(conn)
        game_ratings_builder.ensure_table(conn)
        conn.executemany('''INSERT INTO player_game_ratings
            (player_id, game_id, season, week, team, position_group, rating, raw_score)
            VALUES (?, ?, 2024, 1, ?, ?, ?, ?)''', [
            ('00-BUF-QB1', GAME_ID, 'BUF', 'QB', 8, 4),
            ('no-stats', GAME_ID, 'MIA', 'RB', 8, 4),
            ('tie', GAME_ID, 'BUF', 'WR', 8, 4),
            ('low', GAME_ID, 'BUF', 'RB', 7, 99),
            ('null-high', GAME_ID, 'MIA', 'DEF', None, 5),
            ('missing', GAME_ID, None, 'DEF', None, None),
            ('00-BUF-QB1', '2024_02_KC_BUF', 'BUF', 'QB', 10, 100),
        ])
        conn.execute('''UPDATE player_game_ratings
            SET plays_counted = 30, epa_total = 2.5, turnovers = 1,
                def_events_score = 0, fg_points = 0
            WHERE player_id = '00-BUF-QB1' AND game_id = '2024_01_BUF_MIA' ''')
        conn.executemany('''INSERT INTO rosters
            (player_id, season, week, team, player_name, position)
            VALUES (?, ?, ?, ?, ?, ?)''', [
            ('00-BUF-QB1', 2024, 8, 'NYJ', 'Roster Name', 'WR'),
            ('00-BUF-QB1', 2025, 99, 'SEA', 'Wrong Season', 'TE'),
            ('no-stats', 2024, 1, 'MIA', 'Old Name', 'TE'),
            ('no-stats', 2024, 8, 'MIA', 'Alpha Name', 'RB'),
            ('no-stats', 2024, 8, 'SEA', 'Wrong Tie', 'TE'),
        ])
        conn.executemany('''INSERT INTO player_game_stats
            (player_id, player_name, game_id, season, week, team, pass_yards, sacks)
            VALUES (?, ?, ?, 2024, 1, 'BUF', ?, ?)''', [
            ('00-BUF-QB1', 'Josh Allen', GAME_ID, 25, 0),
            ('00-BUF-QB1', None, GAME_ID, None, 1),
            ('tie', 'Zed Name', GAME_ID, 0, 0),
            ('low', 'Low Name', GAME_ID, 0, 0),
        ])
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def _http_rows(rows):
    return [GamePlayerRating.model_validate(row).model_dump(mode='json') for row in rows]


def test_projection_order_roster_name_fallback_and_http_parity(client, ratings_data):
    rows = game_ratings.get_game_ratings(GAME_ID)
    assert [row['player_id'] for row in rows] == [
        'no-stats', '00-BUF-QB1', 'tie', 'low', 'null-high', 'missing',
    ]
    assert rows[0]['player_name'] == 'Alpha Name' and rows[0]['position'] == 'RB'
    assert rows[1] == {
        'player_id': '00-BUF-QB1', 'player_name': 'Josh Allen', 'team': 'BUF',
        'position': 'WR', 'position_group': 'QB', 'rating': 8, 'raw_score': 4,
        'plays_counted': 30, 'epa_total': 2.5, 'turnovers': 1,
        'def_events_score': 0, 'fg_points': 0,
    }
    assert rows[2]['position'] is None
    assert rows[-1]['player_name'] is None and rows[-1]['team'] is None
    assert rows[-1]['rating'] is None and rows[-1]['plays_counted'] is None
    response = client.get(f'/api/games/{GAME_ID}/ratings')
    assert response.status_code == 200 and response.json() == _http_rows(rows)


def test_shared_player_game_fragment_sums_duplicates_and_null_stats(ratings_data):
    rows = query_to_dict(f'''WITH {PGS_GAME_CTE}
        SELECT player_id, game_id, pass_yards, sacks
        FROM pgs_game WHERE player_id = '00-BUF-QB1' ''', [GAME_ID])
    assert rows == [{'player_id': '00-BUF-QB1', 'game_id': GAME_ID, 'pass_yards': 265, 'sacks': 1}]


def test_missing_ratings_table_still_uses_real_builder(client, ratings_data):
    ratings_data.execute('DROP TABLE player_game_ratings')
    rows = game_ratings.get_game_ratings(GAME_ID)
    assert rows and any(row['player_id'] == '00-BUF-QB1' for row in rows)
    assert ratings_data.execute('SELECT COUNT(*) FROM player_game_ratings').fetchone()[0] > 0
    response = client.get(f'/api/games/{GAME_ID}/ratings')
    assert response.status_code == 200 and response.json() == _http_rows(rows)


@pytest.mark.parametrize('game_id', ['missing', '2024_01_MIA_BUF'])
def test_missing_game_returns_domain_none_and_exact_http_404(client, ratings_data, monkeypatch, game_id):
    def unexpected_builder(*args):
        pytest.fail('missing game reached the ratings builder')
    monkeypatch.setattr(game_ratings_builder, 'read_or_materialize', unexpected_builder)
    assert game_ratings.get_game_ratings(game_id) is None
    response = client.get(f'/api/games/{game_id}/ratings')
    assert response.status_code == 404
    assert response.json() == {'detail': f'Game {game_id} not found'}


def test_empty_builder_result_is_http_success_and_skips_enrichment(client, ratings_data, monkeypatch):
    original = game_ratings.query_to_dict
    builder_calls = []
    def empty(game_id):
        builder_calls.append(game_id)
        return []
    def schedule_only(sql, params):
        assert 'SELECT game_id FROM schedules' in sql
        return original(sql, params)
    monkeypatch.setattr(game_ratings_builder, 'read_or_materialize', empty)
    monkeypatch.setattr(game_ratings, 'query_to_dict', schedule_only)
    assert game_ratings.get_game_ratings(GAME_ID) == []
    response = client.get(f'/api/games/{GAME_ID}/ratings')
    assert response.status_code == 200 and response.json() == []
    assert builder_calls == [GAME_ID, GAME_ID]


@pytest.mark.parametrize('stage', [1, 2])
def test_query_errors_propagate_instead_of_becoming_missing_ratings(client, ratings_data, monkeypatch, stage):
    original = game_ratings.query_to_dict
    for action in [
        lambda: game_ratings.get_game_ratings(GAME_ID),
        lambda: client.get(f'/api/games/{GAME_ID}/ratings'),
    ]:
        calls = []
        def fail_at(sql, params):
            calls.append(sql)
            if len(calls) == stage:
                raise RuntimeError('rating storage failed')
            return original(sql, params)
        monkeypatch.setattr(game_ratings, 'query_to_dict', fail_at)
        with pytest.raises(RuntimeError, match='rating storage failed'):
            action()


def test_unexpected_builder_error_propagates(client, ratings_data, monkeypatch):
    def fail(*args):
        raise RuntimeError('rating builder failed')
    monkeypatch.setattr(game_ratings_builder, 'read_or_materialize', fail)
    with pytest.raises(RuntimeError, match='rating builder failed'):
        game_ratings.get_game_ratings(GAME_ID)
    with pytest.raises(RuntimeError, match='rating builder failed'):
        client.get(f'/api/games/{GAME_ID}/ratings')
