"""Shared passing classification, full-view exports and source corruption guards."""
import json
from pathlib import Path
import sys

import pandas as pd
import pytest

from pipeline.passing_dimensions import DIMENSIONS
from pipeline.passing_down import COUNTS, adapt_passing_partition
from pipeline.passing_metrics import METRIC_CONTEXT, apply_passing_metrics, verify_passing_first_downs
from pipeline.source_results import SeasonalFeed, SourceError
from tests.passing_cases import VIEW_LABELS, view_case


@pytest.mark.parametrize('dimension',list(DIMENSIONS))
@pytest.mark.parametrize('year',[2004,2024])
def test_every_partition_preserves_counts_or_records_wholly_excluded_production(dimension,year):
    data,labels=view_case(dimension,year)
    frames={name:data[name] for name in ('whole','classified','excluded','down')}
    rows,report=adapt_passing_partition(context=data['context'],weekly=data['weekly'],season=year,
                                       dimension=dimension,**frames)
    verify_passing_first_downs(frames,data['weekly'],year)
    rows,metrics=apply_passing_metrics(rows,data['down'],data['context'],data['credits'],year,dimension=dimension)
    if labels.isna().all():
        assert rows.empty and report['qualified_excluded_counts']['passing_yards']==400
        assert not any(metrics['available_rows'].values())
    else:
        assert rows.split_dim.tolist()==[dimension,dimension]
        assert rows.split_value.tolist()==list(VIEW_LABELS[dimension])
        assert rows[['att','cmp','yards','first_downs']].sum().tolist()==[50,35,400,17]
        assert rows.epa.tolist()==[.2,-.1]
        if dimension=='opponent':assert rows.sort_order.isna().all()
        else:assert rows.sort_order.notna().all()


@pytest.fixture
def full_export(tmp_path,monkeypatch):
    from pipeline import passing_preview as preview,passing_exports as exports
    data,_=view_case('down')
    source=tmp_path/'source';source.mkdir()
    class Inputs:
        def feeds(self,seasons):
            assert seasons==[2024]
            return SeasonalFeed(data['context'],seasons,[]),SeasonalFeed(data['weekly'].assign(game_id='game',week=1),seasons,[])
        def receiving_run(self,year):return source,{},'a'*64
        def revision(self):return 'captured full-view fixture'
    inputs=Inputs()
    monkeypatch.setattr(preview,'open_core_inputs',lambda _:inputs)
    monkeypatch.setattr(preview,'_check_environment',lambda *args:None)
    def capture(directory,manifest,name,**kwargs):
        return data['credits'].copy() if name.startswith('credits-') else data['context'].copy()
    monkeypatch.setattr(preview,'read_export_csv',capture)
    monkeypatch.setattr(exports,'read_export_csv',capture)
    monkeypatch.setattr(exports,'verify_receiving_inputs',lambda *args:{'status':'loaded','rows':51})
    def produce(command,*,cwd,env,logfile):
        output=logfile.parent;request=json.loads((output/'request.json').read_text())
        data['whole'].to_csv(output/'whole.csv',index=False)
        data['whole'][['player_id','season','season_type',*COUNTS]].to_csv(output/'weekly.csv',index=False)
        data['context'][list(preview.CONTEXT)].to_csv(output/'context.csv',index=False)
        data['context'][list(METRIC_CONTEXT)].to_csv(output/'metric-context.csv',index=False)
        data['credits'].to_csv(output/'metric-credits.csv',index=False)
        (output/'credits.rds').write_bytes(b'native R transport fixture')
        for dimension in request['dimensions']:
            d,labels=view_case(dimension)
            for name in ('classified','excluded'):d[name].to_csv(output/f'{name}-{dimension}.csv',index=False)
            d['down'].to_csv(output/f'{dimension}.csv',index=False)
            d['context'][['game_id','play_id']].assign(split_value=labels).to_csv(output/f'membership-{dimension}.csv',index=False)
        files={p.name:preview.file_sha256(p) for p in output.iterdir()}
        (output/'run.json').write_text(json.dumps(dict(format_version=3,kind='passing_splits_preview',season=2024,
            dimensions=request['dimensions'],R='4.6.1',nflfastR='6.0.0',nflreadr='1.5.1',
            source_run_sha256='a'*64,fresh_credits_match_capture=True,
            credit_match_scope='supplied REG nonconversion game/play keys',files=files)))
    monkeypatch.setattr(preview,'run_r_export',produce)
    return preview,exports,tmp_path,inputs


