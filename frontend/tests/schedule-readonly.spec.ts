import { test as base, expect, type Page } from '@playwright/test'
import type { Game, Scoreboard, SeasonStatus } from '../src/types'

// Every scenario guards against reintroducing public ingestion, including its stream.
const test = base.extend<{ readOnlyGuard: void }>({
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

const seasonList: SeasonStatus[] = [
  { season: 2026, status: 'scheduled' },
  { season: 2025, status: 'available' },
  { season: 2023, status: 'loaded' },
]
const game: Game = {
  game_id: '2026_01_BUF_MIA', season: 2026, week: 1, game_type: 'REG',
  gameday: '2026-09-13', gametime: '13:00', away_team: 'BUF', home_team: 'MIA',
  away_score: null, home_score: null, away_qb_name: null, home_qb_name: null,
  spread_line: null, total_line: null, roof: null, surface: null, temp: null,
  wind: null, stadium: null, overtime: null, div_game: 1,
}
const board: Scoreboard = {
  games: [], source: 'schedule', poll_after: null, fetched_at: '2026-10-13T12:00:00Z',
}

async function mockApi(page: Page, seasons = seasonList, scoreboard = board) {
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

test('offers loaded and scheduled years and defaults to published fixtures', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const selector = page.getByRole('combobox', { name: 'Season' })
  await expect(selector).toHaveValue('2026')
  await expect(selector.getByRole('option')).toHaveText(['2026', '2023'])
  await expect(page.locator('a[href="/games/2026_01_BUF_MIA"]').first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Load season' })).toHaveCount(0)
  await selector.selectOption('2023')
  await expect(page).toHaveURL(/season=2023/)
  await expect(page.locator('a[href="/games/2023_01_BUF_MIA"]').first()).toBeVisible()
})

for (const status of ['available', 'queued', 'loading', 'error'] as const) {
  test(`an explicit ${status} season shows a message without starting work`, async ({ page }) => {
    const reads = await mockApi(page, [{ season: 2025, status }, { season: 2023, status: 'loaded' }])
    await page.goto('/?season=2025')
    await expect(page.getByText('Scores for this season are not available yet.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Load season' })).toHaveCount(0)
    await expect(page.getByRole('combobox').getByRole('option')).toHaveText(['Choose a season', '2023'])
    expect(reads.filter(path => !['/api/seasons', '/api/live/scoreboard'].includes(path))).toEqual([])
    await page.getByRole('combobox').selectOption('2023')
    await expect(page.locator('a[href="/games/2023_01_BUF_MIA"]').first()).toBeVisible()
  })
}

test('unknown bookmarked years do not start data requests', async ({ page }) => {
  const reads = await mockApi(page)
  await page.goto('/?season=1900')
  await expect(page.getByText('Scores for this season are not available yet.')).toBeVisible()
  expect(reads.filter(path => !['/api/seasons', '/api/live/scoreboard'].includes(path))).toEqual([])
})

test('no readable seasons ends loading and disables the picker', async ({ page }) => {
  await mockApi(page, [{ season: 2025, status: 'available' }])
  await page.goto('/')
  await expect(page.getByText('No seasons are available yet.')).toBeVisible()
  await expect(page.getByRole('combobox')).toBeDisabled()
  await expect(page.getByText('Loading seasons...')).toHaveCount(0)
})

test('season-list failure ends loading with a readable error', async ({ page }) => {
  await mockApi(page)
  await page.route('**/api/seasons', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }))
  await page.goto('/')
  await expect(page.getByText('Could not load the season list. Please reload the page to try again.')).toBeVisible()
  await expect(page.getByText('Loading seasons...')).toHaveCount(0)
})

test('mobile scores and live overlay still display through the existing provider', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockApi(page, seasonList, {
    ...board, source: 'live', games: [{
      game_id: 'second-game', away_team: 'SF', home_team: 'KC', gameday: '2026-09-13',
      state: 'in', away_score: 14, home_score: 17, period: 3, clock: '5:42',
      possession: 'KC', detail: '3rd Quarter', away_periods: [], home_periods: [],
      down_distance: null, red_zone: false, last_play: null, away_timeouts: null,
      home_timeouts: null, leaders: [],
    }],
  })
  await page.goto('/?season=2026&week=1')
  const liveGame = page.locator('a[href="/games/second-game"]').first()
  await expect(liveGame.getByText('LIVE', { exact: true })).toBeVisible()
  await expect(liveGame.getByText('Q3 · 5:42', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
