"""Count/model population disagreements must only mask the affected metrics."""
import numpy as np
import pandas as pd
import pytest

from pipeline.passing_down import adapt_passing_down
from pipeline.passing_metrics import apply_passing_metrics, verify_passing_first_downs
from pipeline.source_results import SourceError
from tests.passing_cases import metric_case


def adapt(data):
    rows, _ = adapt_passing_down(**{k:v for k,v in data.items() if k != 'credits'})
    return apply_passing_metrics(rows, data['down'], data['context'], data['credits'], data['season'])


def test_verified_metrics_match_known_formulas_and_inputs_are_unchanged():
    data = metric_case()
    before = {k:v.copy(deep=True) for k,v in data.items() if isinstance(v,pd.DataFrame)}
    rows, report = adapt(data)
    assert rows[['epa','success_pct','cpoe']].values.tolist() == [[0.2,80.0,4.0],[-0.1,60.0,4.0]]
    assert rows[['air_yards','yac','first_downs']].values.tolist() == [[220,80,10],[190,60,7]]
    assert report['attribution_mismatch_player_buckets'] == [] and report['unavailable'] == []
    for k,v in before.items(): pd.testing.assert_frame_equal(v,data[k])


def test_historical_air_and_yac_unavailable_without_losing_first_downs_or_rates():
    data = metric_case(2004)
    rows, report = adapt(data)
    assert rows[['air_yards','yac']].isna().all().all()
    assert rows[['first_downs','epa','success_pct','cpoe']].notna().all().all()
    assert report['available_rows']['first_downs'] == 2


def test_two_passers_on_one_play_only_mask_the_affected_bucket_and_keep_counts():
    data = metric_case()
    # The original PBP identity cannot represent both passes; give one known
    # completion's detailed credit to an additional passer, like the real case.
    data['credits'].loc[0,'gsis_player_id'] = 'other'
    raw = data['down'].iloc[:1].copy()
    raw['player_id'] = 'other'
    raw[list(('attempts','completions','passing_yards','passing_tds','passing_interceptions','sacks_suffered'))] = [1,1,60,1,0,0]
    raw[['passing_first_downs','passing_epa','passing_cpoe']] = [1,np.nan,np.nan]
    data['down'] = pd.concat([data['down'],raw],ignore_index=True)
    data['down'].loc[0,['attempts','completions','passing_yards','passing_tds','passing_first_downs']] = [24,19,190,2,9]
    for name in ('whole','classified','weekly'):
        data[name].loc[data[name].player_id.eq('qb'),['attempts','completions','passing_yards','passing_tds']] = [49,34,340,3]
        extra = data[name].iloc[:1].copy().assign(player_id='other')
        extra[['attempts','completions','passing_yards','passing_tds','passing_interceptions','sacks_suffered']] = [1,1,60,1,0,0]
        data[name] = pd.concat([data[name],extra],ignore_index=True)
    rows, report = adapt(data)
    assert rows.iloc[0][['att','cmp','yards','first_downs']].tolist() == [24,19,190,9]
    assert rows.iloc[0][['epa','success_pct','cpoe','air_yards','yac']].isna().all()
    assert rows.iloc[1][['epa','success_pct','cpoe','air_yards','yac']].notna().all()
    assert report['attribution_mismatch_player_buckets'] == [dict(player_id='other',split_value='1'),dict(player_id='qb',split_value='1')]


@pytest.mark.parametrize('field,masked', [('qb_epa',['epa']),('epa',['success_pct']),
                                        ('air_yards',['air_yards','yac'])])
def test_missing_input_masks_only_its_dependent_metrics(field,masked):
    data = metric_case()
    data['context'].loc[0,field] = np.nan
    if field == 'qb_epa':data['down'].loc[0,'passing_epa'] -= 0.5
    rows,_ = adapt(data)
    assert rows.iloc[0][masked].isna().all()
    untouched = set(['epa','success_pct','cpoe','air_yards','yac','first_downs']) - set(masked)
    assert rows.iloc[0][list(untouched)].notna().all()
    assert rows.iloc[1][list(untouched)].notna().all()


