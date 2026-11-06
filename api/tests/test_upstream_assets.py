import httpx
import pytest

from pipeline import upstream_assets as assets
from tests.test_upstream_proof import published


@pytest.mark.parametrize('key',list(assets.CORE_ASSETS))
def test_download_requires_matching_digest_and_size_and_sends_no_token(tmp_path,monkeypatch,key):
    content = b'published RDS bytes'
    item = published(key,content=content)
    requests = []
    def transport(request):
        requests.append(request)
        return httpx.Response(200,content=content)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        monkeypatch.setattr(assets.httpx,'stream',client.stream)
        monkeypatch.setenv('GITHUB_TOKEN','metadata-only-token')
        output = tmp_path/'asset.rds'
        assets.download_asset(item,output)
        assert output.read_bytes() == content and 'authorization' not in requests[0].headers
        with pytest.raises(FileExistsError):assets.download_asset(item,output)
        broken = {**item,'digest':'sha256:'+'0'*64}
        with pytest.raises(ValueError,match='SHA256'):assets.download_asset(broken,tmp_path/'bad.rds')
        assert not (tmp_path/'bad.rds').exists()


@pytest.mark.parametrize('field,value',[('digest',None),('id',True),('size',0),('name','other.rds'),
                                       ('repository','other'),('url','https://untrusted.example/file')])
def test_incomplete_or_wrong_asset_identity_is_rejected(field,value):
    item = {**published('pbp_rds'),field:value}
    with pytest.raises(ValueError):assets.validate_asset('pbp_rds',2026,item)


def test_version_changes_when_content_changes_even_at_same_timestamp():
    original = published('playstats')
    assert assets.asset_version(original) != assets.asset_version({**original,'digest':'sha256:'+'0'*64})


def test_metadata_observer_uses_each_exact_repository_and_rejects_missing_credits(monkeypatch):
    calls = []
    missing = False
    def transport(request):
        calls.append(request)
        key = next(key for key,(repository,tag,_,_) in assets.CORE_ASSETS.items()
                   if request.url.path == f'/repos/nflverse/{repository}/releases/tags/{tag}')
        item = published(key)
        payload = {**item,'browser_download_url':item['url']}
        return httpx.Response(200,json={'assets':[] if missing and key=='playstats' else [payload]})
    original_client = httpx.Client
    monkeypatch.setattr(assets.httpx,'Client',lambda **options:original_client(
        **options,transport=httpx.MockTransport(transport)))
    monkeypatch.setenv('GITHUB_TOKEN','metadata-only-token')
    assert set(assets.observe_core_assets(2026)) == set(assets.CORE_ASSETS)
    assert all(request.headers['authorization'] == 'Bearer metadata-only-token' for request in calls)
    missing = True
    with pytest.raises(ValueError,match='playstats'):
        assets.observe_core_assets(2026)
