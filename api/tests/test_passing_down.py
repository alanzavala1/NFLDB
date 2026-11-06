"""Official passing-count mapping, source partition checks and unchanged admission."""
import json
from pathlib import Path
import sys

import duckdb
import numpy as np
import pandas as pd
import pytest

from pipeline.passing_down import COUNTS, UNVERIFIED, adapt_passing_down
from pipeline.source_results import SourceError
from splits_core import PLAYER_COLUMNS


def case():
    context = pd.DataFrame([dict(game_id='game',play_id=i,season=2004,season_type='REG',
        down=1 if i<25 else 2,passer_player_id='qb',pass_attempt=1,sack=0,two_point_attempt=0)
        for i in range(50)])
    def row(player,att,cmp,yards,td=0,int_=0,sacks=0):
        return dict(player_id=player,season=2004,season_type='REG',**dict(zip(COUNTS,(att,cmp,yards,td,int_,sacks))))
    whole = pd.DataFrame([row('qb',50,35,400,4,2),row('backup',1,1,14)])
    down = pd.DataFrame([row('qb',25,20,250,3,1),row('qb',25,15,150,1,1),row('backup',1,1,14)])
    down['split_value'] = ['1','2','1']
    return dict(context=context,whole=whole,classified=whole.copy(),excluded=whole.iloc[:0].copy(),
                down=down,weekly=whole.copy(),season=2004)


def test_preview_round_trips_shared_schema_and_keeps_unknowns_null():
    data = case()
    before = {key:value.copy(deep=True) for key,value in data.items() if isinstance(value,pd.DataFrame)}
    rows,report = adapt_passing_down(**data)
    assert tuple(rows) == PLAYER_COLUMNS
    assert rows.player_id.tolist() == ['qb','qb']
    assert rows[['att','cmp','yards','td','interceptions']].sum().tolist() == [50,35,400,4,2]
    assert rows[list(UNVERIFIED)].isna().all().all()
    assert report['publication_ready'] is False and report['status']=='preview_only'
    assert report['qualifying_plays'] == {'qb':50}
    import splits_builder
    with duckdb.connect(':memory:') as conn:
        splits_builder.ensure_table(conn)
        conn.register('preview',rows)
        conn.execute('INSERT INTO player_splits BY NAME SELECT * FROM preview')
        assert conn.execute('SELECT SUM(att),SUM(cmp),SUM(yards) FROM player_splits').fetchone() == (50,35,400)
    for key,frame in before.items():
        pd.testing.assert_frame_equal(frame,data[key])


def test_admission_uses_fresh_legacy_dropbacks_including_sacks_not_export_volume():
    data = case()
    data['context'].loc[49,['pass_attempt','sack']] = [0,1]
    assert adapt_passing_down(**data)[1]['qualifying_plays'] == {'qb':50}
    data['context'] = data['context'].iloc[:-1]
    assert adapt_passing_down(**data)[0].empty  # Large output cannot admit a 49-play source player.


def test_missing_down_keeps_counts_in_whole_and_excluded_reference():
    data = case()
    data['context'].loc[data['context'].down.eq(2),'down'] = np.nan
    data['excluded'] = data['down'].loc[data['down'].split_value.eq('2')].drop(columns='split_value')
    data['down'] = data['down'].loc[data['down'].split_value.eq('1')]
    data['classified'] = data['down'].drop(columns='split_value')
    rows,report = adapt_passing_down(**data)
    assert rows.yards.sum()==250 and report['qualified_excluded_counts']['passing_yards']==150
    assert report['context']['excluded']==25


def test_wholly_unavailable_down_preserves_qualified_whole_production():
    data = case()
    data['context']['down'] = np.nan
    data['excluded'] = data['whole'].copy()
    data['classified'] = data['whole'].iloc[:0].copy()
    data['down'] = data['down'].iloc[:0].copy()
    rows,report = adapt_passing_down(**data)
    assert rows.empty and tuple(rows)==PLAYER_COLUMNS
    assert report['qualified_players']==1 and report['qualified_excluded_counts']['passing_yards']==400


