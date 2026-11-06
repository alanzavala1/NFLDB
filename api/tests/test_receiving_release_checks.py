"""Full integration diagnostics remain strict without permitting publication."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import pandas as pd

import pytest

from pipeline.reconciliation import passing_epa_mismatches
from pipeline.validation import SnapshotValidationError, validate_snapshot
from tests.test_snapshot_validation import prepared, reconciled
from tests.test_receiving_core_inputs import bundle


@pytest.mark.parametrize('fault', [None, 'missing_bucket', 'invented_zero_rate', 'wrong_positive_rate', 'unknown_positive_rate'])
def test_sack_only_down_preserves_negative_epa_without_waiving_real_errors(reconciled, fault):
    c = reconciled
    c.execute("INSERT INTO plays VALUES (2024,'REG',4,1,1,'qb',-4,'pass')")
    c.execute("INSERT INTO plays VALUES (2024,'POST',4,1,1,'qb',-400,'pass')")
    c.execute("INSERT INTO plays VALUES (2023,'REG',4,1,1,'qb',-400,'pass')")
    c.execute("INSERT INTO plays VALUES (2024,'REG',4,1,1,'qb',-400,'no_play')")
    c.execute("INSERT INTO player_splits VALUES (2024,'qb','passing','down','4',0,NULL,-4,0)")
    c.execute('UPDATE weekly_player_stats SET passing_epa=16')
    if fault == 'missing_bucket':
        c.execute("DELETE FROM player_splits WHERE split_value='4'")
    elif fault == 'invented_zero_rate':
        c.execute("UPDATE player_splits SET epa=0 WHERE split_value='4'")
    elif fault == 'wrong_positive_rate':
        c.execute("UPDATE player_splits SET epa=0.3 WHERE split_value='1'")
    elif fault == 'unknown_positive_rate':
        c.execute("UPDATE player_splits SET epa=NULL WHERE split_value='1'")
    assert passing_epa_mismatches(c,2024) == int(fault is not None)


@pytest.fixture
def official_prepared(prepared, monkeypatch):
    """Use real generic builders; mock only the separately tested receiving replay.

    Its 43 source-corruption controls and real historical CLI proof cover replay;
    these cases check how the complete validator composes it with other gates.
    """
    conn, _ = prepared
    # The legacy fixture deliberately has weekly data for only one game. Give
    # this complete-catalog control an official QB row for every supplied game.
    template = conn.execute('SELECT * FROM weekly_player_stats LIMIT 1').df()
    groups = conn.execute('''SELECT game_id,season,week,posteam AS team,
        passer_player_id AS player_id,MAX(passer_player_name) AS player_name,
        COUNT(*) AS attempts,SUM(complete_pass) AS completions,
        SUM(passing_yards) AS passing_yards,SUM(qb_epa) AS passing_epa
        FROM plays WHERE passer_player_id IS NOT NULL
        GROUP BY game_id,season,week,posteam,passer_player_id''').df()
    weekly = pd.concat([template.assign(**row) for row in groups.to_dict('records')],ignore_index=True)
    conn.register('complete_weekly',weekly)
    conn.execute('CREATE OR REPLACE TABLE weekly_player_stats AS SELECT * FROM complete_weekly')
    from pipeline.player_stats import build_player_game_stats
    from pipeline.analytics import prepare_analytics
    build_player_game_stats(conn,conn.execute('SELECT * FROM plays').df(),[2024],log=lambda _:None)
    prepare_analytics([2024],log=lambda _:None)
    conn.execute('CREATE TABLE receiving_build_preparation AS SELECT 2024 AS season')
    conn.execute('''CREATE TABLE snapshot_preparation (
        format_version INTEGER,requested_seasons JSON,source_outcomes JSON)''')
    outcomes = [dict(source=t,season=2024,status='loaded',rows=conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
                for t in ('plays','weekly_player_stats','schedules','rosters')]
    conn.execute('INSERT INTO snapshot_preparation VALUES (1,?,?)',[json.dumps([2024]),json.dumps(outcomes)])
    calls = []
    inputs = object()
    def receiving(c, owner, **kwargs):
        assert c is conn and owner is inputs
        calls.append('receiving')
        return {'status':'passed','played_seasons':[2024]}
    def charting(c, owner, years):
        assert c is conn and owner is inputs and years == [2024]
        calls.append('charting')
    monkeypatch.setattr('pipeline.receiving_validation.validate_receiving',receiving)
    monkeypatch.setattr('pipeline.receiving_inputs.verify_stored_ftn',charting)
    return conn, inputs, calls


def test_full_diagnostics_use_bound_receiving_instead_of_down_subtotals_and_keep_guard(official_prepared,monkeypatch):
    from pipeline import reconciliation
    c, inputs, calls = official_prepared
    original = reconciliation.count_mismatches
    def counts(conn,year,category,*args):
        assert category != 'receiving', 'legacy Down receiving checks must not run'
        return original(conn,year,category,*args)
    monkeypatch.setattr(reconciliation,'count_mismatches',counts)
    messages = []
    with pytest.raises(SnapshotValidationError,match='require native passing preparation before publication'):
        validate_snapshot(c,receiving_inputs=inputs,log=messages.append)
    assert calls == ['receiving','charting']
    assert any('Snapshot[2024]' in msg and 'pass_attempts=0/0' in msg for msg in messages)


@pytest.mark.parametrize('table',['player_game_stats','player_game_ratings','team_game_ol_grades'])
def test_season_nonempty_cannot_hide_missing_game_analytics(official_prepared,table):
    c, inputs, _ = official_prepared
    c.execute(f'DELETE FROM {table} WHERE game_id=(SELECT MIN(game_id) FROM {table})')
    assert c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] > 0
    with pytest.raises(SnapshotValidationError,match='missing supplied REG games'):
        validate_snapshot(c,receiving_inputs=inputs)


@pytest.mark.parametrize('failure',['receiving','charting','preparation'])
def test_source_failures_stop_full_validation(official_prepared,monkeypatch,failure):
    from pipeline.source_results import SourceError
    c, inputs, calls = official_prepared
    if failure == 'preparation':
        c.execute("UPDATE snapshot_preparation SET requested_seasons='[true]'")
        expected = 'invalid requested seasons'
    elif failure == 'receiving':
        def fail(*args,**kwargs):
            raise SnapshotValidationError('receiving source replay differs')
        monkeypatch.setattr('pipeline.receiving_validation.validate_receiving',fail)
        expected = 'source replay differs'
    else:
        def fail(*args,**kwargs):
            raise SourceError('ftn_charting',2024,'different charting capture')
        monkeypatch.setattr('pipeline.receiving_inputs.verify_stored_ftn',fail)
        expected = 'different charting capture'
    with pytest.raises(SnapshotValidationError,match=expected):
        validate_snapshot(c,receiving_inputs=inputs)
    assert 'charting' not in calls


def test_unrelated_failures_from_all_years_are_reported_without_larger_allowances(official_prepared,monkeypatch):
    c, inputs, _ = official_prepared
    monkeypatch.setattr('pipeline.validation.season_checks',lambda *a,**kw:
                        {'pass_attempts':(1,0),'passing_epa':(1,0)})
    with pytest.raises(SnapshotValidationError) as error:
        validate_snapshot(c,receiving_inputs=inputs)
    assert 'pass_attempts[2024]: 1 mismatches (allowed 0)' in str(error.value)
    assert 'passing_epa[2024]: 1 mismatches (allowed 0)' in str(error.value)


def test_captured_option_cannot_be_ignored_for_legacy_snapshot(prepared):
    c, _ = prepared
    with pytest.raises(SnapshotValidationError,match='require official receiving preparation records'):
        validate_snapshot(c,receiving_inputs=object())


@pytest.mark.parametrize('marker',['receiving_whole_reference','receiving_season_totals'])
def test_deleting_preparation_marker_cannot_bypass_official_guard(prepared,marker):
    c, _ = prepared
    c.execute(f'CREATE TABLE {marker} AS SELECT 2024 AS season')
    with pytest.raises(SnapshotValidationError,match='coverage-aware API/UI'):
        validate_snapshot(c)


@pytest.mark.parametrize('fault',['missing_preparation','invalid_manifest'])
def test_real_full_cli_uses_captured_inputs_and_rejects_read_only(prepared,bundle,fault):
    conn,path = prepared
    conn.execute('CREATE TABLE receiving_build_preparation AS SELECT 2024 AS season')
    conn.close()
    if fault == 'invalid_manifest':
        (bundle/'run.json').write_text('{')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    process = subprocess.run([sys.executable,'-m','jobs.validate','--database',str(path),
                              '--core-inputs',str(bundle)],
                             cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert process.returncode != 0
    expected = 'no preparation record' if fault == 'missing_preparation' else 'JSONDecodeError'
    assert expected in process.stderr,process.stderr
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not Path(str(path)+'.wal').exists()


def test_snapshot_wrapper_passes_bound_inputs_to_its_read_only_validation(monkeypatch):
    from pipeline import snapshots
    calls = []
    monkeypatch.setattr(snapshots,'_run_job',lambda *args,**kwargs:calls.append((args,kwargs)))
    snapshots._run_validation(Path('candidate'),core_inputs=Path('captured'))
    assert calls == [((Path('candidate'),'jobs.validate',
                       ['--database','candidate','--core-inputs','captured']),{'read_only':True})]
