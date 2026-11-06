"""One atomic local selection of an immutable DB + watermarks release."""
import json
import os
from pathlib import Path
import uuid

from pipeline.releases import ReleaseError, digest, verify_release


def select_release(release, pointer, *, expected=None):
    """Compare-and-swap with a writer lock; select DB and watermarks together.

    `expected=None` is first publication only. Updates require the SHA256 of
    the pointer the operator/job read. A failure leaves the previous selection.
    Local pointer only: cloud storage must implement its own generation match.
    """
    release, pointer = Path(release).resolve(), Path(pointer).absolute()
    if pointer.resolve().is_relative_to(release):
        raise ReleaseError('Selection pointer must be outside immutable release directories')
    lock = pointer.with_name(pointer.name + '.lock')
    temporary = pointer.with_name(pointer.name + '.' + uuid.uuid4().hex + '.tmp')
    # mkdir is deliberately not implicit; caller chooses the publication root.
    # Close the reservation descriptor before cleanup (Windows cannot unlink
    # an open file). The exclusive path itself remains the writer reservation.
    with lock.open('x'):
        pass
    try:
        if pointer.is_symlink() or (pointer.exists() and digest(pointer) != expected) or (not pointer.exists() and expected is not None):
            raise ReleaseError('Current release changed; reload its selection before publishing')
        verify_release(release)
        value = {'format_version': 1, 'release_directory': str(release),
                 'release_manifest_sha256': digest(release / 'release.json')}
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, pointer)
    finally:
        temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)
    return value


def current_release(pointer):
    value = json.loads(Path(pointer).read_bytes())
    directory = Path(value['release_directory'])
    if value.get('format_version') != 1 or not directory.is_absolute():
        raise ReleaseError('Invalid release selection')
    if digest(directory / 'release.json') != value['release_manifest_sha256']:
        raise ReleaseError('Selected release manifest changed')
    verify_release(directory)
    return directory