def test_zero_attempt_sack_bucket_and_negative_passing_yards_are_preserved():
    data = case()
    sack = data['down'].iloc[:1].copy()
    sack[list(COUNTS)] = [0,0,0,0,0,3]
    sack['split_value'] = '4'
    data['down'] = pd.concat([data['down'],sack],ignore_index=True)
    sack_plays=data['context'].iloc[:3].copy()
    sack_plays[['play_id','down','pass_attempt','sack']]=[[50,4,0,1],[51,4,0,1],[52,4,0,1]]
    data['context']=pd.concat([data['context'],sack_plays],ignore_index=True)
    for name in ('whole','classified','weekly'):
        data[name].loc[data[name].player_id.eq('qb'),'sacks_suffered'] = 3
    rows,_ = adapt_passing_down(**data)
    assert rows.iloc[-1]['att']==0 and rows.iloc[-1]['epa'] is None
    data = case()
    for name in ('whole','classified','weekly'):
        data[name].loc[data[name].player_id.eq('backup'),'passing_yards'] = -3
    data['down'].loc[data['down'].player_id.eq('backup'),'passing_yards'] = -3
    adapt_passing_down(**data)


@pytest.mark.parametrize('field,value',[
    ('attempts',None),('attempts',float('inf')),('passing_yards',1.5),('sacks_suffered',-1),
    ('attempts',2147483648),('attempts',True),('completions',51),('passing_tds',40),('passing_interceptions',25),
])
def test_bad_counts_cannot_hide_behind_low_volume_admission(field,value):
    data = case()
    data['down'][field] = data['down'][field].astype(object)
    data['down'].loc[data['down'].player_id.eq('backup'),field] = value
    with pytest.raises(SourceError):adapt_passing_down(**data)


@pytest.mark.parametrize('fault', ['duplicate','bucket','post','other_season','weekly','whole','classified','excluded'])
def test_invalid_scope_keys_and_partition_references_fail(fault):
    data = case()
    if fault=='duplicate':data['down']=pd.concat([data['down'],data['down'].iloc[:1]])
    elif fault=='bucket':data['down'].loc[0,'split_value']='5'
    elif fault=='post':data['down'].loc[0,'season_type']='POST'
    elif fault=='other_season':data['down'].loc[0,'season']=2024
    else:
        if fault=='excluded':data[fault]=data['whole'].iloc[:1].copy()
        else:data[fault].loc[0,'passing_yards']+=1
    with pytest.raises(SourceError):adapt_passing_down(**data)


@pytest.mark.parametrize('fault', ['duplicate','nan_key','infinite_key','conversion','flag','blank_passer','post'])
def test_invalid_source_context_fails_before_qualification(fault):
    data = case()
    data['context']['play_id'] = data['context']['play_id'].astype(float)
    if fault=='duplicate':data['context']=pd.concat([data['context'],data['context'].iloc[:1]])
    elif fault=='nan_key':data['context'].loc[0,'play_id']=np.nan
    elif fault=='infinite_key':data['context'].loc[0,'play_id']=np.inf
    elif fault=='conversion':data['context'].loc[0,'two_point_attempt']=1
    elif fault=='flag':data['context'].loc[0,'sack']=7
    elif fault=='blank_passer':data['context'].loc[0,'passer_player_id']=' '
    else:data['context'].loc[0,'season_type']='POST'
    with pytest.raises(SourceError):adapt_passing_down(**data)


