"""Deployment gates fail closed for corrupt data, wrong DBs and stale jobs."""
import asyncio
import json

import pytest

from jobs import deploy
from pipeline import releases
from publication import downloads
from tests.test_releases import release_case, build
from tests.test_publication_selection import (
    prepared, case, captures, bundle, choose, SelectedStore,
)


@pytest.mark.parametrize('name', [*releases.FILES, 'release.json'])
def test_image_identity_requires_every_certified_file(release_case, name):
    release = build(release_case)
    (release/name).write_bytes(b'corrupt')
    with pytest.raises(releases.ReleaseError):
        deploy.identity(release)


@pytest.mark.parametrize('writable,wrong_path', [(True, False), (False, True)])
def test_image_check_rejects_runtime_configuration_before_opening_database(
        release_case, monkeypatch, writable, wrong_path):
    release = build(release_case)
    monkeypatch.setenv('NFL_DB_PATH', str(release/('wrong.duckdb' if wrong_path else 'nfl.duckdb')))
    monkeypatch.setenv('NFL_DB_READ_ONLY', '0' if writable else '1')
    before = releases.digest(release/'nfl.duckdb')
    with pytest.raises(ValueError, match='read-only mode'):
        asyncio.run(deploy.check_image(release))
    assert releases.digest(release/'nfl.duckdb') == before
    assert not (release/'wrong.duckdb').exists()


def test_deploy_rechecks_latest_selection_instead_of_historical_pin(prepared, tmp_path):
    selected = choose(prepared)
    output = tmp_path/'download'
    downloads.download_selected(selected['pointer'], output, prepared[0][3], log=lambda _: None)
    assert deploy.assert_current(output, prepared[0][3]) == selected
    # Even selecting the SAME publication again supersedes the old job.
    choose(prepared, selected['pointer_generation'])
    with pytest.raises(ValueError, match='superseded'):
        deploy.assert_current(output, prepared[0][3])
    assert json.loads((output/'download.json').read_bytes())['selection'] == selected


def test_deploy_requires_completed_download_before_cloud_access(tmp_path):
    store = SelectedStore()
    with pytest.raises(FileNotFoundError):
        deploy.assert_current(tmp_path, store)
    (tmp_path/'download.json').write_text('{}')
    with pytest.raises(ValueError, match='completed'):
        deploy.assert_current(tmp_path, store)
    assert store.events == []
