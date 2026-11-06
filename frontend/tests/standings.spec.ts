import { test, expect, type Page, type Route } from '@playwright/test'
import type { DivisionStandings, Game, SeasonStatus, StandingsRow } from '../src/types'

const seasons: SeasonStatus[] = [
  { season: 2022, status: 'loaded' },
  { season: 2027, status: 'scheduled' },
  { season: 2023, status: 'loaded' },
]
const row: StandingsRow = {
  team: 'BUF', w: 11, l: 6, t: 0, pct: 11 / 17, pf: 451, pa: 311,
  home: '7-2', away: '4-4', div: '4-2', strk: 'W5', gb: '—',
}
const standings = (team = 'BUF'): DivisionStandings[] => [{ division: 'AFC East', teams: [{ ...row, team }] }]

async function mockApi(page: Page, seasonList = seasons) {
  await page.route('**/api/seasons', route => route.fulfill({ json: seasonList }))
  await page.route('**/api/schedule?*', route => route.fulfill({ json: [] }))
  await page.route('**/api/standings?*', route => route.fulfill({ json: standings() }))
  await page.route('https://a.espncdn.com/**', route => route.abort())
}

test('defaults to latest loaded season and preserves standings presentation', async ({ page }) => {
  await mockApi(page)
  await page.goto('/standings')
  await expect(page.getByRole('combobox', { name: 'Season' })).toHaveValue('2023')
  await expect(page.getByRole('option')).toHaveText(['2023', '2022'])
  const table = page.getByRole('table')
  await expect(table.getByRole('link', { name: 'BUF' })).toHaveAttribute('href', '/teams/BUF')
  await expect(table.getByRole('cell', { name: '.647', exact: true })).toBeVisible()
  await expect(table.getByRole('cell', { name: '+140', exact: true })).toBeVisible()
  await expect(table.getByRole('columnheader', { name: 'T', exact: true })).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('standings-desktop.png'), fullPage: true })
})

test('explicit old season links work and switching preserves other URL parameters', async ({ page }) => {
  await mockApi(page)
  await page.goto('/standings?season=2022&source=bookmark')
  await expect(page.getByRole('combobox', { name: 'Season' })).toHaveValue('2022')
  await expect(page.getByRole('table')).toBeVisible()
  await page.getByRole('combobox').selectOption('2023')
  await expect(page).toHaveURL(/season=2023&source=bookmark/)
  await expect(page.getByText('2023 NFL Season')).toBeVisible()
})

for (const requested of ['banana', '2027', '2023.5', '']) {
  test(`unavailable season '${requested}' does not request another year's data`, async ({ page }) => {
    let requests = 0
    await mockApi(page)
    page.on('request', request => { if (request.url().includes('/api/standings')) requests++ })
    await page.goto(`/standings?season=${requested}`)
    await expect(page.getByRole('alert')).toContainText('That season is unavailable')
    await expect(page.getByRole('table')).toHaveCount(0)
    expect(requests).toBe(0)
    await page.getByRole('combobox').selectOption('2023')
    await expect(page.getByRole('table')).toBeVisible()
  })
}

test('no loaded seasons produces an empty state without a standings request', async ({ page }) => {
  let requests = 0
  await mockApi(page, [{ season: 2027, status: 'scheduled' }])
  page.on('request', request => { if (request.url().includes('/api/standings')) requests++ })
  await page.goto('/standings')
  await expect(page.getByText('No loaded seasons are available yet.')).toBeVisible()
  await expect(page.getByRole('combobox')).toBeDisabled()
  expect(requests).toBe(0)
})

test('shows loading then empty standings honestly', async ({ page }) => {
  await mockApi(page)
  let release!: () => void
  const ready = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/standings?*', async route => {
    await ready
    await route.fulfill({ json: [] })
  })
  await page.goto('/standings')
  await expect(page.getByRole('status')).toHaveText('Loading standings…')
  release()
  await expect(page.getByText('No standings data for 2023.')).toBeVisible()
})

for (const resource of ['seasons', 'standings', 'schedule']) {
  test(`${resource} failure is visible and retry recovers`, async ({ page }) => {
    await mockApi(page)
    let fail = true
    const pattern = resource === 'seasons' ? '**/api/seasons' : `**/api/${resource}?*`
    await page.route(pattern, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Temporarily unavailable.' } }
      : { json: resource === 'seasons' ? seasons : resource === 'standings' ? standings() : [] }))
    await page.goto('/standings')
    await expect(page.getByRole('alert')).toContainText('Temporarily unavailable.')
    await expect(page.getByText('No standings data for 2023.')).toHaveCount(0)
    fail = false
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByRole('table')).toBeVisible()
  })
}

