"""Representative HTTP requests against prepared data, without app startup writes."""
from urllib.parse import quote

import httpx

from pipeline.validation import SnapshotValidationError


async def check_api(conn, seasons):
    # ASGITransport exercises routing, services and response schemas in-process.
    # It does not run lifespan (which still writes), open a port, or use a model.
    from main import app
    paths = ['/api/seasons']
    for season in sorted({min(seasons), max(seasons)}):
        paths.extend(f'/api/{resource}?season={season}' for resource in (
            'schedule', 'standings', 'leaders', 'power-rankings', 'team-analytics'))
        sample = conn.execute('''SELECT game_id, home_team FROM schedules
            WHERE season = ? AND game_type = 'REG' AND home_score IS NOT NULL
            AND away_score IS NOT NULL AND game_id IN (SELECT DISTINCT game_id FROM plays)
            ORDER BY week, game_id LIMIT 1''', [season]).fetchone()
        if not sample:
            raise SnapshotValidationError(f'schedules[{season}]: no completed game with play data')
        game, team = sample
        paths.extend((f'/api/games/{quote(game, safe="")}/ratings',
                      f'/api/teams/{quote(team, safe="")}/splits?season={season}'))
        player = conn.execute('''SELECT player_id FROM player_splits WHERE season = ?
            ORDER BY player_id LIMIT 1''', [season]).fetchone()
        if player:
            paths.append(f'/api/players/{quote(player[0], safe="")}/splits')

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://candidate') as client:
        for path in paths:
            response = await client.get(path)
            if response.status_code != 200:
                raise SnapshotValidationError(f'{path}: HTTP {response.status_code}')
            payload = response.json()
            if not payload or (path.startswith('/api/team-analytics?') and not payload['league']):
                raise SnapshotValidationError(f'{path}: unexpectedly empty response')
    if 'receiving_build_preparation' in {row[0] for row in conn.execute('SHOW TABLES').fetchall()}:
        from pipeline.receiving_api_checks import check_receiving_api
        paths.extend(await check_receiving_api(conn, seasons))
    if 'passing_build_preparation' in {row[0] for row in conn.execute('SHOW TABLES').fetchall()}:
        from pipeline.passing_api_checks import check_passing_api
        paths.extend(await check_passing_api(conn, seasons))
    return paths
