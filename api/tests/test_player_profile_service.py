"""Shared profile composition and HTTP/assistant missing-player handling."""
import pytest

from schemas.players import PlayerProfile
from services import player_profile, player_snaps


def test_seeded_profile_totals_log_and_http_parity(client):
    profile = player_profile.get_player_profile('00-BUF-QB1')
    assert profile['games_played'] == 3 and profile['season_totals']['pass_yards'] == 880
    assert [game['week'] for game in profile['games']] == [1, 2, 3]
    response = client.get('/api/players/00-BUF-QB1')
    assert response.status_code == 200
    assert response.json() == PlayerProfile.model_validate(profile).model_dump(mode='json')


@pytest.mark.parametrize('name', ['get_player_game_log', 'get_player_career', 'get_player_overview'])
def test_absence_matches_service_http_and_all_assistant_callers(client, name):
    import llm

    player_id = '00-9999999'
    assert player_profile.get_player_profile(player_id) is None
    response = client.get(f'/api/players/{player_id}')
    assert response.status_code == 404 and response.json() == {'detail': f'Player {player_id} not found'}
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == name)
    args = {'player_id': player_id}
    if name != 'get_player_career':
        args['season'] = 2024
    raw = tool.func(**args)
    assert raw == 'No player found for that id.'
    assert ctx.calls == [{'tool': name, 'args': args}]
    assert ctx.raw_results == [raw]


def test_unexpected_profile_lookup_error_is_not_a_missing_player(client, monkeypatch):
    def fail(*args):
        raise RuntimeError('profile storage failed')
    monkeypatch.setattr(player_profile, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='profile storage failed'):
        client.get('/api/players/00-9999999')


def test_identity_prefers_existing_max_id_and_missing_player_is_empty(client):
    identity = player_snaps._pfr_identity('00-BUF-QB1')
    assert identity[1] == 'Josh Allen'
    assert player_snaps._pfr_identity('missing') == (None, None)
    assert player_snaps._get_snap_totals('missing') == {}
    assert player_snaps._get_snap_first_games('missing') == []