def test_cpoe_uses_only_modeled_passes_and_is_unknown_without_observations():
    data = metric_case()
    data['context'].loc[data['context'].down.eq(1),'cpoe'] = np.nan
    data['down'].loc[data['down'].split_value.eq('1'),'passing_cpoe'] = np.nan
    rows,_ = adapt(data)
    assert pd.isna(rows.iloc[0].cpoe) and rows.iloc[0].epa == 0.2 and rows.iloc[1].cpoe == 4


@pytest.mark.parametrize('field,value', [('passing_epa',123),('passing_cpoe',9),
    ('passing_first_downs',21),('passing_air_yards',float('inf')),('passing_yards_after_catch',1.5),
    ('passing_first_downs',True),('passing_first_downs',-1)])
def test_bad_native_metrics_fail_before_admission(field,value):
    data = metric_case()
    data['down'][field] = data['down'][field].astype(object)
    data['down'].loc[2,field] = value  # Low-volume backup cannot hide bad data.
    with pytest.raises((SourceError,ValueError)):adapt(data)


@pytest.mark.parametrize('field,value', [('qb_epa',float('inf')),('cpoe',101),('complete_pass',4),('air_yards',1.5)])
def test_bad_metric_context_is_rejected(field,value):
    data = metric_case()
    data['context'][field] = data['context'][field].astype(object)
    data['context'].loc[0,field] = value
    with pytest.raises((SourceError,ValueError)):adapt(data)


def test_rebound_credit_counts_cannot_change_a_native_export():
    data = metric_case()
    data['credits'].loc[0,'yards'] += 1
    with pytest.raises(SourceError,match='projection differs'):adapt(data)


def test_sack_only_bucket_keeps_counts_and_cpoe_unknown_instead_of_zero():
    data = metric_case()
    sack = data['context'].iloc[:1].copy()
    sack[['play_id','down','complete_pass','incomplete_pass','interception','sack','passing_yards',
          'pass_touchdown','first_down','qb_epa','epa','cpoe','air_yards','yards_after_catch']] = [
          60,4,0,0,0,1,np.nan,0,0,-2,-2,np.nan,np.nan,np.nan]
    data['context'] = pd.concat([data['context'],sack],ignore_index=True)
    credit = data['credits'].iloc[:1].copy()
    credit[['play_id','stat_id','yards']] = [60,20,7]
    data['credits'] = pd.concat([data['credits'],credit],ignore_index=True)
    source = data['down'].iloc[:1].copy()
    source[['split_value','attempts','completions','passing_yards','passing_tds','passing_interceptions',
            'sacks_suffered','passing_air_yards','passing_yards_after_catch','passing_first_downs',
            'passing_epa','passing_cpoe']] = ['4',0,0,0,0,0,1,0,0,0,-2,np.nan]
    data['down'] = pd.concat([data['down'],source],ignore_index=True)
    for name in ('whole','classified','weekly'):
        data[name].loc[data[name].player_id.eq('qb'),'sacks_suffered'] = 1
    rows,report = adapt(data)
    row=rows.iloc[-1]
    assert row.att == 0 and row.yards == 0 and row.first_downs == 0
    assert row[['epa','success_pct','cpoe']].isna().all()
    parts = next(item for item in report['aggregation'] if item['split_value'] == '4')
    assert parts['epa_sum'] == -2 and parts['successes'] == 0
    assert parts['cpoe_sum'] == 0 and parts['cpoe_count'] == 0


def test_a_real_zero_epa_is_available_but_all_missing_epa_is_unknown():
    data = metric_case()
    data['context'].loc[data['context'].down.eq(1),'qb_epa'] = 0
    data['down'].loc[data['down'].split_value.eq('1'),'passing_epa'] = 0
    assert adapt(data)[0].iloc[0].epa == 0
    data['context'].loc[data['context'].down.eq(1),'qb_epa'] = np.nan
    assert pd.isna(adapt(data)[0].iloc[0].epa)


def test_cpoe_ignores_nonmodeled_play_types_as_the_official_calculator_does():
    data=metric_case()
    data['context'].loc[1,['play_type','cpoe']] = ['no_play',99]
    data['down'].loc[0,'passing_epa'] -= 0.5
    rows,_=adapt(data)
    assert rows.iloc[0].cpoe == 4 and rows.iloc[0].epa == 0.18


