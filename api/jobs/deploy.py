"""Check native serving images and refuse deployments of superseded selections."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from pipeline import releases


def identity(release):
    release = Path(release).resolve()
    manifest = releases.verify_release(release)
    return dict(release_sha256=releases.digest(release/'release.json'),
                database_sha256=manifest['files']['nfl.duckdb']['sha256'],
                validation_code_sha256=manifest['validation_code_sha256'])


def assert_current(download, store):
    from publication.selection import read_selection

    receipt = json.loads((Path(download)/'download.json').read_bytes())
    if receipt.get('format_version') != 1 or receipt.get('kind') != 'native_release_download':
        raise ValueError('A completed, verified download is required')
    expected = receipt['selection']
    # Read the latest pointer, NOT the pinned historical version we downloaded.
    actual = read_selection(expected['pointer'], store)
    if actual != expected:
        raise ValueError('Selection changed; this deployment is superseded')
    return actual


async def check_image(release):
    """Run in a fresh process, using the image's actual serving configuration."""
    release = Path(release).resolve()
    before = identity(release)  # Missing/invalid bundles fail, never skip.
    if (os.environ.get('NFL_DB_READ_ONLY') == '0'
            or Path(os.environ.get('NFL_DB_PATH', '')).resolve() != release/'nfl.duckdb'):
        raise ValueError('Serving must use this release in read-only mode')

    import database
    import duckdb
    from main import app
    from pipeline.api_checks import check_api

    if Path(database.DB_PATH).resolve() != release/'nfl.duckdb':
        raise ValueError('API connection points at a different database')
    report = json.loads((release/'validation.json').read_bytes())
    try:
        conn = database.get_connection()
        try:
            conn.execute('CREATE TABLE deployment_write_must_fail (value INTEGER)')
        except duckdb.Error as error:
            if 'read-only' not in str(error).lower():
                raise
        else:
            raise RuntimeError('Serving connection accepted a persistent write')
        # Also exercise real startup; ASGITransport alone omits lifespan.
        async with app.router.lifespan_context(app):
            paths = await check_api(conn, report['played_seasons'])
        if paths != report['api_requests']:
            raise ValueError('Image HTTP coverage differs from the validated release')
    finally:
        database.close_connection()
    if identity(release) != before:
        raise ValueError('Release changed during image verification')
    return dict(**before, api_checks=len(paths), write_rejected=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('identity', 'check-image'):
        command = commands.add_parser(name)
        command.add_argument('--release', type=Path, default=Path('/app/api/data/release'))
    current = commands.add_parser('assert-current')
    current.add_argument('--download', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'assert-current':
        from publication.gcs import GCloudStore
        result = assert_current(args.download, GCloudStore())
    elif args.command == 'identity':
        result = identity(args.release)
    else:
        result = asyncio.run(check_image(args.release))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
