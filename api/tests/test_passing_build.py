"""Atomic native-passing build integration and exact source replay controls."""
import json
import duckdb
import pytest

import splits_builder
from pipeline import passing_build
from pipeline.passing_inputs import PassingInputs, assemble_passing_inputs
from pipeline.passing_validation import validate_passing
from pipeline.source_results import SourceError
from pipeline.validation import SnapshotValidationError, validate_snapshot
from tests.test_passing_partitions import full_export, prepare


@pytest.fixture
def candidate(full_export,monkeypatch):
    _,_,path,core=full_export
    prepare(full_export)
    index=assemble_passing_inputs([path/'output'],path/'passing-index',core,log=lambda _:None)
    plays,weekly=core.feeds([2024])
    for name,value in dict(week=1,rusher_player_id='runner',rush_attempt=1,run_gap='guard',
                           run_location='left',rushing_yards=3,rush_touchdown=0).items():
        plays.data[name]=value
    c=duckdb.connect(':memory:')
    c.register('captured_plays',plays.data);c.execute('CREATE TABLE plays AS SELECT * FROM captured_plays')
    c.register('captured_weekly',weekly.data);c.execute('CREATE TABLE weekly_player_stats AS SELECT * FROM captured_weekly')
    splits_builder.ensure_table(c)
    c.execute("""INSERT INTO player_splits(player_id,season,category,split_dim,split_value,att,cmp,yards,td)
        VALUES ('old',2024,'passing','down','1',1,1,999,0),('older',1998,'passing','down','1',1,1,12,0)""")
    monkeypatch.setattr(splits_builder,'get_connection',lambda:c)
    monkeypatch.setattr('pipeline.receiving_build.prepare_receiving',lambda *args:object())
    def receiving(conn,year,prepared):
        conn.execute("""INSERT INTO player_splits(player_id,season,category,split_dim,split_value,att,cmp,yards,td)
            VALUES ('receiver',?,'receiving','down','1',1,1,10,0)""",[year])
    monkeypatch.setattr('pipeline.receiving_build.store_receiving',receiving)
    yield c,core,index,path
    c.close()


def rows(c):return c.execute('SELECT * FROM player_splits ORDER BY ALL').fetchall()


def build(c,core,index):
    splits_builder.materialize(2024,receiving_inputs=core,passing_inputs=index)


def test_native_build_bypasses_old_passing_sql_and_preserves_other_seasons(candidate,monkeypatch):
    c,core,index,_=candidate
    original=splits_builder._category_sql;calls=[]
    def sql(category,*args):
        calls.append(category);assert category=='rushing'
        return original(category,*args)
    monkeypatch.setattr(splits_builder,'_category_sql',sql)
    build(c,core,index)
    assert calls==['rushing']
    assert c.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(first_downs) FROM player_splits WHERE season=2024 AND category='passing' AND split_dim='down'").fetchone()==(50,35,400,17)
    assert c.execute("SELECT yards FROM player_splits WHERE player_id='older'").fetchone()==(12,)
    assert c.execute("SELECT COUNT(*) FROM player_splits WHERE player_id='old'").fetchone()==(0,)
    record=json.loads(c.execute('SELECT record FROM passing_build_preparation').fetchone()[0])
    assert len(record['dimensions'])==17 and record['passing_revision']==index.revision()


def test_late_native_store_failure_rolls_back_every_category_and_metadata(candidate,monkeypatch):
    c,core,index,_=candidate;before=rows(c)
    original=passing_build.store_passing
    def fail(*args):original(*args);raise RuntimeError('after native insert')
    monkeypatch.setattr(passing_build,'store_passing',fail)
    with pytest.raises(RuntimeError,match='after native insert'):build(c,core,index)
    assert rows(c)==before
    assert 'passing_build_preparation' not in {r[0] for r in c.execute('SHOW TABLES').fetchall()}


def test_bad_candidate_source_is_rejected_before_split_replacement(candidate):
    c,core,index,_=candidate;before=rows(c)
    c.execute('UPDATE weekly_player_stats SET passing_yards=passing_yards+1')
    with pytest.raises(SourceError):build(c,core,index)
    assert rows(c)==before


def test_official_passing_cannot_be_rebuilt_without_its_inputs(candidate):
    c,core,index,_=candidate;build(c,core,index);before=rows(c)
    with pytest.raises(RuntimeError,match='passing inputs'):
        splits_builder.materialize(2024,receiving_inputs=core)
    assert rows(c)==before
    with pytest.raises(RuntimeError,match='same captured core'):
        splits_builder.materialize(2024,passing_inputs=index)


def test_ingest_refuses_missing_native_inputs_before_loading_any_source(candidate,monkeypatch):
    import ingest
    c,core,index,_=candidate;build(c,core,index);before=rows(c)
    monkeypatch.setattr(ingest,'get_connection',lambda:c)
    def forbidden(*args,**kwargs):raise AssertionError('must reject before source loading')
    monkeypatch.setattr(ingest,'load_and_store_raw',forbidden)
    with pytest.raises(RuntimeError,match='before any source refresh'):
        ingest.run_ingest([2024],core_inputs=core)
    assert rows(c)==before


