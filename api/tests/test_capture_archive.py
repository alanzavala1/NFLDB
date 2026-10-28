"""Relocation must preserve identities and never fall back to original paths."""
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from pipeline.capture_archive import pack_captures, restore_captures
from pipeline.capture_paths import MAP_NAME, capture_directory
from pipeline.passing_exports import passing_policy
from pipeline.passing_inputs import PassingInputs
from pipeline.receiving_core_collection import assemble_core_inputs, open_core_inputs
from pipeline.receiving_preview import file_sha256
from tests.test_receiving_core_inputs import bundle


@pytest.fixture
def captures(bundle, tmp_path):
    core = assemble_core_inputs([bundle], tmp_path / 'collection', log=lambda _: None)
    export = tmp_path / 'passing-export'
    export.mkdir()
    (export / 'run.json').write_text('{}')
    passing = tmp_path / 'passing'
    passing.mkdir()
    record = {'format_version': 1, 'kind': 'passing_export_collection', 'seasons': [2024],
              'policy': passing_policy(), 'exports': [{'season': 2024, 'directory': str(export),
                                                      'manifest_sha256': file_sha256(export / 'run.json')}]}
    (passing / 'run.json').write_text(json.dumps(record))
    return core.directory, passing


def rewrite_archive(source, target, change):
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    change(members)
    with zipfile.ZipFile(target, 'w') as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def test_restore_preserves_manifests_feeds_and_never_reads_originals(captures, tmp_path):
    core, passing = captures
    original = open_core_inputs(core)
    expected = original.feeds([2024])
    archive = tmp_path / 'captures.zip'
    manifest = pack_captures(core, passing, archive)
    # Remove every original source, including paths that still exist in JSON.
    originals = {Path(value) for value in manifest['directories']}
    for path in originals:
        destination = path.with_name(path.name + '-unavailable')
        assert path.resolve().is_relative_to(tmp_path.resolve())
        assert destination.resolve().is_relative_to(tmp_path.resolve())
        path.rename(destination)
    result = restore_captures(archive, tmp_path / 'restored')
    restored = open_core_inputs(result['core'])
    assert restored.revision() == original.revision()
    assert PassingInputs(result['passing']).revision() == manifest['revisions']['passing']
    for actual, source in zip(restored.feeds([2024]), expected):
        pd.testing.assert_frame_equal(actual.data, source.data)
    for relative, record in manifest['files'].items():
        assert file_sha256(tmp_path / 'restored' / relative) == record['sha256']
    # A second relocation retains exactly the same source revisions too.
    repacked = tmp_path / 'repacked.zip'
    assert pack_captures(result['core'], result['passing'], repacked)['revisions'] == manifest['revisions']
    again = restore_captures(repacked, tmp_path / 'again')
    assert open_core_inputs(again['core']).revision() == original.revision()


def test_single_core_bundle_and_existing_outputs(captures, tmp_path):
    collection, passing = captures
    core = next(iter(open_core_inputs(collection).owners.values())).directory
    output = tmp_path / 'capture.zip'
    pack_captures(core, passing, output)
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        pack_captures(core, passing, output)
    assert output.read_bytes() == before
    destination = tmp_path / 'restored'
    result = restore_captures(output, destination)
    with pytest.raises(FileExistsError):
        restore_captures(output, destination)
    assert open_core_inputs(result['core']).seasons == [2024]


@pytest.mark.parametrize('change', ['extra', 'missing', 'bytes', 'hash', 'traversal', 'backslash', 'absolute', 'map_escape'])
def test_corrupt_or_unsafe_archive_leaves_no_completed_restore(captures, tmp_path, change):
    source, broken, output = (tmp_path / name for name in ('capture.zip', 'broken.zip', 'restored'))
    pack_captures(*captures, source)
    def alter(members):
        record = json.loads(members[MAP_NAME])
        name = next(name for name in members if name.endswith('/plays-2024.csv'))
        if change == 'extra':
            members['unknown.txt'] = b'x'
        elif change == 'missing':
            del members[name]
        elif change == 'bytes':
            members[name] += b'changed'
        elif change == 'hash':
            members[name] = members[name].replace(b'2024', b'2025')
        elif change == 'map_escape':
            record['directories'][next(iter(record['directories']))] = '../outside'
        else:
            unsafe = {'traversal': '../outside', 'backslash': 'objects\\outside', 'absolute': '/outside'}[change]
            members[unsafe] = members.pop(name)
            record['files'][unsafe] = record['files'].pop(name)
        members[MAP_NAME] = json.dumps(record).encode()
    rewrite_archive(source, broken, alter)
    with pytest.raises(ValueError):
        restore_captures(broken, output)
    assert not output.exists()
    assert not (tmp_path / 'outside').exists()


def test_duplicate_and_symlink_members_rejected(captures, tmp_path):
    source, broken = tmp_path / 'capture.zip', tmp_path / 'broken.zip'
    pack_captures(*captures, source)
    with zipfile.ZipFile(source) as origin, zipfile.ZipFile(broken, 'w') as target:
        for name in origin.namelist():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o120777 << 16 if name.endswith('/plays-2024.csv') else 0
            target.writestr(info, origin.read(name))
    with pytest.raises(ValueError, match='payload'):
        restore_captures(broken, tmp_path / 'restored')
    with zipfile.ZipFile(source, 'a') as target:
        with pytest.warns(UserWarning):
            target.writestr(MAP_NAME, b'{}')
    with pytest.raises(ValueError, match='Duplicate'):
        restore_captures(source, tmp_path / 'restored')


def test_changed_source_and_failed_packing_preserve_previous_paths(captures, tmp_path, monkeypatch):
    source = tmp_path / 'capture.zip'
    original_write = zipfile.ZipFile.write
    def fail(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr(zipfile.ZipFile, 'write', fail)
    with pytest.raises(OSError, match='disk failure'):
        pack_captures(*captures, source)
    assert not source.exists()
    monkeypatch.setattr(zipfile.ZipFile, 'write', original_write)
    core = next(iter(open_core_inputs(captures[0]).owners.values())).directory
    (core / 'plays-2024.csv').write_text('corrupt')
    with pytest.raises(ValueError, match='Changed'):
        pack_captures(*captures, source)
    assert not source.exists()


def test_foreign_paths_resolve_inside_restored_root_and_missing_mapping_fails(tmp_path):
    root = tmp_path / 'restored'
    context = root / 'objects/0000'
    context.mkdir(parents=True)
    foreign = r'C:\Users\old-machine\captures'
    marker = root / MAP_NAME
    marker.write_text(json.dumps({'format_version': 1, 'kind': 'native_capture_archive',
                                 'directories': {foreign: 'objects/0000'}}))
    assert capture_directory(context, foreign) == context
    with pytest.raises(ValueError, match='missing'):
        capture_directory(context, str(tmp_path))  # Exists, but fallback is forbidden.


def test_archive_reader_open_failure_cleans_new_destination_file(captures, tmp_path, monkeypatch):
    source, output = tmp_path / 'capture.zip', tmp_path / 'restored'
    pack_captures(*captures, source)
    original = zipfile.ZipFile.open
    def fail_on_payload(self, name, *args, **kwargs):
        if str(name).endswith('/plays-2024.csv'):
            raise OSError('payload could not be opened')
        return original(self, name, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, 'open', fail_on_payload)
    with pytest.raises(OSError, match='payload could not be opened'):
        restore_captures(source, output)
    assert not output.exists()
