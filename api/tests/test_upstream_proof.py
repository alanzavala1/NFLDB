"""Freshness requires exact published assets, consumed inputs and typed equality."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import core_capture
from pipeline.receiving_preview import file_sha256
from pipeline.source_results import SourceError
from pipeline.upstream_assets import CORE_ASSETS, asset_version
from pipeline.upstream_proof import read_upstream_versions


def published(key, season=2026, content=None):
    repository, tag, template, _ = CORE_ASSETS[key]
    content = content if content is not None else key.encode()
    name = template.format(season=season)
    return dict(repository=repository, tag=tag, name=name, id=123, size=len(content),
                updated_at='2026-10-28T00:00:00Z', digest='sha256:'+hashlib.sha256(content).hexdigest(),
                url=f'https://github.com/nflverse/{repository}/releases/download/{tag}/{name}')


@pytest.fixture
def capture(tmp_path, monkeypatch):
    executable, library = tmp_path/'Rscript', tmp_path/'library'
    executable.write_bytes(b'fixture')
    library.mkdir()
    metadata = {key: published(key) for key in CORE_ASSETS}
    observations = []
    def observe(year):
        observations.append(year)
        return deepcopy(metadata)
    monkeypatch.setattr(core_capture, 'observe_core_assets', observe)
    monkeypatch.setattr(core_capture, 'download_asset', lambda item, path: path.write_bytes(
        next(key.encode() for key in CORE_ASSETS if item['name'] == metadata[key]['name'])))
    def export(rscript, library, output, seasons, run_id, *, before_export):
        before_export()
        files = {}
        for key, (_, _, _, prefix) in CORE_ASSETS.items():
            path = output/f'{prefix}-{seasons[0]}.rds'
            path.write_bytes(b'reserialized '+key.encode())
            files[path.name] = file_sha256(path)
        (output/'run.json').write_text(json.dumps(dict(run_id=run_id, seasons=seasons, files=files)))
    monkeypatch.setattr(core_capture, '_run_export', export)
    def compare(command, **options):
        output = Path(command[3])
        request = json.loads((output/'upstream-request.json').read_bytes())
        result = {key: dict(status='equal', rows=4, download_sha256=item['download_sha256'],
                            consumed_sha256=item['consumed_sha256']) for key,item in request['assets'].items()}
        (output/'upstream-result.json').write_text(json.dumps(result))
    monkeypatch.setattr(core_capture, 'run_r_export', compare)
    def convert(source, output, **options):
        output.mkdir()
        return SimpleNamespace(directory=output, revision=lambda:'fixture source revision')
    monkeypatch.setattr(core_capture, 'export_core_inputs', convert)
    output = tmp_path/'captured'
    return output, executable, library, metadata, observations


def run(capture):
    output, executable, library, _, _ = capture
    return core_capture.capture_core(output, 2026, rscript=executable, library=library, log=lambda _:None)


def test_fresh_capture_binds_proof_before_conversion_and_never_claims_publication(capture):
    result = run(capture)
    output, _, _, metadata, observations = capture
    manifest = json.loads((output/'receiving/run.json').read_bytes())
    versions = read_upstream_versions(output/'receiving',manifest,2026)
    assert versions == {key:asset_version(item) for key,item in metadata.items()}
    assert observations == [2026,2026]
    assert result.directory == output/'core'
    assert json.loads((output/'capture.json').read_bytes())['publication_ready'] is False
    with pytest.raises(FileExistsError):run(capture)
    assert observations == [2026,2026]


@pytest.mark.parametrize('fault', ['download','consumed','proof','verifier','result','season','run_id','version','missing_credit'])
def test_changed_or_mixed_proof_cannot_acknowledge_any_upstream_version(capture,fault):
    run(capture)
    output = capture[0]/'receiving'
    manifest = json.loads((output/'run.json').read_bytes())
    if fault in ('download','consumed','verifier'):
        name = {'download':'upstream-pbp_rds-2026.rds','consumed':'pbp-2026.rds','verifier':'upstream-verify.R'}[fault]
        with (output/name).open('ab') as stream:stream.write(b'changed')
    else:
        name = 'upstream-result.json' if fault == 'result' else 'upstream-proof.json'
        record = json.loads((output/name).read_bytes())
        if fault == 'proof': record['kind'] = 'unverified'
        if fault == 'result':record['playstats']['status'] = 'different'
        if fault == 'season':record['season'] = 2025
        if fault == 'run_id':record['run_id'] = 'different run'
        if fault == 'version':record['assets']['pbp_rds']['version'] = 'today'
        if fault == 'missing_credit':del record['assets']['playstats']
        (output/name).write_text(json.dumps(record))
        # Rebind outer file hash to reach the semantic proof checks.
        manifest['files'][name] = file_sha256(output/name)
    with pytest.raises((ValueError,SourceError)):
        read_upstream_versions(output,manifest,2026)


def test_unmodified_old_capture_has_no_freshness_claim(tmp_path):
    assert read_upstream_versions(tmp_path,{'files':{}},2026) == {}


def test_changed_upstream_during_export_leaves_no_freshness_completion(capture,monkeypatch):
    metadata = capture[3]
    original = core_capture.run_r_export
    def compare(*args,**kwargs):
        original(*args,**kwargs)
        metadata['playstats']['updated_at'] = '2026-10-28T01:00:00Z'
    monkeypatch.setattr(core_capture,'run_r_export',compare)
    with pytest.raises(ValueError,match='changed during'):run(capture)
    assert not (capture[0]/'capture.json').exists()
    assert not (capture[0]/'receiving/upstream-proof.json').exists()
    assert 'upstream-proof.json' not in json.loads((capture[0]/'receiving/run.json').read_bytes())['files']


def test_typed_comparison_failure_never_creates_proof(capture,monkeypatch):
    def fail(*args,**kwargs):raise RuntimeError('typed values differ')
    monkeypatch.setattr(core_capture,'run_r_export',fail)
    with pytest.raises(RuntimeError,match='typed values differ'):run(capture)
    assert not (capture[0]/'capture.json').exists()
    assert not (capture[0]/'receiving/upstream-proof.json').exists()
