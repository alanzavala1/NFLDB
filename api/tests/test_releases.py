"""Real files: incomplete releases, stale publishers and failures preserve current."""
import json

import duckdb
import pytest

from pipeline import releases, release_pointer


@pytest.fixture
def release_case(tmp_path, monkeypatch):
    source = tmp_path / 'candidate.duckdb'
    with duckdb.connect(str(source)) as conn:
        conn.execute('CREATE TABLE sentinel AS SELECT 42 AS value')
    report = dict(publication_ready=True, official_receiving=True, official_passing=True,
                  played_seasons=[2024], api_requests=['/api/seasons'], source_revisions={'core':'capture', 'passing':'export'})
    calls = []
    def validate(*args):
        calls.append(args)
        return report
    monkeypatch.setattr(releases, '_validate', validate)
    return source, tmp_path, report, calls


def build(case, name='release', marks=None):
    source, root, _, _ = case
    target = root / name
    releases.create_release(source, target, core_inputs=root/'core', passing_inputs=root/'passing', watermarks=marks)
    return target


def test_real_bundle_copies_exact_validated_bytes_and_selects_db_and_marks_together(release_case):
    source, root, _, calls = release_case
    before = releases.digest(source)
    target = build(release_case, marks={'pbp:2024':'previously-acknowledged'})
    assert len(calls) == 1 and releases.digest(target/'nfl.duckdb') == before == releases.digest(source)
    assert not (root/'current.json').exists()  # Packaging alone never publishes.
    release_pointer.select_release(target, root/'current.json')
    selected = release_pointer.current_release(root/'current.json')
    assert selected == target and json.loads((selected/'watermarks.json').read_bytes()) == {'pbp:2024':'previously-acknowledged'}


@pytest.mark.parametrize('field', ['publication_ready', 'official_receiving', 'official_passing', 'api_requests', 'played_seasons'])
def test_incomplete_or_legacy_validation_cannot_produce_completion_marker(release_case, field):
    source, root, report, _ = release_case
    report[field] = False
    before = releases.digest(source)
    with pytest.raises(releases.ReleaseError): build(release_case)
    assert not (root/'release').exists() and releases.digest(source) == before


def test_existing_output_and_pending_wal_are_refused_without_touching_files(release_case):
    source, root, _, calls = release_case
    (root/'release').mkdir()
    (root/'release'/'sentinel').write_text('keep')
    with pytest.raises(FileExistsError): build(release_case)
    assert not calls and (root/'release'/'sentinel').read_text() == 'keep'
    (root/'candidate.duckdb.wal').write_text('pending')
    with pytest.raises(releases.ReleaseError, match='WAL'): build(release_case, 'new')
    assert not calls and not (root/'new').exists()


def test_copy_failure_cleans_only_owned_output_and_preserves_source(release_case, monkeypatch):
    source, root, _, _ = release_case
    before = releases.digest(source)
    def fail(*args): raise OSError('disk full')
    monkeypatch.setattr(releases.shutil, 'copyfileobj', fail)
    with pytest.raises(OSError, match='disk full'): build(release_case)
    assert not (root/'release').exists() and releases.digest(source) == before


@pytest.mark.parametrize('name', ['nfl.duckdb', 'validation.json', 'watermarks.json', 'release.json'])
def test_corrupt_or_missing_bundle_does_not_change_current_selection(release_case, name):
    _, root, _, _ = release_case
    first = build(release_case)
    pointer = root/'current.json'
    release_pointer.select_release(first, pointer)
    before = pointer.read_bytes()
    second = build(release_case, 'second')
    (second/name).write_text('corrupted')
    with pytest.raises(releases.ReleaseError):
        release_pointer.select_release(second, pointer, expected=releases.digest(pointer))
    assert pointer.read_bytes() == before
    assert release_pointer.current_release(pointer) == first


def test_stale_and_concurrent_publishers_cannot_replace_current_selection(release_case):
    _, root, _, _ = release_case
    first, second = build(release_case), build(release_case, 'second')
    pointer = root/'current.json'
    release_pointer.select_release(first, pointer)
    old = releases.digest(pointer)
    release_pointer.select_release(second, pointer, expected=old)
    with pytest.raises(releases.ReleaseError, match='Current release changed'):
        release_pointer.select_release(first, pointer, expected=old)
    assert release_pointer.current_release(pointer) == second
    pointer.with_name('current.json.lock').write_text('another writer')
    with pytest.raises(FileExistsError): release_pointer.select_release(first, pointer, expected=releases.digest(pointer))
    assert pointer.with_name('current.json.lock').read_text() == 'another writer'


def test_failed_atomic_replace_keeps_previous_selection_and_cleans_temp(release_case, monkeypatch):
    _, root, _, _ = release_case
    first, second = build(release_case), build(release_case, 'second')
    pointer = root/'current.json'
    release_pointer.select_release(first, pointer)
    before = pointer.read_bytes()
    def fail(*args): raise OSError('replace failed')
    monkeypatch.setattr(release_pointer.os, 'replace', fail)
    with pytest.raises(OSError): release_pointer.select_release(second, pointer, expected=releases.digest(pointer))
    assert pointer.read_bytes() == before
    assert not list(root.glob('*.tmp')) and not list(root.glob('*.lock'))


def test_pointer_cannot_mutate_an_immutable_release(release_case):
    target = build(release_case)
    before = releases.digest(target/'release.json')
    with pytest.raises(releases.ReleaseError): release_pointer.select_release(target, target/'release.json')
    assert releases.digest(target/'release.json') == before


def test_changed_validation_code_invalidates_a_previously_built_release(release_case, monkeypatch):
    target = build(release_case)
    monkeypatch.setattr(releases, 'validation_revision', lambda: 'different-code')
    with pytest.raises(releases.ReleaseError, match='manifest'):
        releases.verify_release(target)


def test_reviewed_orchestration_compatibility_is_limited_to_exact_code_revision():
    from automation.validation_policy import EQUIVALENT_REVISIONS, compatible_revision

    assert releases.validation_revision() == 'f72611443cf21bba4fc9ecec485459304b10e6094c4997339747b4ac16ef7ef4'
    for revision, policy in EQUIVALENT_REVISIONS.items():
        assert compatible_revision(revision) == policy
        changed = ('1' if revision[0] == '0' else '0') + revision[1:]
        assert compatible_revision(changed) == changed


def test_policy_changed_during_validation_cannot_create_a_release(release_case, monkeypatch):
    source, root, report, _ = release_case
    policy = root/'policy.txt'
    policy.write_text('before')
    monkeypatch.setattr(releases, 'validation_revision', lambda: releases.digest(policy))
    def validate(*args):
        policy.write_text('after')
        return report
    monkeypatch.setattr(releases, '_validate', validate)
    before = releases.digest(source)
    with pytest.raises(releases.ReleaseError, match='policy changed'):
        build(release_case)
    assert not (root/'release').exists() and releases.digest(source) == before