@pytest.fixture
def captured(tmp_path,monkeypatch):
    """Only R transport is simulated; actual loader, hashes and adapter run."""
    from pipeline import passing_preview as preview
    from pipeline.source_results import SeasonalFeed
    from tests.passing_cases import metric_case
    data = metric_case(2004)
    weekly = data['weekly'].assign(game_id='game')
    class Inputs:
        def feeds(self,seasons):
            assert seasons==[2004]
            return SeasonalFeed(data['context'],seasons,[]),SeasonalFeed(weekly,seasons,[])
        def receiving_run(self,year):return tmp_path,{},'a'*64
        def revision(self):return 'captured fixture'
    monkeypatch.setattr(preview,'open_core_inputs',lambda path:Inputs())
    monkeypatch.setattr(preview,'_check_environment',lambda *args:None)
    monkeypatch.setattr(preview,'read_export_csv',lambda *args,**kwargs:data['credits'].copy())
    def produce(command,*,cwd,env,logfile):
        output=logfile.parent
        for name in ('context','whole','classified','excluded','down','weekly'):
            frame=data[name][list(preview.CONTEXT)] if name=='context' else data[name]
            frame.to_csv(output/(name+'.csv'),index=False)
        data['context'].to_csv(output/'metric-context.csv',index=False)
        data['credits'].to_csv(output/'metric-credits.csv',index=False)
        (output/'credits.rds').write_bytes(b'captured native credits transport fixture')
        files={p.name:preview.file_sha256(p) for p in output.iterdir()}
        manifest=dict(format_version=2,kind='passing_down_metrics_preview',season=2004,R='4.6.1',
            nflfastR='6.0.0',nflreadr='1.5.1',fresh_credits_match_capture=True,source_run_sha256='a'*64,files=files)
        (output/'run.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(preview,'run_r_export',produce)
    return preview,tmp_path,data


def test_csv_job_has_no_database_output_and_refuses_existing_directory(captured):
    preview,path,_=captured
    output=path/'output'
    report=preview.prepare_passing_preview(path,output,2004,rscript=Path(sys.executable),library=path,log=lambda _:None)
    assert report['rows']==2 and report['publication_ready'] is False
    assert set(output.glob('*.duckdb'))==set()
    assert (output/'canonical-down.csv').exists() and (output/'preview.json').exists()
    before=(output/'preview.json').read_bytes()
    with pytest.raises(FileExistsError):
        preview.prepare_passing_preview(path,output,2004,rscript=Path(sys.executable),library=path)
    assert (output/'preview.json').read_bytes()==before


@pytest.mark.parametrize('fault',['csv_bytes','context_rebound','weekly_rebound','request','policy','runtime','counts',
                                'metric_context_rebound','credit_rebound','model_rebound','credit_scope'])
def test_changed_bound_inputs_or_exported_bytes_never_complete(captured,monkeypatch,fault):
    preview,path,data=captured
    original=preview.run_r_export
    def bad_export(command,**kwargs):
        original(command,**kwargs)
        output=kwargs['logfile'].parent
        manifest=json.loads((output/'run.json').read_text())
        if fault=='csv_bytes':
            with (output/'down.csv').open('ab') as stream:stream.write(b'changed')
        elif fault in ('context_rebound','weekly_rebound','counts','metric_context_rebound','credit_rebound','model_rebound'):
            name={'context_rebound':'context.csv','weekly_rebound':'weekly.csv','counts':'down.csv',
                  'metric_context_rebound':'metric-context.csv','credit_rebound':'metric-credits.csv',
                  'model_rebound':'down.csv'}[fault]
            frame=pd.read_csv(output/name)
            field={'context_rebound':'play_id','metric_context_rebound':'qb_epa',
                   'credit_rebound':'yards','model_rebound':'passing_epa'}.get(fault,'passing_yards')
            frame.loc[0,field]=999
            frame.to_csv(output/name,index=False)
            manifest['files'][name]=preview.file_sha256(output/name)
        elif fault in ('request','policy'):
            name='request.json' if fault=='request' else 'producer.R'
            (output/name).write_text('{}')
            manifest['files'][name]=preview.file_sha256(output/name)
        elif fault=='credit_scope':manifest['credit_match_scope']='ignore mismatches'
        else:manifest['nflfastR']='99.0.0'
        (output/'run.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(preview,'run_r_export',bad_export)
    output=path/'bad-output'
    with pytest.raises(SourceError):
        preview.prepare_passing_preview(path,output,2004,rscript=Path(sys.executable),library=path,log=lambda _:None)
    assert not (output/'preview.json').exists() and not (output/'canonical-down.csv').exists()


def test_new_credits_outside_supplied_plays_do_not_change_a_captured_replay(captured,monkeypatch):
    preview,path,data=captured
    original=preview.run_r_export
    def later_games(command,**kwargs):
        original(command,**kwargs)
        output=kwargs['logfile'].parent
        credits=pd.read_csv(output/'metric-credits.csv')
        newer=credits.iloc[:1].copy().assign(game_id='later-game',play_id=999)
        pd.concat([credits,newer],ignore_index=True).to_csv(output/'metric-credits.csv',index=False)
        manifest=json.loads((output/'run.json').read_text())
        manifest['files']['metric-credits.csv']=preview.file_sha256(output/'metric-credits.csv')
        manifest['credit_match_scope']='supplied REG nonconversion game/play keys'
        (output/'run.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(preview,'run_r_export',later_games)
    report=preview.prepare_passing_preview(path,path/'output',2004,rscript=Path(sys.executable),library=path,log=lambda _:None)
    assert report['rows']==2 and report['credit_match_scope']=='supplied REG nonconversion game/play keys'
