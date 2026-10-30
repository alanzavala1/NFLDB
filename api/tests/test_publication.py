"""The upload completion marker is never issued for partial or mixed releases."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from pipeline import releases as native
from pipeline.capture_archive import pack_captures
from pipeline.capture_paths import MAP_NAME
from publication import archive, gcs, releases
from tests.test_capture_archive import captures, rewrite_archive
from tests.test_receiving_core_inputs import bundle
from tests.test_releases import release_case


DESTINATION = 'gs://test-bucket/native/releases/test-release'


def md5(data):
    return base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode()


class Store:
    def __init__(self):
        self.objects, self.latest, self.events = {}, {}, []
        self.after_create = lambda uri: None
        self.fail_name = None
        self.bad_metadata = None

    def create(self, uri, path, expected_md5):
        self.events.append(('create', uri))
        if uri in self.latest:
            raise FileExistsError('generation match 0 failed')
        if uri.endswith('/'+str(self.fail_name)):
            raise OSError('interrupted upload')
        data = Path(path).read_bytes()
        if md5(data) != expected_md5:
            raise ValueError('server rejected content MD5')
        version = str(len(self.objects)+1)
        self.objects[uri, version] = data
        self.latest[uri] = version
        self.after_create(uri)
        return self.stat(uri)

    def stat(self, uri, version=None):
        version = version or self.latest[uri]
        data = self.objects[uri, version]
        result = dict(generation=version, size=str(len(data)), md5Hash=md5(data))
        if uri.endswith('/'+str(self.bad_metadata)):
            result['md5Hash'] = 'wrong'
        self.events.append(('stat', uri, version))
        return result

    def read(self, uri, version):
        self.events.append(('read', uri, version))
        return self.objects[uri, version]


@pytest.fixture
def case(captures, release_case, tmp_path):
    core, passing = captures
    source, _, report, _ = release_case
    packed = tmp_path/'captures.zip'
    record = pack_captures(core, passing, packed)
    report['source_revisions'] = record['revisions']
    target = tmp_path/'release'
    native.create_release(source, target, core_inputs=core, passing_inputs=passing, watermarks={'source:2024':'acknowledged'})
    return target, packed, report, Store()


def publish(case, destination=DESTINATION):
    release, packed, _, store = case
    return releases.publish(release, packed, destination, store, log=lambda _: None)


def test_complete_release_pins_all_payloads_and_writes_marker_last(case):
    release, packed, report, store = case
    before = {path: native.digest(path) for path in [*release.iterdir(), packed]}
    receipt = publish(case)
    assert receipt['publication']['source_revisions'] == report['source_revisions']
    assert receipt['publication']['publisher_code_sha256'] == releases.publisher_revision()
    created = [event[1].rsplit('/',1)[1] for event in store.events if event[0] == 'create']
    assert created == ['reservation.json', *releases.PAYLOADS, 'publication.json']
    assert receipt['publication']['files'].keys() == set(releases.PAYLOADS)
    for name, record in receipt['publication']['files'].items():
        data = store.objects[DESTINATION+'/'+name, record['generation']]
        assert hashlib.sha256(data).hexdigest() == record['sha256']
    assert before == {path: native.digest(path) for path in before}
    assert not any('current.json' in uri for uri in store.latest)


@pytest.mark.parametrize('name', ['reservation.json', *releases.PAYLOADS, 'publication.json'])
def test_failed_upload_leaves_no_completion_or_current_pointer(case, name):
    store = case[3]
    store.fail_name = name
    with pytest.raises(OSError, match='interrupted'):
        publish(case)
    assert DESTINATION+'/publication.json' not in store.latest
    assert not any('current.json' in uri for uri in store.latest)


@pytest.mark.parametrize('name', ['reservation.json', *releases.PAYLOADS])
def test_bad_remote_checksum_cannot_complete_a_release(case, name):
    store = case[3]
    store.bad_metadata = name
    with pytest.raises(ValueError, match='checksum'):
        publish(case)
    assert DESTINATION+'/publication.json' not in store.latest


def test_completed_release_cannot_be_reused_and_original_objects_stay_intact(case):
    receipt = publish(case)
    store = case[3]
    before = dict(store.objects)
    with pytest.raises(FileExistsError):
        publish(case)
    assert store.objects == before
    assert releases.verify(DESTINATION, store) == receipt


def test_concurrent_publisher_is_stopped_by_reservation(case):
    store = case[3]
    attempts = []
    def compete(uri):
        if uri.endswith('/reservation.json'):
            with pytest.raises(FileExistsError):
                publish(case)
            attempts.append('refused')
    store.after_create = compete
    publish(case)
    assert attempts == ['refused']


def test_publisher_code_drift_cannot_issue_a_completion_marker(case, monkeypatch):
    store = case[3]
    def change(uri):
        if uri.endswith('/captures.zip'):
            monkeypatch.setattr(releases, 'publisher_revision', lambda: '0'*64)
    store.after_create = change
    with pytest.raises(ValueError, match='Publisher code changed'):
        publish(case)
    assert DESTINATION+'/publication.json' not in store.latest


@pytest.mark.parametrize('name', ['captures.zip', 'validation.json', 'nfl.duckdb'])
def test_local_mutation_during_upload_prevents_completion(case, name):
    release, packed, _, store = case
    def change(uri):
        if uri.endswith('/release.json'):
            path = packed if name == 'captures.zip' else release/name
            with path.open('ab') as stream:
                stream.write(b'changed')
    store.after_create = change
    # Windows rejects a raw database write while our read-only lock is held;
    # platforms permitting it must reject the subsequent checksum mismatch.
    with pytest.raises((ValueError, native.ReleaseError, PermissionError)):
        publish(case)
    assert DESTINATION+'/publication.json' not in store.latest


@pytest.mark.parametrize('change', ['revision', 'season', 'payload', 'declared_hash', 'root', 'unreferenced', 'unsafe', 'missing', 'cycle'])
def test_mismatched_or_corrupt_capture_archive_causes_no_cloud_writes(case, tmp_path, change):
    release, packed, _, store = case
    broken = tmp_path/'broken.zip'
    def alter(members):
        record = json.loads(members[MAP_NAME])
        if change == 'revision':
            record['revisions']['core'] = 'another capture'
        elif change == 'root':
            record['roots']['core'] = record['roots']['passing']
        elif change == 'unreferenced':
            record['directories']['unused'] = 'objects/9999'
        elif change in ('payload', 'missing', 'unsafe'):
            name = next(name for name in members if name.endswith('/plays-2024.csv'))
            if change == 'payload':
                members[name] += b'changed'
            elif change == 'missing':
                del members[name]
            else:
                members['../outside'] = members.pop(name)
                record['files']['../outside'] = record['files'].pop(name)
        else:
            name = record['roots']['core']+'/run.json'
            manifest = json.loads(members[name])
            if change == 'season':
                manifest['seasons'] = [2025]
            elif change == 'cycle':
                reference = next(ref for ref, target in record['directories'].items() if target == record['roots']['core'])
                manifest['bundles'] = [dict(directory=reference,manifest_sha256='0'*64)]
            else:
                name = next(name for name in members if name.endswith('/plays-2024.csv'))
                record['files'][name]['sha256'] = '0'*64
                manifest = None
            if manifest is not None:
                members[name] = json.dumps(manifest).encode()
                record['files'][name]['sha256'] = hashlib.sha256(members[name]).hexdigest()
        members[MAP_NAME] = json.dumps(record).encode()
    rewrite_archive(packed, broken, alter)
    with pytest.raises((ValueError, KeyError)):
        releases.publish(release, broken, DESTINATION, store, log=lambda _: None)
    assert not store.objects


def test_valid_archive_identity_is_recomputed_instead_of_trusting_its_header(case):
    _, packed, report, _ = case
    with pytest.raises(ValueError, match='does not match'):
        archive.verify_archive(packed, dict(core='other',passing='other'), report['played_seasons'])


def test_archive_replacement_after_content_check_cannot_become_upload_baseline(case, monkeypatch):
    original = releases.verify_archive
    def replace(path, *args):
        result = original(path, *args)
        Path(path).write_bytes(b'different bytes after the content check')
        return result
    monkeypatch.setattr(releases, 'verify_archive', replace)
    with pytest.raises(ValueError, match='changed during publication preflight'):
        publish(case)
    assert not case[3].objects


@pytest.mark.parametrize('destination', ['gs://bucket', 'gs://bucket/a/', 'gs://bucket/../id',
                                      'gs://bucket/a/*', 'gs://bucket/a?x', 'gs://bucket/a&command', 'https://bucket/id'])
def test_invalid_destinations_fail_before_cloud_writes(case, destination):
    with pytest.raises(ValueError, match='explicit'):
        publish(case, destination)
    assert not case[3].objects


def test_marker_identity_and_object_generations_are_verified(case):
    receipt = publish(case)
    store = case[3]
    store.events.clear()
    releases.verify(DESTINATION, store, marker_generation=receipt['manifest_generation'],
                    marker_sha256=receipt['manifest_sha256'])
    assert all(event[2] for event in store.events if event[0] in ('read','stat'))
    with pytest.raises(ValueError, match='marker changed'):
        releases.verify(DESTINATION, store, marker_sha256='0'*64)


def test_remote_payload_corruption_is_detected(case):
    receipt = publish(case)
    store = case[3]
    version = receipt['publication']['files']['captures.zip']['generation']
    store.objects[DESTINATION+'/captures.zip', version] = b'corrupted'
    with pytest.raises(ValueError, match='checksum'):
        releases.verify(DESTINATION, store)


def test_payload_reads_stay_on_recorded_versions_when_latest_objects_change(case):
    receipt = publish(case)
    store = case[3]
    for name in releases.PAYLOADS:
        uri = DESTINATION+'/'+name
        store.objects[uri,'9999'] = b'a different latest version'
        store.latest[uri] = '9999'
    assert releases.verify(DESTINATION, store) == receipt


@pytest.mark.parametrize('name,field,value', [
    ('validation.json','publication_ready',False),
    ('validation.json','source_revisions',{'core':'other','passing':'other'}),
    ('watermarks.json','source:2024',None),
    ('release.json','validation_code_sha256','other'),
])
def test_remote_metadata_must_still_satisfy_native_bundle_contract(case, name, field, value):
    receipt = publish(case)
    store = case[3]
    publication = receipt['publication']
    uri = DESTINATION+'/'+name
    record = publication['files'][name]
    content = json.loads(store.objects[uri,record['generation']])
    content[field] = value
    raw = json.dumps(content).encode()
    store.objects[uri,record['generation']] = raw
    record.update(releases._bytes_record(raw))
    marker_uri = DESTINATION+'/publication.json'
    store.objects[marker_uri,receipt['manifest_generation']] = json.dumps(publication).encode()
    with pytest.raises((ValueError,native.ReleaseError)):
        releases.verify(DESTINATION, store)


def test_gcloud_uses_generation_precondition_server_md5_and_raw_metadata(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(gcs, 'command', lambda: ['sdk-python', 'gcloud.py'])
    def run(args, **kwargs):
        calls.append((args,kwargs))
        result = dict(generation='123',size='4',md5Hash=md5(b'data'))
        return subprocess.CompletedProcess(args,0,json.dumps(result).encode())
    monkeypatch.setattr(gcs.subprocess,'run',run)
    store = gcs.GCloudStore()
    store.create(DESTINATION+'/nfl.duckdb', tmp_path/'file with spaces', md5(b'data'))
    argv, options = calls[0]
    assert '--if-generation-match=0' in argv and '--content-md5='+md5(b'data') in argv
    assert options['env']['CLOUDSDK_STORAGE_PARALLEL_COMPOSITE_UPLOAD_ENABLED'] == 'false'
    assert options['check'] is True and not options.get('shell')
    assert '--raw' in calls[1][0] and '--format=json' in calls[1][0]
    store.read(DESTINATION+'/publication.json','123')
    assert calls[-1][0][-1].endswith('/publication.json#123')


@pytest.mark.parametrize('version', ['0', '-1', '', '123#4', '1&command', 123])
def test_invalid_object_generation_is_rejected(version):
    with pytest.raises(ValueError, match='generation'):
        gcs.generation(version)
