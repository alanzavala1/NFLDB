"""Create immutable, source-validated release bundles; never change a serving DB."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import duckdb


class ReleaseError(RuntimeError):
    pass


FILES = ('nfl.duckdb', 'validation.json', 'watermarks.json')


def validation_revision():
    """Portable policy fingerprint; line endings don't change Python semantics."""
    from automation.validation_policy import compatible_revision

    api = Path(__file__).resolve().parents[1]
    paths = [*api.glob('*.py'), api/'uv.lock', api/'jobs/validate.py']
    for folder in ('pipeline', 'schemas', 'services', 'routers'):
        paths.extend((api/folder).glob('*.py'))
    value = hashlib.sha256()
    for path in sorted(paths):
        value.update(path.relative_to(api).as_posix().encode()+b'\0')
        value.update(path.read_bytes().replace(b'\r\n', b'\n')+b'\0')
    return compatible_revision(value.hexdigest())


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def _validate(database, core_inputs, passing_inputs):
    command = [sys.executable, '-m', 'jobs.validate', '--database', str(database),
               '--core-inputs', str(core_inputs), '--passing-inputs', str(passing_inputs)]
    env = dict(os.environ, NFL_DB_PATH=str(database), NFL_DB_READ_ONLY='1')
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=env,
                            stdout=subprocess.PIPE, text=True, check=True)
    return json.loads(result.stdout)


def _report(report):
    if (not isinstance(report, dict) or report.get('publication_ready') is not True or report.get('official_receiving') is not True
            or report.get('official_passing') is not True or not report.get('played_seasons')
            or not report.get('api_requests') or not isinstance(report.get('source_revisions'), dict)
            or not all(report['source_revisions'].get(key) for key in ('core', 'passing'))):
        raise ReleaseError('A native release requires full source and HTTP validation')


def _marks(value):
    if not isinstance(value, dict) or any(not isinstance(key, str) or not isinstance(stamp, str)
                                          or not stamp for key, stamp in value.items()):
        raise ReleaseError('Watermarks must contain acknowledged string stamps')


def create_release(database, output, *, core_inputs, passing_inputs, watermarks=None):
    """Validate under a read lock, copy, hash and write completion marker last.

    Existing paths are never overwritten. A failed build has no completion
    marker and cannot be selected. Caller supplies already acknowledged marks;
    packaging an old candidate never fetches or advances upstream stamps.
    """
    database, output = Path(database).resolve(), Path(output).absolute()
    core_inputs, passing_inputs = Path(core_inputs).resolve(), Path(passing_inputs).resolve()
    _marks({} if watermarks is None else watermarks)
    marks = {} if watermarks is None else dict(watermarks)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if not database.is_file() or Path(str(database)+'.wal').exists():
        raise ReleaseError('Release input must be a closed database without a WAL')
    with duckdb.connect(str(database), read_only=True):
        if Path(str(database)+'.wal').exists():
            raise ReleaseError('Release input has a pending WAL')
        before = digest(database)
        policy = validation_revision()
        report = _validate(database, core_inputs, passing_inputs)
        _report(report)
        if digest(database) != before or validation_revision() != policy:
            raise ReleaseError('Database or validation policy changed during validation')
        output.mkdir()  # Exclusive ownership; never clean up pre-existing files.
        try:
            with database.open('rb') as origin, (output / 'nfl.duckdb').open('xb') as target:
                shutil.copyfileobj(origin, target)
                target.flush()
                os.fsync(target.fileno())
            if digest(output / 'nfl.duckdb') != before:
                raise ReleaseError('Release database copy differs from validated input')
            _json(output / 'validation.json', report)
            _json(output / 'watermarks.json', marks)
            manifest = {'format_version': 1, 'kind': 'native_nfl_release',
                        'validation_code_sha256': policy,
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'count_scope': 'Observed production on supplied games; not a freshness certificate',
                        'files': {name: {'sha256': digest(output / name), 'bytes': (output / name).stat().st_size}
                                  for name in FILES}}
            _json(output / 'release.json', manifest)
        except BaseException:
            # Known filenames only, inside this call's exclusively created dir.
            for name in (*FILES, 'release.json'):
                (output / name).unlink(missing_ok=True)
            output.rmdir()
            raise
    return verify_release(output)


def verify_release(directory):
    directory = Path(directory).resolve()
    try:
        marker = directory / 'release.json'
        if marker.is_symlink():
            raise ReleaseError('Release marker must be a regular file')
        manifest = json.loads(marker.read_bytes())
        if (type(manifest.get('format_version')) is not int or manifest['format_version'] != 1
                or manifest.get('kind') != 'native_nfl_release' or set(manifest['files']) != set(FILES)
                or manifest.get('validation_code_sha256') != validation_revision()):
            raise ReleaseError('Invalid release manifest')
        for name in FILES:
            path, record = directory / name, manifest['files'][name]
            if (not path.is_file() or path.is_symlink() or type(record['bytes']) is not int
                    or path.stat().st_size != record['bytes'] or digest(path) != record['sha256']):
                raise ReleaseError(f'Release file does not match its manifest: {name}')
        if Path(str(directory / 'nfl.duckdb')+'.wal').exists():
            raise ReleaseError('Published releases cannot have pending writes')
        _report(json.loads((directory / 'validation.json').read_bytes()))
        _marks(json.loads((directory / 'watermarks.json').read_bytes()))
        return manifest
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ReleaseError('Incomplete or invalid release bundle') from error
