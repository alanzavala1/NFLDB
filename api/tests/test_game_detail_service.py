"""Offline game assembly, optional panels and HTTP/assistant absence handling."""
import json

import duckdb
import pytest

from tests.conftest import _create_schema, _seed
from schemas.schedule import GameDetail
from services import game_detail


@pytest.fixture
def detail_data(monkeypatch):
    import database

    # Reuse the mini-league schema in a fresh connection; never mutate session data.
    with duckdb.connect(':memory:') as conn:
        _create_schema(conn)
        _seed(conn)
        for name, kind in [
            ('total_away_score', 'INTEGER'), ('total_home_score', 'INTEGER'),
            ('home_wp', 'DOUBLE'), ('first_down', 'INTEGER'),
            ('fourth_down_converted', 'INTEGER'), ('fourth_down_failed', 'INTEGER'),
            ('penalty', 'INTEGER'), ('penalty_team', 'VARCHAR'), ('penalty_yards', 'INTEGER'),
            ('sp', 'INTEGER'), ('safety', 'INTEGER'), ('two_point_conv_result', 'VARCHAR'),
        ]:
            conn.execute(f'ALTER TABLE plays ADD COLUMN {name} {kind}')
        conn.execute('DELETE FROM plays')
        conn.execute('''INSERT INTO schedules
            (game_id, season, game_type, week, away_team, home_team, away_score, home_score, overtime)
            VALUES ('detail', 2024, 'REG', 2, 'BUF', 'MIA', 15, 10, 0),
                   ('pre', 2024, 'PRE', 0, 'BUF', 'DEN', 7, 0, 0),
                   ('old', 2023, 'REG', 1, 'BUF', 'MIA', 7, 0, 0),
                   ('partial', 2024, 'REG', 1, 'BUF', 'MIA', 7, NULL, 0),
                   ('future', 2024, 'REG', 4, 'BUF', 'MIA', NULL, NULL, NULL)''')
        conn.execute("UPDATE player_game_stats SET game_id = 'detail', week = 2 WHERE game_id = '2024_01_BUF_MIA'")
        # Latest roster may be elsewhere; the existing team correction uses game stats.
        conn.execute('''INSERT INTO rosters
            (player_id, season, week, team, position, jersey_number, player_name)
            VALUES ('00-BUF-QB1', 2024, 8, 'NYJ', 'QB', 99, 'Josh Allen')''')
        plays = [
            dict(qtr=1, seconds=3000, away=6, home=0, team='BUF', kind='pass', sp=1,
                 touchdown=1, td_team='BUF', desc='BUF touchdown', first_down=1,
                 third_down_converted=1, epa=1.12345, success=1, home_wp=0.1234567),
            dict(qtr=1, seconds=2999, away=7, home=0, team='BUF', kind='extra_point', sp=1,
                 extra_point_result='good'),
            dict(qtr=2, seconds=2000, away=7, home=3, team='MIA', kind='field_goal', sp=1,
                 field_goal_result='made', home_wp=0.6, desc='MIA field goal'),
            dict(qtr=2, seconds=1900, away=9, home=3, team='MIA', kind='run', sp=1,
                 safety=1, defteam='BUF', desc='BUF safety'),
            dict(qtr=3, seconds=1000, away=9, home=9, team='BUF', kind='pass', sp=1,
                 touchdown=1, td_team='MIA', defteam='MIA', interception=1,
                 desc='MIA pick six', third_down_failed=1, epa=-1.11111, success=0),
            dict(qtr=3, seconds=999, away=9, home=10, team='MIA', kind='extra_point', sp=1,
                 extra_point_result='good'),
            dict(qtr=4, seconds=200, away=9, home=10, team='MIA', kind='no_play',
                 penalty=1, penalty_team='MIA', penalty_yards=5),
            dict(qtr=4, seconds=150, away=9, home=10, team='BUF', kind='punt'),
            dict(qtr=4, seconds=100, away=15, home=10, team='BUF', kind='run', sp=1,
                 touchdown=1, td_team='BUF', desc='BUF rushing touchdown',
                 first_down=1, fourth_down_converted=1, epa=2.0, success=1),
            dict(qtr=4, seconds=99, away=15, home=10, team='BUF', kind='two_point', sp=1,
                 two_point_conv_result='failure'),
            dict(qtr=4, seconds=None, away=15, home=10, team=None, kind=None, home_wp=0.9),
        ]
        for play in plays:
            row = {'game_id': 'detail', 'game_seconds_remaining': play.pop('seconds'),
                   'total_away_score': play.pop('away'), 'total_home_score': play.pop('home'),
                   'posteam': play.pop('team'), 'play_type': play.pop('kind'), **play}
            names = ', '.join(f'"{name}"' for name in row)
            placeholders = ', '.join('?' for _ in row)
            conn.execute(f'INSERT INTO plays ({names}) VALUES ({placeholders})', list(row.values()))
        conn.execute('''INSERT INTO plays
            (game_id, qtr, game_seconds_remaining, total_away_score, total_home_score, home_wp, sp, touchdown)
            VALUES ('other-game', 1, 3500, 99, 99, 0.99, 1, 1)''')
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