test('non-JSON server errors have a readable fallback', async ({ page }) => {
  await mockApi(page)
  await page.route('**/api/standings?*', route => route.fulfill({ status: 502, body: '<html>Bad gateway</html>' }))
  await page.goto('/standings')
  await expect(page.getByRole('alert')).toContainText('Request failed (502). Please try again.')
})

test('late responses cannot overwrite a newly selected season and revisits use the cache', async ({ page }) => {
  await mockApi(page)
  let oldRoute!: Route
  let markStarted!: () => void
  const started = new Promise<void>(resolve => { markStarted = resolve })
  const counts: Record<string, number> = {}
  await page.route('**/api/standings?*', async route => {
    const year = new URL(route.request().url()).searchParams.get('season')!
    counts[year] = (counts[year] ?? 0) + 1
    if (year === '2022') {
      oldRoute = route
      markStarted()
      return
    }
    await route.fulfill({ json: standings('BUF') })
  })
  await page.goto('/standings?season=2022')
  await started
  await page.getByRole('combobox').selectOption('2023')
  await expect(page.getByRole('table').getByRole('link', { name: 'BUF' })).toBeVisible()
  await oldRoute.fulfill({ json: standings('MIA') })
  await expect.poll(() => oldRoute.request().failure()?.errorText).toMatch(/ABORTED/)
  await expect(page.getByRole('table').getByRole('link', { name: 'MIA' })).toHaveCount(0)
  // Going back to an uncached, cancelled year issues a new request.
  await page.unroute('**/api/standings?*')
  await page.route('**/api/standings?*', route => {
    const year = new URL(route.request().url()).searchParams.get('season')!
    counts[year] = (counts[year] ?? 0) + 1
    return route.fulfill({ json: standings('MIA') })
  })
  await page.getByRole('combobox').selectOption('2022')
  await expect(page.getByRole('table').getByRole('link', { name: 'MIA' })).toBeVisible()
  await page.getByRole('combobox').selectOption('2023')
  await expect(page.getByRole('table').getByRole('link', { name: 'BUF' })).toBeVisible()
  expect(counts['2023']).toBe(1)
  expect(counts['2022']).toBe(2)
})

test('mobile tables retain tied records and horizontally scroll without widening the page', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockApi(page)
  await page.route('**/api/standings?*', route => route.fulfill({ json: [{ division: 'AFC East', teams: [{ ...row, t: 1 }] }] }))
  await page.goto('/standings')
  await expect(page.getByRole('columnheader', { name: 'T', exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'HOME', exact: true })).toBeHidden()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('standings-mobile.png'), fullPage: true })
})

test('playoff game links and champion remain intact after changing the data layer', async ({ page }) => {
  await mockApi(page)
  const game: Game = {
    game_id: '2023_22_SF_KC', season: 2023, game_type: 'SB', week: 22,
    gameday: '2024-02-11', gametime: '18:30', away_team: 'SF', home_team: 'KC',
    away_score: 22, home_score: 25, away_qb_name: null, home_qb_name: null,
    spread_line: null, total_line: null, roof: null, surface: null, temp: null,
    wind: null, stadium: null, overtime: 1, div_game: 0,
  }
  await page.route('**/api/schedule?*', route => route.fulfill({ json: [{ week: 22, games: [game] }] }))
  await page.goto('/standings')
  await expect(page.getByText('Super Bowl LVIII')).toBeVisible()
  await expect(page.getByRole('link', { name: /Super Bowl LVIII/ })).toHaveAttribute('href', '/games/2023_22_SF_KC')
  await expect(page.getByText('KC · Champions')).toBeVisible()
})

for (const empty of [false, true]) {
  test(`failed background refresh keeps cached ${empty ? 'empty result' : 'table'} and shows a warning`, async ({ page }) => {
    await page.clock.install()
    await mockApi(page)
    let fail = false
    await page.route('**/api/standings?*', route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Unavailable.' } }
      : { json: empty ? [] : standings() }))
    await page.goto('/standings?season=2023')
    const result = empty ? page.getByText('No standings data for 2023.') : page.getByRole('table')
    await expect(result).toBeVisible()
    await page.clock.fastForward(301_000)
    await page.clock.resume()
    await page.getByRole('combobox').selectOption('2022')
    await expect(empty ? page.getByText('No standings data for 2022.') : page.getByRole('table')).toBeVisible()
    fail = true
    await page.getByRole('combobox').selectOption('2023')
    await expect(page.getByRole('alert')).toContainText('Could not refresh standings. Showing the last successful result.')
    await expect(result).toBeVisible()
  })
}
