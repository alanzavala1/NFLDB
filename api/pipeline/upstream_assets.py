"""Exact published RDS assets consumed by the pinned native calculator."""
import hashlib
import json
import os
from pathlib import Path

import httpx


CORE_ASSETS = {
    'pbp_rds': ('nflverse-data', 'pbp', 'play_by_play_{season}.rds', 'pbp'),
    'weekly_rds': ('nflverse-data', 'stats_player', 'stats_player_week_{season}.rds', 'weekly'),
    'playstats': ('nflverse-pbp', 'playstats', 'play_stats_{season}.rds', 'credits'),
}


def asset_version(asset):
    """Asset identity includes content, not only a release-level timestamp."""
    value = {key: asset[key] for key in ('repository', 'tag', 'name', 'id', 'updated_at', 'size', 'digest')}
    return 'github-asset-sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate_asset(key, season, asset):
    repository, tag, template, _ = CORE_ASSETS[key]
    name = template.format(season=season)
    url = f'https://github.com/nflverse/{repository}/releases/download/{tag}/{name}'
    digest = asset.get('digest', '')
    if (asset.get('repository') != repository or asset.get('tag') != tag or asset.get('name') != name
            or asset.get('url') != url or type(asset.get('id')) is not int or asset['id'] <= 0
            or type(asset.get('size')) is not int or asset['size'] <= 0
            or not isinstance(asset.get('updated_at'), str) or not asset['updated_at']
            or not isinstance(digest, str) or not digest.startswith('sha256:')
            or len(digest) != 71 or any(c not in '0123456789abcdef' for c in digest[7:])):
        raise ValueError(f'{key}[{season}]: incomplete GitHub asset identity/SHA256')
    return asset


def observe_core_assets(season):
    headers = {'Accept': 'application/vnd.github+json'}
    if token := os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = f'Bearer {token}'
    result = {}
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for key, (repository, tag, template, _) in CORE_ASSETS.items():
            response = client.get(f'https://api.github.com/repos/nflverse/{repository}/releases/tags/{tag}', headers=headers)
            response.raise_for_status()
            matches = [item for item in response.json()['assets'] if item['name'] == template.format(season=season)]
            if len(matches) != 1:
                raise ValueError(f'{key}[{season}]: expected one published RDS asset')
            item = matches[0]
            result[key] = validate_asset(key, season, dict(repository=repository, tag=tag, name=item['name'],
                id=item['id'], size=item['size'], updated_at=item['updated_at'], digest=item.get('digest'),
                url=item['browser_download_url']))
    return result


def download_asset(asset, output):
    """Public asset requests carry no API token, including across redirects."""
    output = Path(output)
    with output.open('xb') as target:
        try:
            digest, size = hashlib.sha256(), 0
            with httpx.stream('GET', asset['url'], timeout=180, follow_redirects=True) as response:
                response.raise_for_status()
                for block in response.iter_bytes():
                    target.write(block)
                    digest.update(block)
                    size += len(block)
            if size != asset['size'] or 'sha256:'+digest.hexdigest() != asset['digest']:
                raise ValueError('Downloaded asset differs from published size/SHA256')
        except BaseException:
            target.close()
            output.unlink()
            raise