def prepare(full_export,dimensions=None,name='output'):
    preview,_,path,_=full_export
    return preview.prepare_passing_preview(path,path/name,2024,rscript=Path(sys.executable),library=path,
                                          dimensions=list(DIMENSIONS) if dimensions is None else dimensions,log=lambda _:None)


def test_complete_export_has_all_views_and_replays_identically(full_export):
    _,exports,path,inputs=full_export
    report=prepare(full_export)
    assert len(report['dimensions'])==17 and report['rows']==34 and not report['publication_ready']
    replay=exports.load_passing_season(path/'output',inputs,2024)
    assert len(replay.rows)==17 and replay.report['admission']['qualifying_plays']=={'qb':50}
    assert (path/'output/canonical-splits.csv').exists() and not list(path.rglob('*.duckdb'))


def test_subset_is_useful_for_diagnostics_but_cannot_enter_a_build(full_export):
    _,exports,path,inputs=full_export
    assert prepare(full_export,['quarter'])['rows']==2
    with pytest.raises(SourceError,match='every passing dimension'):
        exports.load_passing_season(path/'output',inputs,2024)


@pytest.mark.parametrize('fault',['membership','counts','first_downs','metric','policy','request','dimensions','bytes'])
def test_rebound_or_corrupted_native_exports_do_not_complete(full_export,monkeypatch,fault):
    preview,_,path,_=full_export
    original=preview.run_r_export
    def corrupt(command,**kwargs):
        original(command,**kwargs)
        output=kwargs['logfile'].parent;m=json.loads((output/'run.json').read_text())
        name={'membership':'membership-quarter.csv','counts':'quarter.csv','first_downs':'quarter.csv',
              'metric':'quarter.csv','policy':'producer.R','request':'request.json','bytes':'quarter.csv'}.get(fault)
        if fault=='dimensions':m['dimensions']=['down']
        elif fault=='policy':(output/name).write_text('changed producer')
        elif fault=='request':
            request=json.loads((output/name).read_text());request['source_run_sha256']='b'*64;(output/name).write_text(json.dumps(request))
        else:
            frame=pd.read_csv(output/name)
            field={'membership':'split_value','counts':'passing_yards','first_downs':'passing_first_downs',
                   'metric':'passing_epa','bytes':'passing_yards'}[fault]
            frame.loc[0,field]=999;frame.to_csv(output/name,index=False)
        if name and fault!='bytes':m['files'][name]=preview.file_sha256(output/name)
        (output/'run.json').write_text(json.dumps(m))
    monkeypatch.setattr(preview,'run_r_export',corrupt)
    with pytest.raises((SourceError,ValueError)):prepare(full_export)
    assert not (path/'output/preview.json').exists() and not (path/'output/canonical-splits.csv').exists()


@pytest.mark.parametrize('relocate',[False,True])
def test_unchanged_season_export_can_be_reused_when_the_outer_collection_changes(full_export,monkeypatch,relocate):
    _,exports,path,inputs=full_export
    prepare(full_export)
    original=inputs.revision()
    monkeypatch.setattr(inputs,'revision',lambda:'new collection with another season refreshed')
    if relocate:
        monkeypatch.setattr(inputs,'receiving_run',lambda year:(path/'restored-source',{},'a'*64))
    replay=exports.load_passing_season(path/'output',inputs,2024)
    assert replay.report['export_core_revision']==original
    assert replay.report['core_revision']==inputs.revision()
    assert replay.report['rows']==34