@pytest.mark.parametrize('fault',[None,'yards','unknown_epa','first_downs','swap_counts','missing_view','metadata','record_season'])
def test_exact_native_replay_rejects_self_consistent_or_partial_changes(candidate,fault):
    c,core,index,_=candidate;build(c,core,index)
    c.execute("DELETE FROM player_splits WHERE season=1998")
    if fault=='yards':c.execute("UPDATE player_splits SET yards=yards+1 WHERE category='passing' AND split_dim='down'")
    elif fault=='unknown_epa':c.execute("UPDATE player_splits SET epa=NULL WHERE category='passing' AND split_dim='quarter'")
    elif fault=='first_downs':c.execute("UPDATE player_splits SET first_downs=0 WHERE category='passing' AND split_dim='quarter'")
    elif fault=='swap_counts':c.execute("UPDATE player_splits SET yards=400-yards WHERE category='passing' AND split_dim='quarter'")
    elif fault=='missing_view':c.execute("DELETE FROM player_splits WHERE category='passing' AND split_dim='quarter'")
    elif fault=='metadata':c.execute("UPDATE passing_build_preparation SET record='{}'")
    elif fault=='record_season':c.execute('UPDATE passing_build_preparation SET season=2023')
    if fault:
        with pytest.raises(SnapshotValidationError):validate_passing(c,core,index)
    else:
        assert validate_passing(c,core,index)['seasons'][2024]==dict(rows=34,views=17,qualified_players=1)


def test_collection_cannot_be_rebound_after_loading(candidate):
    _,core,index,path=candidate
    manifest=path/'output/run.json';manifest.write_text(manifest.read_text()+' ')
    with pytest.raises(SourceError,match='completion changed'):index.load(2024,core)


@pytest.mark.parametrize('fault',['index','policy','duplicate'])
def test_collection_rejects_changed_policy_and_ambiguous_seasons(candidate,fault):
    _,core,index,path=candidate
    p=path/'passing-index/run.json';record=json.loads(p.read_text())
    if fault=='policy':record['policy']['producer.R']='0'*64
    elif fault=='duplicate':record['exports']*=2
    else:record['exports'][0]['manifest_sha256']='0'*64
    p.write_text(json.dumps(record))
    with pytest.raises(SourceError):PassingInputs(p.parent)


def test_main_gate_requires_matching_native_records_and_inputs_before_schema_checks(candidate):
    c,core,index,_=candidate
    with pytest.raises(SnapshotValidationError,match='matching preparation'):
        validate_snapshot(c,receiving_inputs=core,passing_inputs=index)
    build(c,core,index)
    with pytest.raises(SnapshotValidationError,match='matching preparation'):
        validate_snapshot(c,receiving_inputs=core)


def test_candidate_wrapper_forwards_passing_inputs_to_worker_and_validation(tmp_path,monkeypatch):
    from pipeline import snapshots
    source=tmp_path/'source.duckdb'
    with duckdb.connect(str(source)) as c:c.execute('CREATE TABLE example AS SELECT 1 AS value')
    calls=[]
    monkeypatch.setattr(snapshots,'_run_worker',lambda *args,**kwargs:calls.append(('worker',kwargs)))
    monkeypatch.setattr(snapshots,'validate_preparation',lambda *args:None)
    monkeypatch.setattr(snapshots,'_run_validation',lambda *args,**kwargs:calls.append(('validate',kwargs)))
    core,passing=tmp_path/'core',tmp_path/'passing'
    snapshots.prepare_candidate(source,tmp_path/'candidate.duckdb',[2024],core_inputs=core,passing_inputs=passing,log=lambda _:None)
    assert calls==[('worker',dict(core_inputs=core.resolve(),passing_inputs=passing.resolve())),
                   ('validate',dict(core_inputs=core.resolve(),passing_inputs=passing.resolve()))]
    with pytest.raises(ValueError,match='captured core'):
        snapshots.prepare_candidate(source,tmp_path/'rejected.duckdb',[2024],passing_inputs=passing)
    assert not (tmp_path/'rejected.duckdb').exists()


def test_passing_cli_arguments_reach_the_isolated_worker_and_readonly_validator(tmp_path,monkeypatch):
    from pipeline import snapshots
    calls=[]
    monkeypatch.setattr(snapshots,'_run_job',lambda *args,**kwargs:calls.append((args,kwargs)))
    candidate,core,passing=(tmp_path/name for name in ('candidate','core','passing'))
    snapshots._run_worker(candidate,[2024],core_inputs=core,passing_inputs=passing)
    snapshots._run_validation(candidate,core_inputs=core,passing_inputs=passing)
    assert calls==[
        ((candidate,'jobs.prepare_worker',['--seasons','2024','--core-inputs',str(core),'--passing-inputs',str(passing)]),{}),
        ((candidate,'jobs.validate',['--database',str(candidate),'--core-inputs',str(core),'--passing-inputs',str(passing)]),{'read_only':True})]


@pytest.mark.parametrize('delta',[0,0.4,1.0])
def test_source_epa_identity_preserves_existing_tolerance_and_checks_conversions(delta):
    from pipeline.reconciliation import passing_source_epa_mismatches
    with duckdb.connect(':memory:') as c:
        c.execute("""CREATE TABLE plays AS SELECT 2024 AS season,'REG' AS season_type,
            'qb' AS passer_player_id,19.0::DOUBLE AS qb_epa,'pass' AS play_type""")
        c.execute("INSERT INTO plays VALUES (2024,'REG','qb',1,'qb_spike'),(2024,'POST','qb',900,'pass'),(2024,'REG','qb',900,'no_play')")
        c.execute("CREATE TABLE weekly_player_stats AS SELECT 2024 AS season,'REG' AS season_type,'qb' AS player_id,100 AS attempts,20.0 AS passing_epa")
        c.execute('UPDATE weekly_player_stats SET passing_epa=passing_epa+?',[delta])
        assert passing_source_epa_mismatches(c,2024)==int(delta>.5)
