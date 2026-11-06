"""Download a selected snapshot to a new directory and verify it before use."""
import json
import os
from pathlib import Path

from pipeline import releases as native
from publication.archive import verify_archive
from publication.releases import fingerprint, publisher_revision, verify
from publication.selection import read_selection


def download_selected(pointer, output, store, *, pointer_generation=None, pointer_sha256=None,
                      include_captures=False, log=print):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Download output must be a new directory')
    worker = publisher_revision()
    selected = read_selection(pointer, store, pointer_generation=pointer_generation, pointer_sha256=pointer_sha256)
    selection = selected['selection']
    receipt = verify(selection['destination'], store, marker_generation=selection['manifest_generation'],
                     marker_sha256=selection['manifest_sha256'])
    publication = receipt['publication']
    names = [*native.FILES, 'release.json']
    if include_captures:
        names.append('captures.zip')
    output.mkdir()  # No existing output, database or local selection is replaced.
    written, folders, records = [], [output], {}
    try:
        release = output/'release'
        release.mkdir()
        folders.append(release)
        for name in names:
            path = output/name if name == 'captures.zip' else release/name
            log('Downloading '+name)
            record = publication['files'][name]
            with path.open('xb') as target:
                written.append(path)
                store.download(selection['destination']+'/'+name, record['generation'], target)
                target.flush()
                os.fsync(target.fileno())
            actual = fingerprint(path)
            if any(actual[key] != record[key] for key in actual):
                raise ValueError('Downloaded file differs from publication: '+name)
            records[path.relative_to(output).as_posix()] = actual
        native.verify_release(release)
        if include_captures:
            log('Checking downloaded capture archive')
            verify_archive(output/'captures.zip', publication['source_revisions'], publication['seasons'])
        if publisher_revision() != worker:
            raise ValueError('Download code changed during verification')
        for relative, expected in records.items():
            if fingerprint(output/relative) != expected:
                raise ValueError('Downloaded file changed before completion')
        result = dict(format_version=1, kind='native_release_download', selection=selected,
                      publication=receipt, includes_captures=include_captures, files=records,
                      consumer_code_sha256=worker)
        with (output/'download.json').open('x',encoding='utf-8',newline='\n') as stream:
            written.append(output/'download.json')
            json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        return result
    except BaseException:
        for path in reversed(written):
            path.unlink()
        for folder in reversed(folders):
            # Preserve unexpected files created by another actor; never recurse.
            try:
                folder.rmdir()
            except OSError:
                pass
        raise