def test_air_and_yac_disagreements_do_not_discard_other_valid_metrics():
    data=metric_case()
    data['down'].loc[0,['passing_air_yards','passing_yards_after_catch']] += 1
    rows,_=adapt(data)
    assert rows.iloc[0][['air_yards','yac']].isna().all()
    assert rows.iloc[0][['epa','success_pct','cpoe','first_downs']].notna().all()


def test_passing_yac_uses_verified_decomposition_independent_of_receiver_yac():
    data=metric_case()
    data['context']['yards_after_catch'] = np.nan
    rows,_=adapt(data)
    assert rows.yac.tolist() == [80,60]
    data['context'].loc[0,'yards_after_catch'] = -19
    assert adapt(data)[0].yac.tolist() == [80,60]


def test_equal_bucket_totals_cannot_hide_per_play_credit_disagreement():
    data=metric_case()
    data['credits'].loc[[0,1],'yards'] = [10,60]
    rows,report=adapt(data)
    assert rows.iloc[0][['att','cmp','yards']].tolist() == [25,20,250]
    assert rows.iloc[0][['epa','success_pct','cpoe','air_yards','yac']].isna().all()
    assert rows.iloc[1].epa == -0.1
    assert report['attribution_mismatch_player_buckets'] == [dict(player_id='qb',split_value='1')]


def test_unavailable_down_has_empty_output_and_no_invented_metric_values():
    data=metric_case()
    data['context']['down'] = np.nan
    data['excluded'] = data['whole'].copy()
    data['classified'] = data['whole'].iloc[:0].copy()
    data['down'] = data['down'].iloc[:0].copy()
    rows,report=adapt(data)
    assert rows.empty and not any(report['available_rows'].values())


def test_unidentified_model_aggregate_is_checked_but_never_admitted():
    data=metric_case()
    unknown=data['context'].iloc[:1].copy()
    unknown[['play_id','passer_player_id','complete_pass','incomplete_pass','interception',
             'pass_attempt','passing_yards','pass_touchdown','first_down','qb_epa','epa','cpoe']] = [
             70,pd.NA,0,0,0,0,np.nan,0,0,-3,-3,np.nan]
    data['context']=pd.concat([data['context'],unknown],ignore_index=True)
    raw=data['down'].iloc[:1].copy()
    raw['player_id']=pd.NA
    from pipeline.passing_down import COUNTS
    raw[list(COUNTS)]=0
    raw[['passing_air_yards','passing_yards_after_catch','passing_first_downs','passing_epa','passing_cpoe']] = [0,0,0,-3,np.nan]
    data['down']=pd.concat([data['down'],raw],ignore_index=True)
    rows,_=adapt(data)
    assert rows.player_id.tolist()==['qb','qb']
    data['down'].loc[data['down'].player_id.isna(),'passing_epa']=-4
    with pytest.raises(SourceError,match='model population'):adapt(data)


@pytest.mark.parametrize('fault',[None,'weekly','down','excluded','fraction','negative','impossible','missing'])
def test_first_downs_match_weekly_counts_and_all_source_partitions(fault):
    data=metric_case()
    frames={name:data[name] for name in ('whole','classified','excluded','down')}
    if fault in ('weekly','down'):data[fault].loc[0,'passing_first_downs']-=1
    elif fault=='excluded':frames['excluded']=data['whole'].iloc[:1].copy()
    elif fault=='fraction':frames['down']['passing_first_downs']=frames['down'].passing_first_downs.astype(float)+0.5
    elif fault=='negative':frames['down'].loc[0,'passing_first_downs']=-1
    elif fault=='impossible':frames['down'].loc[0,'passing_first_downs']=999
    elif fault=='missing':frames['down']=frames['down'].drop(columns='passing_first_downs')
    if fault:
        with pytest.raises(SourceError):verify_passing_first_downs(frames,data['weekly'],2024)
    else:verify_passing_first_downs(frames,data['weekly'],2024)
