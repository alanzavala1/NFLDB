"""Reviewed real plays exercise the isolated prototype, without network or DB files."""
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from experiments.receiving_credits import METRICS, receiving_player_plays, receiving_splits


CASES = json.loads((Path(__file__).parent / 'fixtures' / 'receiving_credit_cases.json').read_text())['cases']


def frames(case):
    context = case['play']
    credits = [{**row, 'game_id': context['game_id'], 'play_id': context['play_id']}
               for row in case['credits']]
    return pd.DataFrame([context]), pd.DataFrame(credits)


@pytest.fixture(params=CASES, ids=lambda case: case['name'])
def case(request):
    return request.param


def test_reviewed_player_play_credits(case):
    result = receiving_player_plays(*frames(case))
    assert result[['player_id', *METRICS]].to_dict('records') == case['expected_receiving']
    assert not result.duplicated(['game_id', 'play_id', 'player_id']).any()


@pytest.mark.parametrize('dimension,context_field', [('down', 'down'), ('quarter', 'qtr')])
def test_reviewed_credits_land_in_correct_split(case, dimension, context_field):
    result = receiving_splits(receiving_player_plays(*frames(case)), dimension)
    expected_value = case['play'][context_field]
    expected = []
    if expected_value is not None:
        label = 'OT' if dimension == 'quarter' and expected_value > 4 else str(int(expected_value))
        expected = [{'player_id': row['player_id'], 'split_dim': dimension,
                     'split_value': label, **{metric: row[metric] for metric in METRICS}}
                    for row in case['expected_receiving']]
    assert result[['player_id', 'split_dim', 'split_value', *METRICS]].to_dict('records') == expected


def test_gibbs_two_plays_keep_41_yards_without_extra_targets_or_catches():
    gibbs = [case for case in CASES if case['name'].startswith('gibbs_')]
    paired = [frames(case) for case in gibbs]
    result = receiving_player_plays(pd.concat([p for p, _ in paired]), pd.concat([c for _, c in paired]))
    player = result[result.player_id == '00-0039139']
    assert player[list(METRICS)].sum().to_dict() == {
        'target_credits': 0, 'receptions': 0, 'receiving_yards': 41, 'receiving_tds': 1,
    }
    down = receiving_splits(result, 'down')
    assert down[down.player_id == '00-0039139'].receiving_yards.sum() == 41


def test_same_play_id_in_two_games_does_not_cross_join():
    first = deepcopy(CASES[0])
    second = deepcopy(first)
    second['play'].update(game_id='2024_02_ARI_LA', down=4)
    paired = [frames(case) for case in (first, second)]
    result = receiving_player_plays(pd.concat([p for p, _ in paired]), pd.concat([c for _, c in paired]))
    assert result[['game_id', 'receptions', 'receiving_yards']].to_dict('records') == [
        {'game_id': '2024_01_ARI_BUF', 'receptions': 1, 'receiving_yards': 9},
        {'game_id': '2024_02_ARI_LA', 'receptions': 1, 'receiving_yards': 9},
    ]
    assert receiving_splits(result, 'down')[['split_value', 'receiving_yards']].to_dict('records') == [
        {'split_value': '1', 'receiving_yards': 9}, {'split_value': '4', 'receiving_yards': 9},
    ]


def test_duplicate_context_fails_before_credits_can_multiply():
    plays, credits = frames(CASES[0])
    with pytest.raises(ValueError, match='duplicate or missing'):
        receiving_player_plays(pd.concat([plays, plays]), credits)


@pytest.mark.parametrize('column', ['game_id', 'play_id', 'season'])
def test_missing_play_identity_or_season_fails(column):
    plays, credits = frames(CASES[0])
    plays[column] = None
    with pytest.raises(ValueError, match='duplicate or missing'):
        receiving_player_plays(plays, credits)


@pytest.mark.parametrize('invalid', [None, float('inf'), float('nan')])
def test_invalid_yard_credit_fails_instead_of_becoming_zero(invalid):
    plays, credits = frames(CASES[0])
    credits['yards'] = credits.yards.astype(float)
    credits.loc[credits.stat_id == 21, 'yards'] = invalid
    with pytest.raises(ValueError, match='missing or nonfinite receiving yardage'):
        receiving_player_plays(plays, credits)


def test_conversion_and_postseason_context_excluded_even_with_ordinary_credit_records():
    plays, credits = frames(CASES[0])
    plays['two_point_attempt'] = 1
    assert receiving_player_plays(plays, credits).empty
    plays['two_point_attempt'] = 0
    plays['season_type'] = 'POST'
    assert receiving_player_plays(plays, credits).empty


def test_unidentified_credits_do_not_create_an_unknown_player_total():
    plays, credits = frames(CASES[0])
    credits['gsis_player_id'] = None
    assert receiving_player_plays(plays, credits).empty


def test_missing_down_preserves_play_total_and_quarter_split():
    plays, credits = frames(CASES[0])
    plays['down'] = None
    player_plays = receiving_player_plays(plays, credits)
    assert player_plays.receiving_yards.sum() == 9
    assert receiving_splits(player_plays, 'down').empty
    assert receiving_splits(player_plays, 'quarter').receiving_yards.sum() == 9


def test_overtime_quarters_share_existing_ot_bucket():
    plays, credits = frames(CASES[0])
    plays['qtr'] = 5
    result = receiving_splits(receiving_player_plays(plays, credits), 'quarter')
    assert result[['split_value', 'sort_order', 'receiving_yards']].to_dict('records') == [
        {'split_value': 'OT', 'sort_order': 5, 'receiving_yards': 9},
    ]


@pytest.mark.parametrize('input_name,missing', [('plays', 'down'), ('credits', 'stat_id')])
def test_missing_input_columns_fail_clearly(input_name, missing):
    plays, credits = frames(CASES[0])
    if input_name == 'plays':
        plays = plays.drop(columns=missing)
    else:
        credits = credits.drop(columns=missing)
    with pytest.raises(ValueError, match=f'{input_name}: missing columns'):
        receiving_player_plays(plays, credits)


def test_target_depth_is_not_inferred_for_lateral_recipients():
    with pytest.raises(ValueError, match='dimension must be down or quarter'):
        receiving_splits(receiving_player_plays(*frames(CASES[0])), 'target_depth')
