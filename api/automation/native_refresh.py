"""Connect existing capture, composition, preparation and archive jobs in order."""
import json
import os
from pathlib import Path
import subprocess
import sys

from automation.refresh_plan import read_plan, write_record
from pipeline import releases as native
from pipeline.capture_archive import restore_captures
from publication.archive import verify_archive
from publication.releases import fingerprint


def verify_download(download, plan):
    download = Path(download).resolve()
    receipt = json.loads((download/'download.json').read_bytes())
    if (type(receipt.get('format_version')) is not int or receipt['format_version'] != 1
            or receipt.get('kind') != 'native_release_download' or receipt.get('includes_captures') is not True
            or receipt.get('selection') != plan['selection'] or receipt.get('publication') != plan['publication']):
        raise ValueError('Use a completed download of the exact planned selection, including captures')
    files = {**{f'release/{name}': name for name in (*native.FILES, 'release.json')},
             'captures.zip': 'captures.zip'}
    if set(receipt['files']) != set(files):
        raise ValueError('Incomplete download inventory')
    for relative, name in files.items():
        expected = plan['publication']['publication']['files'][name]
        actual = fingerprint(download/relative)
        if (actual != receipt['files'][relative]
                or any(actual[key] != expected[key] for key in actual)):
            raise ValueError('Downloaded input differs from publication: '+name)
    native.verify_release(download/'release')
    return receipt


def run_job(module, *arguments):
    # Fresh processes keep the offline worker's database/configuration isolated.
    env = dict(os.environ, NFL_TEST_MODE='1', NFL_DB_READ_ONLY='1', PYTHONUNBUFFERED='1')
    subprocess.run([sys.executable, '-m', module, *(str(arg) for arg in arguments)],
                   cwd=Path(__file__).resolve().parents[1], env=env, check=True)


def prepare_refresh(plan_path, download, workspace, *, rscript, library, run=run_job, log=print):
    workspace, download = Path(workspace).absolute(), Path(download).resolve()
    if workspace.exists() or workspace.is_symlink():
        raise FileExistsError('Refresh workspace must be a new directory')
    plan_hash = native.digest(plan_path)
    plan = read_plan(plan_path)
    if not plan['changed']:
        raise ValueError('No refresh required; create a forced plan to rebuild unchanged sources')
    rscript, library = Path(rscript).resolve(), Path(library).resolve()
    if not rscript.is_file() or not library.is_dir():
        raise ValueError('Provide an existing Rscript and locked R library')
    receipt_hash = native.digest(download/'download.json')
    receipt = verify_download(download, plan)
    year = plan['season']
    workspace.mkdir()
    # Failures retain diagnostics but never issue refresh.json or publish.
    log('Restoring verified historical captures')
    base = restore_captures(download/'captures.zip', workspace/'history')
    fresh, passing, inputs = workspace/'fresh', workspace/'fresh-passing', workspace/'inputs'
    runtime = ('--rscript', rscript, '--r-library', library)
    log(f'Capturing fresh native inputs for {year}')
    run('jobs.capture_core', '--season', year, '--output', fresh, *runtime)
    log(f'Calculating all passing views for {year}')
    run('jobs.passing_preview', '--core-inputs', fresh/'core', '--season', year,
        '--exports', passing, *runtime)
    log('Combining refreshed season with unchanged historical inputs')
    run('jobs.refresh_inputs', '--core-inputs', base['core'], '--passing-inputs', base['passing'],
        '--fresh-core', fresh/'core', '--fresh-passing', passing, '--output', inputs)
    log('Preparing candidate and validating every stored season and API view')
    run('jobs.refresh', 'prepare', download/'release/watermarks.json',
        '--source', download/'release/nfl.duckdb', '--candidate', workspace/'candidate.duckdb',
        '--release', workspace/'release', '--seasons', year,
        '--core-inputs', inputs/'core', '--passing-inputs', inputs/'passing')
    log('Packing the matching captured inputs')
    run('jobs.captures', 'pack', '--core-inputs', inputs/'core', '--passing-inputs', inputs/'passing',
        '--output', workspace/'captures.zip')
    native.verify_release(workspace/'release')
    report = json.loads((workspace/'release/validation.json').read_bytes())
    expected_seasons = sorted(set(plan['publication']['publication']['seasons']) | {year})
    if report['played_seasons'] != expected_seasons:
        raise ValueError('Refresh lost historical coverage or did not include the requested season')
    verify_archive(workspace/'captures.zip', report['source_revisions'], expected_seasons)
    verify_download(download, plan)
    if native.digest(plan_path) != plan_hash or native.digest(download/'download.json') != receipt_hash:
        raise ValueError('Refresh plan or input receipt changed during preparation')
    files = {f'release/{name}': fingerprint(workspace/'release'/name)
             for name in (*native.FILES, 'release.json')}
    files['captures.zip'] = fingerprint(workspace/'captures.zip')
    result = dict(format_version=1, kind='native_refresh_ready', season=year, seasons=expected_seasons,
                  selection=plan['selection'], plan_sha256=plan_hash, download_sha256=receipt_hash,
                  validation_code_sha256=plan['validation_code_sha256'], files=files)
    write_record(workspace/'refresh.json', result)
    log('Verified refresh ready; cloud publication and selection remain separate')
    return result
