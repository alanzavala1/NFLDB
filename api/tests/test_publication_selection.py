"""Conditional selection and verified downloads preserve prior usable snapshots."""
import io
import json
from pathlib import Path
import subprocess

import pytest

from pipeline import releases as native
from publication import downloads, gcs, selection
from tests.test_publication import Store, case, captures, bundle, release_case, publish, md5, DESTINATION


POINTER = 'gs://test-bucket/native/trials/current.json'


class SelectedStore(Store):
    def __init__(self):
        super().__init__()
        self.sequence = 1000
        self.before_download = lambda uri: None
        self.fail_download = None
        self.corrupt_download = None

    def replace(self, uri, path, expected_md5, expected_generation):
        self.events.append(('replace',uri,expected_generation))
        if self.latest.get(uri, '0') != expected_generation:
            raise FileExistsError('generation precondition failed')
        data = Path(path).read_bytes()
        assert md5(data) == expected_md5
        self.sequence += 1
        version = str(self.sequence)
        self.latest[uri] = version
        self.objects[uri,version] = data
        return self.stat(uri)

    def download(self, uri, version, target):
        self.before_download(uri)
        self.events.append(('download',uri,version))
        name = uri.rsplit('/',1)[1]
        if name == self.fail_download:
            target.write(b'partial bytes')
            raise OSError('connection interrupted')
        target.write(b'corrupted' if name == self.corrupt_download else self.objects[uri,version])


@pytest.fixture
def prepared(case):
    release, packed, report, _ = case
    store = SelectedStore()
    values = (release,packed,report,store)
    receipt = publish(values)
    return values,receipt


def choose(prepared, expected='0', receipt=None, pointer=POINTER):
    values, original = prepared
    receipt = receipt or original
    return selection.select_release(pointer, receipt['destination'], values[3], expected_generation=expected,
                                    manifest_generation=receipt['manifest_generation'], manifest_sha256=receipt['manifest_sha256'])


def test_initial_selection_and_update_require_exact_observed_generation(prepared):
    store = prepared[0][3]
    first = choose(prepared)
    second = choose(prepared, first['pointer_generation'])
    assert second['pointer_generation'] != first['pointer_generation']
    before = dict(store.objects)
    for stale in ('0',first['pointer_generation']):
        with pytest.raises(FileExistsError):
            choose(prepared,stale)
        assert store.objects == before
    assert selection.read_selection(POINTER,store) == second


def test_explicit_rollback_uses_a_fresh_selection_generation(prepared):
    values, receipt = prepared
    first = choose(prepared)
    other = publish(values, DESTINATION+'-other')
    second = choose(prepared,first['pointer_generation'],other)
    restored = choose(prepared,second['pointer_generation'],receipt)
    assert restored['selection']['destination'] == receipt['destination']


def test_incomplete_or_wrong_manifest_cannot_replace_selection(prepared):
    values, receipt = prepared
    first = choose(prepared)
    store = values[3]
    before = store.objects[POINTER,first['pointer_generation']]
    for version,digest in [('99999',receipt['manifest_sha256']), (receipt['manifest_generation'],'0'*64)]:
        with pytest.raises((KeyError,ValueError)):
            selection.select_release(POINTER,DESTINATION,store,expected_generation=first['pointer_generation'],
                                     manifest_generation=version,manifest_sha256=digest)
        assert store.latest[POINTER] == first['pointer_generation']
        assert store.read(POINTER,first['pointer_generation']) == before


@pytest.mark.parametrize('expected',[None,0,'','-1','1&command'])
def test_invalid_expectation_is_not_replaced_with_a_fresh_read(prepared,expected):
    with pytest.raises(ValueError):
        choose(prepared,expected)
    assert POINTER not in prepared[0][3].latest


@pytest.mark.parametrize('pointer', ['gs://test-bucket/current.json',DESTINATION+'/current.json',
                                   'gs://test-bucket/native/../current.json','gs://test-bucket/native/*.json'])
def test_unsafe_pointer_locations_are_rejected(prepared,pointer):
    with pytest.raises(ValueError):
        choose(prepared,pointer=pointer)
    assert pointer not in prepared[0][3].latest


def test_pinned_selection_can_be_read_and_wrong_identity_fails(prepared):
    first = choose(prepared)
    choose(prepared,first['pointer_generation'])
    store = prepared[0][3]
    assert selection.read_selection(POINTER,store,pointer_generation=first['pointer_generation'],
                                    pointer_sha256=first['pointer_sha256']) == first
    with pytest.raises(ValueError,match='identity changed'):
        selection.read_selection(POINTER,store,pointer_sha256='0'*64)


@pytest.mark.parametrize('captures_included',[False,True])
def test_download_checks_every_byte_and_native_bundle_before_completion(prepared,tmp_path,captures_included):
    values, receipt = prepared
    first = choose(prepared)
    output = tmp_path/'download'
    result = downloads.download_selected(POINTER,output,values[3],include_captures=captures_included,log=lambda _:None)
    assert result == json.loads((output/'download.json').read_bytes())
    assert result['selection'] == first and result['publication'] == receipt
    native.verify_release(output/'release')
    assert (output/'captures.zip').exists() == captures_included
    for name in native.FILES+('release.json',):
        assert native.digest(output/'release'/name) == native.digest(values[0]/name)
    if captures_included:
        assert native.digest(output/'captures.zip') == native.digest(values[1])
    assert len([event for event in values[3].events if event[0]=='download']) == 4+captures_included


