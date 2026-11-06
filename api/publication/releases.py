"""Publish completed native bundles without selecting or deploying them."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import uuid

import duckdb

from pipeline import releases as native
from publication.archive import verify_archive
from publication.gcs import generation, prefix


PAYLOADS = (*native.FILES, 'release.json', 'captures.zip')
MARKER = 'publication.json'


def publisher_revision():
    """Transport provenance is separate from the native analytics validation policy."""
    api = Path(__file__).resolve().parents[1]
    paths = [*(api/'publication').glob('*.py'), api/'jobs/publish.py']
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(api).as_posix().encode()+b'\0')
        digest.update(path.read_bytes().replace(b'\r\n', b'\n')+b'\0')
    return digest.hexdigest()


def fingerprint(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError('Publication requires regular files')
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block)
            md5.update(block)
            size += len(block)
    return dict(sha256=sha.hexdigest(), md5=base64.b64encode(md5.digest()).decode(), bytes=size)


def _bytes_record(data):
    return dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                md5=base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode())


def _matches(info, record, version=None):
    actual_generation = generation(info['generation'])
    if (int(info['size']) != record['bytes'] or info.get('md5Hash') != record['md5']
            or (version is not None and actual_generation != version)):
        raise ValueError('Uploaded object size, checksum or generation differs from publication')
    return actual_generation


def _json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    return fingerprint(path)


def publish(release, captures, destination, store, *, log=print):
    destination = prefix(destination)
    release, captures = Path(release).resolve(), Path(captures).absolute()
    publisher = publisher_revision()
    # Match the existing release protocol: exclude writers for the entire copy.
    with duckdb.connect(str(release/'nfl.duckdb'), read_only=True):
        paths = {name: release/name for name in PAYLOADS if name != 'captures.zip'}
        paths['captures.zip'] = captures
        # Bind bytes before checking their contents, so a replacement between
        # verification and upload cannot become the newly accepted baseline.
        expected = {name: fingerprint(path) for name, path in paths.items()}
        manifest = native.verify_release(release)
        for name in native.FILES:
            if any(expected[name][field] != manifest['files'][name][field] for field in ('sha256', 'bytes')):
                raise ValueError('Native release changed during publication preflight')
        report_bytes = (release/'validation.json').read_bytes()
        if _bytes_record(report_bytes) != expected['validation.json']:
            raise ValueError('Native report changed during publication preflight')
        report = json.loads(report_bytes)
        log('Checking capture payloads and their connection to the validated database')
        verify_archive(captures, report['source_revisions'], report['played_seasons'])
        if any(fingerprint(path) != expected[name] for name, path in paths.items()):
            raise ValueError('Local inputs changed during publication preflight')
        with tempfile.TemporaryDirectory(prefix='nfl-publication-') as temporary:
            temporary = Path(temporary)
            reservation = temporary/'reservation.json'
            record = _json(reservation, dict(format_version=1, kind='native_release_upload',
                           upload_id=uuid.uuid4().hex, destination=destination))
            _matches(store.create(destination+'/reservation.json', reservation, record['md5']), record)
            objects = {}
            for name in PAYLOADS:
                log('Uploading '+name)
                info = store.create(destination+'/'+name, paths[name], expected[name]['md5'])
                objects[name] = dict(expected[name], generation=_matches(info, expected[name]))
            # A mutation or failed upload cannot be followed by a completion marker.
            native.verify_release(release)
            if any(fingerprint(path) != expected[name] for name, path in paths.items()):
                raise ValueError('Local publication inputs changed during upload')
            if publisher_revision() != publisher:
                raise ValueError('Publisher code changed during upload')
            value = dict(format_version=1, kind='native_nfl_publication', destination=destination,
                         created_at=datetime.now(timezone.utc).isoformat(), files=objects,
                         source_revisions=report['source_revisions'], seasons=report['played_seasons'],
                         validation_code_sha256=manifest['validation_code_sha256'], publisher_code_sha256=publisher)
            marker = temporary/MARKER
            record = _json(marker, value)
            info = store.create(destination+'/'+MARKER, marker, record['md5'])
            version = _matches(info, record)
        return verify(destination, store, marker_generation=version, marker_sha256=record['sha256'])


def verify(destination, store, *, marker_generation=None, marker_sha256=None):
    """Verify transfer integrity; deployment must also verify its downloaded bundle."""
    destination = prefix(destination)
    uri = destination+'/'+MARKER
    info = store.stat(uri, marker_generation)
    version = generation(info['generation'])
    if int(info['size']) > 1024 * 1024:
        raise ValueError('Oversized publication marker')
    raw = store.read(uri, version)
    marker = _bytes_record(raw)
    _matches(info, marker, marker_generation)
    if marker_sha256 is not None and marker['sha256'] != marker_sha256:
        raise ValueError('Publication marker changed')
    value = json.loads(raw)
    if (type(value.get('format_version')) is not int or value['format_version'] != 1
            or value.get('kind') != 'native_nfl_publication' or value.get('destination') != destination
            or set(value['files']) != set(PAYLOADS)
            or value.get('validation_code_sha256') != native.validation_revision()
            or not isinstance(value.get('publisher_code_sha256'), str)
            or not re.fullmatch('[0-9a-f]{64}', value['publisher_code_sha256'])
            or set(value['source_revisions']) != {'core', 'passing'}
            or not all(isinstance(v, str) and v for v in value['source_revisions'].values())
            or not value['seasons'] or any(type(year) is not int or year < 1999 for year in value['seasons'])
            or value['seasons'] != sorted(set(value['seasons']))):
        raise ValueError('Invalid publication marker')
    for name, record in value['files'].items():
        if (type(record['bytes']) is not int or record['bytes'] < 0
                or not isinstance(record['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', record['sha256'])):
            raise ValueError('Invalid publication file record')
        pinned = generation(record['generation'])
        _matches(store.stat(destination+'/'+name, pinned), record, pinned)

    def read_json(name):
        record = value['files'][name]
        if record['bytes'] > 1024 * 1024:
            raise ValueError('Oversized release metadata')
        data = store.read(destination+'/'+name, record['generation'])
        if _bytes_record(data) != {key: record[key] for key in ('sha256', 'md5', 'bytes')}:
            raise ValueError('Downloaded release metadata differs from publication')
        return json.loads(data)

    # Reuse the native protocol's report/watermark checks. This does not rerun
    # SQL or replace deployment's full downloaded-bundle verification.
    report, manifest, marks = (read_json(name) for name in ('validation.json', 'release.json', 'watermarks.json'))
    native._report(report)
    native._marks(marks)
    if (report['source_revisions'] != value['source_revisions'] or report['played_seasons'] != value['seasons']
            or type(manifest.get('format_version')) is not int or manifest['format_version'] != 1
            or manifest.get('kind') != 'native_nfl_release' or set(manifest['files']) != set(native.FILES)
            or manifest.get('validation_code_sha256') != value['validation_code_sha256']):
        raise ValueError('Native bundle metadata differs from publication')
    for name, record in manifest['files'].items():
        if any(record[key] != value['files'][name][key] for key in ('sha256', 'bytes')):
            raise ValueError('Native bundle hashes differ from publication')
    return dict(destination=destination, manifest_generation=version, manifest_sha256=marker['sha256'],
                publication=value)
