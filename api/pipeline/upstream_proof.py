"""Read hash-bound source-version evidence; old captures make no freshness claim."""
import hashlib
import json
from pathlib import Path

from pipeline.receiving_preview import file_sha256
from pipeline.receiving_splits import read_export_bytes
from pipeline.upstream_assets import CORE_ASSETS, asset_version, validate_asset


def read_upstream_versions(directory, manifest, season):
    if 'upstream-proof.json' not in manifest.get('files', {}):
        return {}
    def read(name):
        return read_export_bytes(directory, manifest, name, season=season)
    proof, result = (json.loads(read(name)) for name in ('upstream-proof.json', 'upstream-result.json'))
    if (type(proof.get('format_version')) is not int or proof['format_version'] != 1
            or proof.get('kind') != 'native_upstream_proof' or proof.get('season') != season
            or not proof.get('run_id') or proof['run_id'] != manifest.get('run_id')
            or set(proof.get('assets', {})) != set(CORE_ASSETS) or set(result) != set(CORE_ASSETS)):
        raise ValueError('Invalid native upstream proof scope')
    verifier = read('upstream-verify.R')
    if (hashlib.sha256(verifier).hexdigest() != proof['verifier_sha256']
            or proof['verifier_sha256'] != file_sha256(Path(__file__).resolve().parents[1] / 'r/verify_upstream_inputs.R')):
        raise ValueError('Unrecognized upstream comparison policy')
    versions = {}
    for key, (_, _, _, prefix) in CORE_ASSETS.items():
        item, comparison = proof['assets'][key], result[key]
        metadata = validate_asset(key, season, item['metadata'])
        if (item['version'] != asset_version(metadata) or item['download_sha256'] != metadata['digest'][7:]
                or item['download_file'] != f'upstream-{key}-{season}.rds'
                or item['consumed_file'] != f'{prefix}-{season}.rds'
                or comparison != dict(status='equal', rows=comparison.get('rows'),
                    download_sha256=item['download_sha256'], consumed_sha256=item['consumed_sha256'])
                or type(comparison['rows']) is not int or comparison['rows'] <= 0):
            raise ValueError('Invalid upstream asset comparison')
        for name, expected in ((item['download_file'], item['download_sha256']),
                               (item['consumed_file'], item['consumed_sha256'])):
            if hashlib.sha256(read(name)).hexdigest() != expected:
                raise ValueError('Changed upstream or consumed input bytes')
        if (Path(directory) / item['download_file']).stat().st_size != metadata['size']:
            raise ValueError('Changed upstream asset size')
        versions[key] = item['version']
    return versions
