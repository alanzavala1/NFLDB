"""A conditional cloud selection of one completed, immutable publication."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
import uuid

from publication.gcs import generation, prefix
from publication.releases import _bytes_record, _json, _matches, verify


def pointer_uri(value):
    if not isinstance(value, str) or '/' not in value:
        raise ValueError('Supply a gs://bucket/path/selection.json URI')
    parent, name = value.rsplit('/', 1)
    prefix(parent)
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*\.json', name):
        raise ValueError('Selection must use a plain JSON object name')
    return value


def manifest_sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Supply the recorded publication manifest SHA256')
    return value


def read_selection(pointer, store, *, pointer_generation=None, pointer_sha256=None):
    pointer = pointer_uri(pointer)
    info = store.stat(pointer, pointer_generation)
    version = generation(info['generation'])
    if int(info['size']) > 65536:
        raise ValueError('Oversized cloud selection')
    raw = store.read(pointer, version)
    record = _bytes_record(raw)
    _matches(info, record, pointer_generation)
    if pointer_sha256 is not None and record['sha256'] != manifest_sha(pointer_sha256):
        raise ValueError('Cloud selection identity changed')
    value = json.loads(raw)
    if (type(value.get('format_version')) is not int or value['format_version'] != 1
            or value.get('kind') != 'native_nfl_selection'
            or not isinstance(value.get('selection_id'), str)
            or not re.fullmatch('[0-9a-f]{32}', value['selection_id'])
            or not isinstance(value.get('selected_at'), str) or not value['selected_at']):
        raise ValueError('Invalid cloud selection')
    destination = prefix(value['destination'])
    generation(value['manifest_generation'])
    manifest_sha(value['manifest_sha256'])
    if pointer.startswith(destination+'/'):
        raise ValueError('Selection must stay outside the immutable release')
    return dict(pointer=pointer, pointer_generation=version, pointer_sha256=record['sha256'], selection=value)


def select_release(pointer, destination, store, *, expected_generation, manifest_generation, manifest_sha256):
    """Caller supplies the pointer generation observed before its work began.

    Zero means an explicitly absent initial pointer. Never reread and retry on a
    conflict: that would let a stale job replace a newer selection. This selects
    artifacts only; deployment is a separate operation.
    """
    pointer, destination = pointer_uri(pointer), prefix(destination)
    expected = expected_generation if expected_generation == '0' else generation(expected_generation)
    if pointer.startswith(destination+'/'):
        raise ValueError('Selection must stay outside the immutable release')
    version, digest = generation(manifest_generation), manifest_sha(manifest_sha256)
    verify(destination, store, marker_generation=version, marker_sha256=digest)
    value = dict(format_version=1, kind='native_nfl_selection', selection_id=uuid.uuid4().hex,
                 selected_at=datetime.now(timezone.utc).isoformat(), destination=destination,
                 manifest_generation=version, manifest_sha256=digest)
    with tempfile.TemporaryDirectory(prefix='nfl-selection-') as temporary:
        path = Path(temporary)/'selection.json'
        record = _json(path, value)
        info = store.replace(pointer, path, record['md5'], expected)
        selected_version = _matches(info, record)
    return read_selection(pointer, store, pointer_generation=selected_version, pointer_sha256=record['sha256'])