def _tool():
    import llm

    ctx = llm._Ctx()
    return ctx, next(tool for tool in llm._build_tools(ctx) if tool.name == 'get_game_detail')


def _http_detail(detail):
    return GameDetail.model_validate(detail).model_dump(mode='json')


def _ordered_teams(detail):
    # GROUP BY has no team-row order guarantee; preserve all other list ordering.
    return {**detail, 'team_stats': sorted(detail['team_stats'], key=lambda row: row['team'])}


def test_seeded_game_service_and_http_match(client):
    detail = game_detail.get_game_detail('2024_01_BUF_MIA')
    assert detail['away'][0]['player_name'] == 'Josh Allen'
    assert detail['away'][0]['pass_yards'] == 240
    response = client.get('/api/games/2024_01_BUF_MIA')
    assert response.status_code == 200
    assert _ordered_teams(response.json()) == _ordered_teams(_http_detail(detail))


def test_records_player_team_correction_roster_selection_and_http_parity(client, detail_data):
    detail = game_detail.get_game_detail('detail')
    assert (detail['away_record'], detail['home_record']) == ('1-1', '1-0')
    allen = detail['away'][0]
    assert (allen['player_name'], allen['team'], allen['jersey_number'], allen['pass_yards']) == ('Josh Allen', 'BUF', 99, 240)
    assert [player['player_name'] for player in detail['home']] == ['Tua Tagovailoa', 'Tyreek Hill']
    response = client.get('/api/games/detail')
    assert response.status_code == 200
    assert _ordered_teams(response.json()) == _ordered_teams(_http_detail(detail))


def test_quarter_deltas_and_scoring_fold_pat_with_defensive_scores(detail_data):
    detail = game_detail.get_game_detail('detail')
    assert detail['quarter_scores'] == [
        {'qtr': 1, 'away': 7, 'home': 0}, {'qtr': 2, 'away': 2, 'home': 3},
        {'qtr': 3, 'away': 0, 'home': 7}, {'qtr': 4, 'away': 6, 'home': 0},
    ]
    assert [(row['kind'], row['team'], row['away_score'], row['home_score']) for row in detail['scoring']] == [
        ('TD', 'BUF', 7, 0), ('FG', 'MIA', 7, 3), ('SAF', 'BUF', 9, 3),
        ('TD', 'MIA', 9, 10), ('TD', 'BUF', 15, 10),
    ]
    assert detail['scoring'][0]['desc'] == 'BUF touchdown'


def test_team_conversions_rates_turnovers_and_penalties(detail_data):
    teams = {row['team']: row for row in game_detail.get_game_detail('detail')['team_stats']}
    assert teams['BUF'] == {
        'team': 'BUF', 'plays': 3, 'first_downs': 2, 'third_att': 2, 'third_conv': 1,
        'fourth_att': 1, 'fourth_conv': 1, 'turnovers': 1, 'epa_play': 0.671,
        'success_pct': 66.7, 'penalties': 0, 'penalty_yards': 0,
    }
    assert teams['MIA']['penalties'] == 1 and teams['MIA']['penalty_yards'] == 5


def test_win_probability_filters_rounding_and_order(detail_data):
    rows = game_detail.get_game_detail('detail')['win_prob']
    assert [(row['game_seconds_remaining'], row['home_wp']) for row in rows] == [(3000, 0.1235), (2000, 0.6)]
    assert rows[0]['touchdown'] == 1 and rows[0]['interception'] == 0


