"""Capture native inputs and bind them to the exact published RDS versions."""
import json
import os
from pathlib import Path
import uuid

from pipeline.receiving_core_inputs import export_core_inputs
from pipeline.receiving_preview import _run_export, file_sha256
from pipeline.r_runtime import run_r_export
from pipeline.upstream_assets import CORE_ASSETS, asset_version, download_asset, observe_core_assets
from pipeline.upstream_proof import read_upstream_versions


def _json(path, record):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')


def capture_core(output, season, *, rscript, library, log=print):
    """New directory only; never opens a DB, advances marks or publishes.

    Existing calculator bytes stay unchanged. Raw upstream downloads are checked
    against GitHub SHA256 digests, then compared to every consumed typed column.
    """
    output, rscript, library = Path(output).absolute(), Path(rscript).resolve(), Path(library).resolve()
    if type(season) is not int or season < 1999:
        raise ValueError('Provide one integer season from 1999 onward')
    if not rscript.is_file() or not library.is_dir():
        raise ValueError('Provide an existing Rscript and locked R library')
    output.mkdir()
    exports = output / 'receiving'
    exports.mkdir()
    before = {}
    def download():
        before.update(observe_core_assets(season))
        for key, asset in before.items():
            log(f'Capturing {key}[{season}]: {asset["name"]}')
            download_asset(asset, exports / f'upstream-{key}-{season}.rds')
    run_id = uuid.uuid4().hex
    _run_export(rscript, library, exports, [season], run_id, before_export=download)
    manifest_path = exports / 'run.json'
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get('run_id') != run_id or manifest.get('seasons') != [season]:
        raise ValueError('Native capture completion does not match this invocation')
    assets = {}
    for key, (_, _, _, prefix) in CORE_ASSETS.items():
        consumed = f'{prefix}-{season}.rds'
        if file_sha256(exports / consumed) != manifest['files'][consumed]:
            raise ValueError('Consumed input changed after native export')
        assets[key] = dict(metadata=before[key], version=asset_version(before[key]),
            download_file=f'upstream-{key}-{season}.rds', download_sha256=before[key]['digest'][7:],
            consumed_file=consumed, consumed_sha256=manifest['files'][consumed])
    api = Path(__file__).resolve().parents[1]
    (exports / 'upstream-verify.R').write_bytes((api / 'r/verify_upstream_inputs.R').read_bytes())
    _json(exports / 'upstream-request.json', dict(season=season, assets=assets))
    env = dict(os.environ, R_LIBS_USER=str(library), NFL_RECEIVING_LIBRARY=str(library), LC_ALL='C')
    run_r_export([str(rscript), '--vanilla', str(exports / 'upstream-verify.R'), str(exports), str(library)],
                 cwd=api, env=env, logfile=exports / 'upstream-verify.log')
    after = observe_core_assets(season)
    if set(before) != set(CORE_ASSETS) or set(after) != set(CORE_ASSETS) or any(
            asset_version(before[key]) != asset_version(after[key]) for key in CORE_ASSETS):
        raise ValueError('Upstream core assets changed during capture; no freshness proof issued')
    _json(exports / 'upstream-proof.json', dict(format_version=1, kind='native_upstream_proof', season=season,
        run_id=run_id, assets=assets, verifier_sha256=file_sha256(exports / 'upstream-verify.R')))
    names = ['upstream-proof.json', 'upstream-request.json', 'upstream-result.json', 'upstream-verify.R',
             *(item['download_file'] for item in assets.values())]
    manifest['files'].update({name: file_sha256(exports / name) for name in names})
    # Bind sidecars only after comparison and stable-version checks. The native
    # producer policy is unchanged; only this new leaf manifest gets a new hash.
    _json(exports / 'run-with-upstream.json', manifest)
    os.replace(exports / 'run-with-upstream.json', manifest_path)
    versions = read_upstream_versions(exports, manifest, season)
    core = export_core_inputs(exports, output / 'core', rscript=rscript, library=library)
    _json(output / 'capture.json', dict(format_version=1, season=season, core=str(core.directory),
        core_revision=core.revision(), receiving_manifest_sha256=file_sha256(manifest_path), versions=versions,
        publication_ready=False))
    log(f'Verified native core capture: {core.directory}; no watermarks or release selection changed')
    return core
