import { test as base, expect, type Page } from '@playwright/test'
import type { Game, Scoreboard, SeasonStatus } from '../../src/types'

// Every scenario guards against reintroducing public ingestion, including its stream.
export const test = base.extend<{ readOnlyGuard: void }>({
  readOnlyGuard: [async ({ page }, use) => {
    const forbidden: string[] = []
    page.on('request', request => {
      const path = new URL(request.url()).pathname
      if (path.startsWith('/api/') && (request.method() !== 'GET' || path.endsWith('/progress'))) {
        forbidden.push(`${request.method()} ${path}`)
      }
    })
    await use()
    expect(forbidden).toEqual([])
  }, { auto: true }],
})

export const seasonList: SeasonStatus[] = [
  { season: 2026, status: 'scheduled' },
  { season: 2025, status: 'available' },
  { season: 2023, status: 'loaded' },
]
export const game: Game = {
  game_id: '2026_01_BUF_MIA', season: 2026, week: 1, game_type: 'REG',
  gameday: '2026-09-13', gametime: '13:00', away_team: 'BUF', home_team: 'MIA',
  away_score: null, home_score: null, away_qb_name: null, home_qb_name: null,
  spread_line: null, total_line: null, roof: null, surface: null, temp: null,
  wind: null, stadium: null, overtime: null, div_game: 1,
}
export const board: Scoreboard = {
  games: [], source: 'schedule', poll_after: null, fetched_at: '2026-10-13T12:00:00Z',
}

export async function mockApi(page: Page, seasons = seasonList, scoreboard = board) {
  const reads: string[] = []
  await page.route(url => url.pathname.startsWith('/api/'), route => {
    const url = new URL(route.request().url())
    reads.push(url.pathname)
    if (url.pathname === '/api/seasons') return route.fulfill({ json: seasons })
    if (url.pathname === '/api/live/scoreboard') return route.fulfill({ json: scoreboard })
    if (url.pathname === '/api/schedule') {
      const season = Number(url.searchParams.get('season'))
      return route.fulfill({ json: [{ week: 1, games: [
        { ...game, season, game_id: `${season}_01_BUF_MIA` },
        { ...game, season, game_id: 'second-game', away_team: 'SF', home_team: 'KC', gametime: '16:25' },
      ] }] })
    }
    if (['/api/standings', '/api/leaders', '/api/power-rankings'].includes(url.pathname)) {
      return route.fulfill({ json: [] })
    }
    return route.fulfill({ status: 404, json: { detail: 'Unexpected test request' } })
  })
  await page.route('https://a.espncdn.com/**', route => route.abort())
  return reads
}