def test_download_finishes_one_snapshot_when_cloud_selection_changes(prepared,tmp_path):
    values, receipt = prepared
    first = choose(prepared)
    other = publish(values,DESTINATION+'-other')
    store = values[3]
    def change(uri):
        if uri.endswith('/nfl.duckdb'):
            choose(prepared,first['pointer_generation'],other)
    store.before_download = change
    result = downloads.download_selected(POINTER,tmp_path/'download',store,log=lambda _:None)
    assert result['selection'] == first
    assert selection.read_selection(POINTER,store)['selection']['destination'] == other['destination']
    assert all(event[1].startswith(DESTINATION+'/') for event in store.events if event[0]=='download')


@pytest.mark.parametrize('fault',['interrupt','corrupt'])
@pytest.mark.parametrize('name',[*native.FILES,'release.json','captures.zip'])
def test_bad_download_leaves_no_ready_output_or_changes_to_original(prepared,tmp_path,name,fault):
    values,_ = prepared
    first = choose(prepared)
    store = values[3]
    setattr(store,'fail_download' if fault=='interrupt' else 'corrupt_download',name)
    before = native.digest(values[0]/'nfl.duckdb')
    with pytest.raises((OSError,ValueError)):
        downloads.download_selected(POINTER,tmp_path/'download',store,include_captures=True,log=lambda _:None)
    assert not (tmp_path/'download').exists()
    assert native.digest(values[0]/'nfl.duckdb') == before
    assert selection.read_selection(POINTER,store) == first


def test_existing_output_is_preserved_before_any_cloud_read(prepared,tmp_path):
    output = tmp_path/'download'
    output.mkdir()
    (output/'sentinel').write_text('keep')
    store = prepared[0][3]
    before = list(store.events)
    with pytest.raises(FileExistsError):
        downloads.download_selected(POINTER,output,store)
    assert store.events == before and (output/'sentinel').read_text() == 'keep'


def test_failed_download_preserves_unexpected_files_in_owned_directory(prepared,tmp_path):
    choose(prepared)
    store = prepared[0][3]
    output = tmp_path/'download'
    store.before_download = lambda _: (output/'external.txt').write_text('keep')
    store.fail_download = 'nfl.duckdb'
    with pytest.raises(OSError,match='interrupted'):
        downloads.download_selected(POINTER,output,store,log=lambda _:None)
    assert (output/'external.txt').read_text() == 'keep'
    assert not (output/'download.json').exists() and not (output/'release').exists()


def test_consumer_code_drift_rejects_download_before_completion(prepared,tmp_path,monkeypatch):
    choose(prepared)
    store = prepared[0][3]
    store.before_download = lambda _: monkeypatch.setattr(downloads,'publisher_revision',lambda:'0'*64)
    with pytest.raises(ValueError,match='code changed'):
        downloads.download_selected(POINTER,tmp_path/'download',store,log=lambda _:None)
    assert not (tmp_path/'download').exists()


def test_local_file_changed_after_its_check_is_rejected(prepared,tmp_path):
    choose(prepared)
    output = tmp_path/'download'
    def change(uri):
        if uri.endswith('/watermarks.json'):
            (output/'release/nfl.duckdb').write_bytes(b'changed after download')
    prepared[0][3].before_download = change
    with pytest.raises(native.ReleaseError):
        downloads.download_selected(POINTER,output,prepared[0][3],log=lambda _:None)
    assert not output.exists()


def test_missing_pinned_object_never_falls_back_to_latest(prepared,tmp_path):
    values,receipt = prepared
    choose(prepared)
    store = values[3]
    uri = DESTINATION+'/nfl.duckdb'
    del store.objects[uri,receipt['publication']['files']['nfl.duckdb']['generation']]
    store.latest[uri] = '9999'
    store.objects[uri,'9999'] = b'new bytes'
    with pytest.raises(KeyError):
        downloads.download_selected(POINTER,tmp_path/'download',store,log=lambda _:None)
    assert not (tmp_path/'download').exists()


def test_adapter_conditions_updates_and_streams_exact_generation(monkeypatch,tmp_path):
    monkeypatch.setattr(gcs,'command',lambda:['sdk-python','gcloud.py'])
    calls = []
    def run(args,**options):
        calls.append((args,options))
        if '--do-not-decompress' in args:
            Path(args[-3]).write_bytes(b'\x00\xffbinary')
            return subprocess.CompletedProcess(args,0)
        return subprocess.CompletedProcess(args,0,json.dumps({'generation':'200','size':'4','md5Hash':md5(b'data')}).encode())
    monkeypatch.setattr(gcs.subprocess,'run',run)
    store = gcs.GCloudStore()
    store.replace(POINTER,tmp_path/'selection',md5(b'data'),'123')
    assert '--if-generation-match=123' in calls[0][0]
    target = io.BytesIO()
    store.download(DESTINATION+'/nfl.duckdb','456',target)
    assert target.getvalue() == b'\x00\xffbinary'
    assert any(value.endswith('/nfl.duckdb#456') for value in calls[-1][0])
    assert '--no-clobber' in calls[-1][0] and not Path(calls[-1][0][-3]).exists()
    assert calls[-1][1]['check'] and calls[-1][1]['timeout'] == 1800


def test_adapter_timeout_cleans_only_private_staging(monkeypatch):
    monkeypatch.setattr(gcs,'command',lambda:['sdk-python','gcloud.py'])
    staged_paths = []
    def fail(args,**options):
        staged = Path(args[-3])
        staged_paths.append(staged)
        staged.write_bytes(b'partial download')
        raise subprocess.TimeoutExpired(args,options['timeout'])
    monkeypatch.setattr(gcs.subprocess,'run',fail)
    target = io.BytesIO()
    with pytest.raises(subprocess.TimeoutExpired):
        gcs.GCloudStore().download(DESTINATION+'/nfl.duckdb','456',target)
    assert target.getvalue() == b'' and not staged_paths[0].parent.exists()
