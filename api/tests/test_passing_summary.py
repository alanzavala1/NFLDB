"""Summary ingredients use model populations, not rounded attempt averages."""
import numpy as np
import pandas as pd
import pytest

from pipeline.passing_down import COUNTS
from pipeline.passing_summary import prepare_passing_summary
from tests.passing_cases import metric_case


def whole(data):
    columns = [*COUNTS, 'passing_first_downs', 'passing_air_yards',
               'passing_yards_after_catch', 'passing_epa']
    result = data['down'].groupby(['player_id', 'season', 'season_type'], as_index=False)[columns].sum()
    model = data['context'].loc[data['context'].play_type.isin(['pass', 'qb_spike'])]
    result['passing_cpoe'] = result.player_id.map(model.groupby('passer_player_id').cpoe.mean())
    return result


def test_whole_cpoe_uses_modeled_observations_and_preserves_precise_components():
    data = metric_case()
    context = data['context']
    context['cpoe'] = np.nan
    context.loc[[0, 1], 'cpoe'] = 1.0
    context.loc[context.down.eq(2), 'cpoe'] = 9.0
    report = prepare_passing_summary(whole(data), context, data['credits'], 2024, ['qb'])
    row, = report['rows']
    parts, = report['metric_availability']['aggregation']
    assert [row[key] for key in ('att', 'cmp', 'yards', 'first_downs')] == [50, 35, 400, 17]
    assert row['cpoe'] == 8.41  # (2 * 1 + 25 * 9) / 27, not (1 + 9) / 2.
    assert parts['cpoe_count'] == 27 and parts['cpoe_sum'] == 227
    assert parts['epa_sum'] == 2.5 and parts['successes'] == 35
    assert row['epa'] == .05 and row['success_pct'] == 70


def test_independent_whole_summary_keeps_plays_with_missing_down():
    data = metric_case()
    data['context']['down'] = np.nan
    report = prepare_passing_summary(whole(data), data['context'], data['credits'], 2024, ['qb'])
    row, = report['rows']
    assert row['att'] == 50 and row['yards'] == 400 and row['epa'] == .05
    assert row['split_dim'] == 'overall' and row['split_value'] == 'all'


@pytest.mark.parametrize('field,component', [('qb_epa', 'epa_sum'), ('epa', 'successes')])
def test_missing_inputs_stay_unknown_in_summary_components(field, component):
    data = metric_case()
    data['context'].loc[0, field] = np.nan
    if field == 'qb_epa': data['down'].loc[0, 'passing_epa'] -= .5
    report = prepare_passing_summary(whole(data), data['context'], data['credits'], 2024, ['qb'])
    parts, = report['metric_availability']['aggregation']
    assert parts[component] is None
    assert parts['cpoe_count'] > 0


def test_whole_summary_preserves_per_play_attribution_disagreement_even_when_totals_match():
    data = metric_case(2004)
    data['credits'].loc[[0, 1], 'yards'] = [10, 60]
    report = prepare_passing_summary(whole(data), data['context'], data['credits'], 2004, ['qb'])
    row, = report['rows']
    parts, = report['metric_availability']['aggregation']
    assert row['yards'] == 400 and row['first_downs'] == 17
    assert all(row[field] is None for field in ['epa', 'success_pct', 'cpoe', 'air_yards', 'yac'])
    assert all(parts[field] is None for field in ['epa_sum', 'successes', 'cpoe_sum', 'cpoe_count'])
