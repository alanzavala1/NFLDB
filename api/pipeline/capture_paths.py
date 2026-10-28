"""Resolve archived directory references without rewriting original manifests."""
import json
from pathlib import Path, PurePosixPath


MAP_NAME = 'capture-map.json'


def local_member(root, name):
    """Archive members use portable, relative paths contained by their root."""
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('Invalid capture member path')
    parts = PurePosixPath(name)
    if parts.is_absolute() or not parts.parts or any(p in ('.', '..') for p in name.split('/')):
        raise ValueError('Invalid capture member path')
    root = Path(root).resolve()
    target = root.joinpath(*parts.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError('Capture member escapes its root')
    return target


def capture_directory(context, reference):
    """Restored references must resolve inside their bundle, never to originals.

    Exact reference strings support Windows captures on Linux. Unarchived runs
    retain the existing absolute-path contract. No environment/global remapping.
    """
    context = Path(context).resolve()
    for root in (context, *context.parents):
        marker = root / MAP_NAME
        if marker.is_file():
            record = json.loads(marker.read_bytes())
            if record.get('format_version') != 1 or record.get('kind') != 'native_capture_archive':
                raise ValueError('Invalid capture relocation map')
            relative = record['directories'].get(reference)
            if relative is None:
                raise ValueError('Capture directory is missing from the relocation map')
            return local_member(root, relative)
    path = Path(reference)
    if not path.is_absolute():
        raise ValueError('Capture directory paths must be absolute')
    return path