def test_assistant_shared_detail_projection_and_provenance(detail_data):
    ctx, tool = _tool()
    raw = tool.func(game_id='detail')
    result = json.loads(raw)
    assert result['game']['overtime'] is False
    assert result['game']['away_record'] == '1-1'
    assert 'roof' not in result['game']
    assert result['quarter_scores'] == game_detail.get_game_detail('detail')['quarter_scores']
    assert [row['player'] for row in result['top_performers']['BUF']] == ['Josh Allen', 'Stefon Diggs']
    assert result['top_performers']['BUF'][0]['pass_yards'] == 240
    assert 'sacks' not in result['top_performers']['BUF'][0]
    assert set(result) == {'game', 'quarter_scores', 'top_performers'}
    assert ctx.calls == [{'tool': 'get_game_detail', 'args': {'game_id': 'detail'}}]
    assert ctx.data == [result['game']] and ctx.raw_results == [raw]


def test_assistant_keeps_five_performers_and_omits_zero_volume_players(detail_data):
    detail_data.executemany('''INSERT INTO player_game_stats
        (game_id, player_id, player_name, season, week, team, rush_yards)
        VALUES ('detail', ?, ?, 2024, 2, 'BUF', ?)''', [
        (f'runner-{i}', f'Runner {i}', 50 + i) for i in range(6)
    ] + [('zero', 'Zero Volume', 0)])
    _, tool = _tool()
    result = json.loads(tool.func(game_id='detail'))
    assert [row['player'] for row in result['top_performers']['BUF']] == [
        'Josh Allen', 'Stefon Diggs', 'Runner 5', 'Runner 4', 'Runner 3',
    ]


@pytest.mark.parametrize('game_id', ['missing', '2024_01_MIA_BUF'])
def test_missing_domain_game_preserves_http_and_assistant_messages(client, detail_data, game_id):
    assert game_detail.get_game_detail(game_id) is None
    response = client.get(f'/api/games/{game_id}')
    assert response.status_code == 404
    assert response.json() == {'detail': f'Game {game_id} not found'}
    ctx, tool = _tool()
    raw = tool.func(game_id=game_id)
    assert raw == 'No game found for that game_id.'
    assert ctx.calls == [{'tool': 'get_game_detail', 'args': {'game_id': game_id}}]
    assert ctx.data == [] and ctx.raw_results == [raw]


def test_missing_game_stops_before_other_queries(monkeypatch):
    calls = []
    def empty(sql, params):
        calls.append(params)
        assert len(calls) == 1
        return []
    monkeypatch.setattr(game_detail, 'query_to_dict', empty)
    assert game_detail.get_game_detail('missing') is None
    assert calls == [['missing']]


def test_unplayed_game_with_no_stats_or_plays_is_valid(client, detail_data):
    detail = game_detail.get_game_detail('future')
    assert detail['away_score'] is None and detail['home_score'] is None
    assert all(detail[key] == [] for key in ('away', 'home', 'quarter_scores', 'win_prob', 'team_stats', 'scoring'))
    response = client.get('/api/games/future')
    assert response.status_code == 200 and response.json() == _http_detail(detail)


def test_missing_play_table_retains_logged_optional_panel_fallback(client, detail_data, caplog):
    detail_data.execute('DROP TABLE plays')
    detail = game_detail.get_game_detail('detail')
    assert detail['away'][0]['pass_yards'] == 240
    assert all(detail[key] == [] for key in ('quarter_scores', 'win_prob', 'team_stats', 'scoring'))
    assert 'safe_query failed, returning []' in caplog.text
    response = client.get('/api/games/detail')
    assert response.status_code == 200 and response.json() == _http_detail(detail)


@pytest.mark.parametrize('stage', [1, 2, 3])
def test_required_query_failures_propagate_through_all_callers(client, detail_data, monkeypatch, stage):
    original = game_detail.query_to_dict
    _, tool = _tool()
    for action in [
        lambda: game_detail.get_game_detail('detail'),
        lambda: client.get('/api/games/detail'),
        lambda: tool.func(game_id='detail'),
    ]:
        calls = []
        def fail_at(sql, params):
            calls.append(sql)
            if len(calls) == stage:
                raise RuntimeError('game storage failed')
            return original(sql, params)
        monkeypatch.setattr(game_detail, 'query_to_dict', fail_at)
        with pytest.raises(RuntimeError, match='game storage failed'):
            action()
