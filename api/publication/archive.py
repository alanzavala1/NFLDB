"""Check a capture ZIP and its hash graph without a second extracted copy."""
import hashlib
import json
from pathlib import PurePosixPath
import re
import zipfile

from pipeline.capture_paths import MAP_NAME


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Invalid capture SHA256')
    return value


def _directory(value):
    if not isinstance(value, str) or not re.fullmatch(r'objects/[0-9]+', value):
        raise ValueError('Invalid capture object directory')
    return value


def _filename(value):
    if (not isinstance(value, str) or not value or value in ('.', '..', MAP_NAME)
            or any(char in value for char in '/\\:') or PurePosixPath(value).name != value):
        raise ValueError('Invalid capture filename')
    return value


def verify_archive(path, expected_revisions, expected_seasons):
    """Verify every payload, declared child and root identity against the release.

    This verifies transport/provenance, not statistical calculations. Those were
    checked when the native release was created. No paths inside JSON are opened
    on the local filesystem, and nothing is extracted.
    """
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or names.count(MAP_NAME) != 1:
            raise ValueError('Duplicate or missing archive members')
        record = json.loads(archive.read(MAP_NAME))
        if (type(record.get('format_version')) is not int or record['format_version'] != 1
                or record.get('kind') != 'native_capture_archive'):
            raise ValueError('Unsupported capture archive')
        files, directories, roots = record['files'], record['directories'], record['roots']
        if (not files or not directories or set(roots) != {'core', 'passing'}
                or set(names) != {MAP_NAME, *files}):
            raise ValueError('Invalid capture inventory')
        targets = {_directory(value) for value in directories.values()}
        if not {_directory(value) for value in roots.values()} <= targets:
            raise ValueError('Missing capture roots')
        manifests = {}
        for name, item in files.items():
            parent, filename = name.rsplit('/', 1)
            if _directory(parent) not in targets:
                raise ValueError('Unknown capture directory')
            _filename(filename)
            info = archive.getinfo(name)
            if (info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000
                    or type(item['bytes']) is not int or item['bytes'] < 0
                    or item['bytes'] != info.file_size):
                raise ValueError('Invalid capture payload')
            digest = hashlib.sha256()
            if filename == 'run.json':
                raw = archive.read(name)
                digest.update(raw)
                manifests[parent] = json.loads(raw)
            else:
                with archive.open(name) as stream:
                    while block := stream.read(1024 * 1024):
                        digest.update(block)
            if digest.hexdigest() != _sha(item['sha256']):
                raise ValueError(f'Capture payload changed: {name}')
        visited, active, declared = set(), set(), set()

        def visit(directory):
            if directory in active:
                raise ValueError('Cyclic capture references')
            if directory in visited:
                return
            active.add(directory)
            manifest = manifests[directory]
            members = {**manifest.get('files', {}), 'run.json': files[directory+'/run.json']['sha256']}
            for name, digest in members.items():
                member = directory+'/'+_filename(name)
                if files[member]['sha256'] != _sha(digest):
                    raise ValueError('Capture inventory differs from declared source hashes')
                declared.add(member)

            def child(reference, expected):
                target = _directory(directories[reference])
                if files[target+'/run.json']['sha256'] != _sha(expected):
                    raise ValueError('Indexed capture revision changed')
                visit(target)

            kind = manifest.get('kind')
            children = manifest.get('bundles', []) if kind == 'receiving_core_collection' else (
                manifest.get('exports', []) if kind == 'passing_export_collection' else [])
            for item in children:
                child(item['directory'], item['manifest_sha256'])
            if 'source_directory' in manifest:
                child(manifest['source_directory'], manifest['files']['receiving-run.json'])
            active.remove(directory)
            visited.add(directory)

        for root in roots.values():
            visit(root)
        if targets != visited or set(files) != declared:
            raise ValueError('Unreferenced or undeclared capture payloads')
        core, passing = (manifests[roots[key]] for key in ('core', 'passing'))
        seasons = core['seasons']
        if (seasons != expected_seasons or passing['seasons'] != seasons
                or not seasons or any(type(year) is not int or year < 1999 for year in seasons)
                or seasons != sorted(set(seasons)) or passing.get('kind') != 'passing_export_collection'):
            raise ValueError('Capture seasons differ from validated release')
        core_sha, passing_sha = (files[roots[key]+'/run.json']['sha256'] for key in ('core', 'passing'))
        if core.get('kind') == 'receiving_core_collection':
            core_revision = f'receiving core collection SHA256 {core_sha} ({len(seasons)} seasons)'
        elif core.get('format_version') == 1 and 'source_directory' in core:
            core_revision = f"receiving core bundle SHA256 {core_sha}; receiving run SHA256 {core['files']['receiving-run.json']}"
        else:
            raise ValueError('Unsupported core root')
        revisions = dict(core=core_revision, passing=f'passing export collection SHA256 {passing_sha} ({len(seasons)} seasons)')
        if record['revisions'] != revisions or revisions != expected_revisions:
            raise ValueError('Capture archive does not match the validated release')
        return dict(files=len(files), seasons=seasons, revisions=revisions)
