"""Portable, lossless native captures using the standard ZIP container."""
import hashlib
import json
from pathlib import Path
import zipfile

from pipeline.capture_paths import MAP_NAME, capture_directory, local_member
from pipeline.passing_inputs import PassingInputs
from pipeline.receiving_core_collection import open_core_inputs


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _plain(name):
    local_member(Path.cwd(), name)
    if '/' in name or name == MAP_NAME:
        raise ValueError('Capture files must be plain filenames')
    return name


def _inputs(core, passing):
    core, passing = open_core_inputs(core), PassingInputs(passing)
    if core.seasons != passing.seasons:
        raise ValueError('Core and passing captures must cover the same seasons')
    return core, passing


def pack_captures(core, passing, output):
    """Copy declared files only; preserve manifests and their revisions exactly.

    Hash checks establish byte integrity. Native semantic/source validation is
    still required before building a release. This records no new watermarks.
    """
    core, passing, output = Path(core).resolve(), Path(passing).resolve(), Path(output).absolute()
    before = _inputs(core, passing)
    directories, objects, inventory = {}, {}, {}

    def visit(directory, reference):
        directory = directory.resolve()
        if directory in objects:
            directories[reference] = objects[directory]
            return objects[directory]
        relative = f'objects/{len(objects):04d}'
        objects[directory] = relative
        directories[reference] = relative
        directories[str(directory)] = relative
        marker = directory / 'run.json'
        raw = marker.read_bytes()
        record = json.loads(raw)
        files = dict(record.get('files', {}))
        files['run.json'] = hashlib.sha256(raw).hexdigest()
        for name, expected in files.items():
            path = directory / _plain(name)
            if path.is_symlink() or not path.is_file() or _sha(path) != expected:
                raise ValueError(f'Changed or invalid capture file: {path}')
            inventory[f'{relative}/{name}'] = {'sha256': expected, 'bytes': path.stat().st_size}
        children = record.get('bundles', []) if record.get('kind') == 'receiving_core_collection' else (
            record.get('exports', []) if record.get('kind') == 'passing_export_collection' else [])
        for child in children:
            ref = child['directory']
            path = capture_directory(directory, ref)
            if _sha(path / 'run.json') != child['manifest_sha256']:
                raise ValueError('Changed indexed capture revision')
            visit(path, ref)
        if 'source_directory' in record:
            ref = record['source_directory']
            path = capture_directory(directory, ref)
            if _sha(path / 'run.json') != record['files']['receiving-run.json']:
                raise ValueError('Changed receiving source revision')
            visit(path, ref)
        return relative

    roots = {'core': visit(core, str(core)), 'passing': visit(passing, str(passing))}
    manifest = {'format_version': 1, 'kind': 'native_capture_archive', 'roots': roots,
                'directories': directories, 'files': inventory,
                'revisions': {'core': before[0].revision(), 'passing': before[1].revision()},
                'scope': 'Existing captured bytes; no upstream freshness acknowledgment'}
    # Exclusive creation: failed packing may remove only this call's own file.
    with output.open('xb') as target:
        try:
            with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                for directory, relative in objects.items():
                    for member, record in inventory.items():
                        if member.rsplit('/', 1)[0] != relative:
                            continue
                        path = directory / member.rsplit('/', 1)[1]
                        archive.write(path, member)
                        if _sha(path) != record['sha256']:
                            raise ValueError('Capture changed during packing')
                archive.writestr(MAP_NAME, json.dumps(manifest, indent=2, sort_keys=True))
        except BaseException:
            target.close()
            output.unlink()
            raise
    return manifest


def restore_captures(archive_path, output):
    """Restore into a new directory, reject unsafe members, verify every byte.

    No extractall, path rewriting, source downloads, database writes or R runs.
    The completion map is written only after every payload hash has passed.
    """
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or names.count(MAP_NAME) != 1:
            raise ValueError('Duplicate or missing capture archive members')
        raw = archive.read(MAP_NAME)
        manifest = json.loads(raw)
        if (type(manifest.get('format_version')) is not int or manifest['format_version'] != 1
                or manifest.get('kind') != 'native_capture_archive'):
            raise ValueError('Unsupported capture archive')
        files = manifest['files']
        if not files or set(names) != {*files, MAP_NAME}:
            raise ValueError('Capture inventory differs from archive members')
        roots, references = manifest['roots'], manifest['directories']
        if set(roots) != {'core', 'passing'} or not references:
            raise ValueError('Invalid capture roots/references')
        targets = set(references.values())
        for target in [*targets, *roots.values()]:
            local_member(output, target)
            parts = target.split('/')
            if len(parts) != 2 or parts[0] != 'objects' or not parts[1].isdigit():
                raise ValueError('Invalid capture directory member')
            if target not in targets or f'{target}/run.json' not in files:
                raise ValueError('Missing capture directory manifest')
        for name, record in files.items():
            local_member(output, name)
            parent, filename = name.rsplit('/', 1)
            _plain(filename)
            info = archive.getinfo(name)
            mode = info.external_attr >> 16
            if (parent not in targets or info.is_dir() or (mode & 0o170000) == 0o120000
                    or type(record['bytes']) is not int or record['bytes'] < 0
                    or info.file_size != record['bytes'] or not isinstance(record['sha256'], str)
                    or len(record['sha256']) != 64):
                raise ValueError('Invalid capture payload record')
        output.mkdir()  # From here onward cleanup owns only explicitly created paths.
        written, folders = [], [output]
        try:
            parent = output / 'objects'
            parent.mkdir()
            folders.append(parent)
            for target in sorted(targets):
                path = local_member(output, target)
                path.mkdir()
                folders.append(path)
            for name, record in files.items():
                path = local_member(output, name)
                with path.open('xb') as target:
                    written.append(path)
                    with archive.open(name) as origin:
                        digest = hashlib.sha256()
                        while block := origin.read(1024 * 1024):
                            target.write(block)
                            digest.update(block)
                if digest.hexdigest() != record['sha256']:
                    raise ValueError(f'Capture payload hash mismatch: {name}')
            marker = output / MAP_NAME
            with marker.open('xb') as stream:
                written.append(marker)
                stream.write(raw)
            loaded = _inputs(*(local_member(output, roots[key]) for key in ('core', 'passing')))
            if manifest['revisions'] != dict(core=loaded[0].revision(), passing=loaded[1].revision()):
                raise ValueError('Restored capture revisions changed')
        except BaseException:
            for path in reversed(written):
                path.unlink()
            for path in reversed(folders):
                path.rmdir()
            raise
    return {key: local_member(output, value) for key, value in roots.items()}
