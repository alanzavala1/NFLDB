"""Refresh orchestration preserves verified inputs and stops on any failed stage."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from automation import native_refresh, refresh_plan
from pipeline import releases as native
from publication import downloads
from tests.test_publication_selection import prepared, case, captures, bundle, release_case, choose


@pytest.fixture
def refresh_case(prepared, tmp_path):
    selected = choose(prepared)
    store = prepared[0][3]
    plan = refresh_plan.plan_refresh(selected['pointer'], store, season=2024,
                                    observe=lambda _: {'pbp_rds':'fresh'})
    plan_path = tmp_path/'plan.json'
    refresh_plan.write_record(plan_path, plan)
    download = tmp_path/'download'
    downloads.download_selected(selected['pointer'], download, store, include_captures=True, log=lambda _:None)
    rscript, library = tmp_path/'Rscript', tmp_path/'library'
    rscript.write_text('fixture')
    library.mkdir()
    calls = []
    def run(module, *arguments):
        calls.append((module,tuple(str(item) for item in arguments)))
        args = [str(item) for item in arguments]
        if module == 'jobs.refresh':
            shutil.copytree(download/'release', Path(args[args.index('--release')+1]))
        elif module == 'jobs.captures':
            shutil.copyfile(download/'captures.zip', args[args.index('--output')+1])
    options = dict(rscript=rscript,library=library,run=run,log=lambda _:None)
    return plan_path, download, tmp_path/'work', options, calls, store


def test_plan_reads_only_small_metadata_and_records_original_selection(prepared):
    selected = choose(prepared)
    store = prepared[0][3]
    store.events.clear()
    result = refresh_plan.plan_refresh(selected['pointer'],store,season=2024,
                                      observe=lambda _: {'source':'acknowledged'})
    assert result['selection'] == selected and result['changed'] is False
    assert not any(event[0] in ('download','replace','create') for event in store.events)
    assert not any(event[0]=='read' and event[1].endswith(('/nfl.duckdb','/captures.zip')) for event in store.events)


def test_plan_distinguishes_changed_unpublished_and_forced_sources(prepared):
    selected = choose(prepared)
    store = prepared[0][3]
    observed = lambda _: {'source':'acknowledged','unpublished':None,'pbp_rds':'new'}
    result = refresh_plan.plan_refresh(selected['pointer'],store,season=2024,observe=observed)
    assert result['changed'] is True and result['moved'] == ['pbp_rds']
    forced = refresh_plan.plan_refresh(selected['pointer'],store,season=2024,force=True,
                                      observe=lambda _: {'source':'acknowledged'})
    assert forced['changed'] is True and forced['moved'] == [] and forced['forced'] is True


def test_preparation_reuses_jobs_and_finishes_only_after_bundle_and_archive_checks(refresh_case):
    plan,download,work,options,calls,_ = refresh_case
    before = native.digest(download/'release/nfl.duckdb')
    result = native_refresh.prepare_refresh(plan,download,work,**options)
    assert [module for module,_ in calls] == ['jobs.capture_core','jobs.passing_preview','jobs.refresh_inputs',
                                             'jobs.refresh','jobs.captures']
    assert '--dimensions' not in calls[1][1]  # Ordinary exporter defaults to every view.
    assert result['seasons'] == [2024] and result['kind'] == 'native_refresh_ready'
    assert json.loads((work/'refresh.json').read_bytes()) == result
    assert native.digest(download/'release/nfl.duckdb') == before


@pytest.mark.parametrize('module',['jobs.capture_core','jobs.passing_preview','jobs.refresh_inputs',
                                  'jobs.refresh','jobs.captures'])
def test_failed_stages_leave_diagnostics_but_no_ready_marker(refresh_case,module):
    plan,download,work,options,calls,_ = refresh_case
    original = options['run']
    def fail(name,*args):
        if name == module:
            (work/'failure.txt').write_text(name)
            raise subprocess.CalledProcessError(1,[name])
        original(name,*args)
    with pytest.raises(subprocess.CalledProcessError):
        native_refresh.prepare_refresh(plan,download,work,**dict(options,run=fail))
    assert not (work/'refresh.json').exists() and (work/'failure.txt').read_text() == module
    assert native.verify_release(download/'release')


@pytest.mark.parametrize('relative',['release/nfl.duckdb','release/watermarks.json','captures.zip'])
def test_corrupt_download_stops_before_r_or_workspace_creation(refresh_case,relative):
    plan,download,work,options,calls,_ = refresh_case
    (download/relative).write_bytes(b'changed')
    with pytest.raises(ValueError,match='differs'):
        native_refresh.prepare_refresh(plan,download,work,**options)
    assert not work.exists() and not calls


def test_existing_workspace_is_preserved_without_running_any_stage(refresh_case):
    plan,download,work,options,calls,_ = refresh_case
    work.mkdir()
    (work/'keep').write_text('original')
    with pytest.raises(FileExistsError):
        native_refresh.prepare_refresh(plan,download,work,**options)
    assert (work/'keep').read_text() == 'original' and not calls


def test_changed_input_receipt_before_completion_is_rejected(refresh_case):
    plan,download,work,options,_,_ = refresh_case
    original = options['run']
    def change(module,*args):
        original(module,*args)
        if module == 'jobs.captures':
            receipt = download/'download.json'
            receipt.write_bytes(receipt.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='changed during'):
        native_refresh.prepare_refresh(plan,download,work,**dict(options,run=change))
    assert not (work/'refresh.json').exists()


def test_missing_new_season_in_validation_report_cannot_finish(refresh_case):
    plan,download,work,options,_,_ = refresh_case
    value = json.loads(plan.read_bytes())
    value['season'] = 2025
    plan.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='coverage'):
        native_refresh.prepare_refresh(plan,download,work,**options)
    assert not (work/'refresh.json').exists()


@pytest.mark.parametrize('fault', ['missing-captures', 'wrong-selection', 'no-change', 'policy-changed'])
def test_incompatible_or_unnecessary_runs_stop_before_any_worker(refresh_case, fault):
    plan,download,work,options,calls,_ = refresh_case
    if fault == 'missing-captures':
        path = download/'download.json'
        value = json.loads(path.read_bytes())
        value['includes_captures'] = False
    else:
        path = plan
        value = json.loads(path.read_bytes())
        if fault == 'wrong-selection': value['selection']['pointer_generation'] = '999999'
        if fault == 'no-change': value['changed'] = False
        if fault == 'policy-changed': value['validation_code_sha256'] = '0'*64
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        native_refresh.prepare_refresh(plan,download,work,**options)
    assert not work.exists() and not calls
