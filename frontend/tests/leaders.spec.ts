import { expect, type Page, type Route } from '@playwright/test'
import type { LeagueLeader, SeasonStatus, WpaLeaders } from '../src/types'
import { passer } from './fixtures/players'
import { test, mockApi } from './fixtures/scores'

const seasons: SeasonStatus[] = [
  { season: 2026, status: 'scheduled' }, { season: 2023, status: 'loaded' }, { season: 2024, status: 'loaded' },
]
const players: LeagueLeader[] = [
  { ...passer, player_id: 'alpha', player_name: 'Alpha passer', pass_yards: 5000 },
  { ...passer, player_id: 'bravo', player_name: 'Bravo passer', pass_yards: 4000 },
  { ...passer, player_id: 'charlie', player_name: 'Charlie passer', pass_yards: 3000 },
  { ...passer, player_id: 'backup', player_name: 'Backup passer', pass_yards: 6000, attempts: 10 },
  { ...passer, player_id: 'runner', player_name: 'Test runner', position: 'RB', attempts: 0, carries: 100, rush_yards: 1000 },
  { ...passer, player_id: 'receiver', player_name: 'Test receiver', position: 'WR', attempts: 0, targets: 80, rec_yards: 1500 },
  { ...passer, player_id: 'defender', player_name: 'Test defender', position: 'EDGE', attempts: 0, solo_tackles: 40, sacks: 8 },
  { ...passer, player_id: 'punter', player_name: 'Test punter', position: 'P', attempts: 0, punts: 60, punt_yards: 2700 },
]
const wpa: WpaLeaders = {
  passing: [{ player_id: 'air', player_name: 'Air passer', team: 'BUF', position: 'QB', headshot_url: null, wpa: 1.25, games_played: 17, attempts: 400 }],
  rushing: [{ player_id: 'rush', player_name: 'Rush runner', team: 'BUF', position: 'RB', headshot_url: null, wpa: 0.5, games_played: 17, carries: 100 }],
  receiving: [],
}

async function mockLeaders(page: Page, data = players, years = seasons) {
  await mockApi(page)
  await page.route('**/api/seasons', route => route.fulfill({ json: years }))
  await page.route('**/api/leaders?*', route => route.fulfill({ json: data }))
  await page.route('**/api/wpa-leaders?*', route => route.fulfill({ json: wpa }))
}

test('latest loaded season, qualified players, and sorting survive tab changes', async ({ page }) => {
  await mockLeaders(page)
  await page.goto('/leaders?source=bookmark')
  await expect(page.getByRole('combobox')).toHaveValue('2024')
  await expect(page.getByRole('option')).toHaveText(['2024', '2023'])
  const table = page.getByRole('table')
  await expect(table.locator('tbody tr').first()).toContainText('Alpha passer')
  await expect(table.getByText('Backup passer')).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('leaders-desktop.png'), fullPage: true })
  await table.getByRole('columnheader', { name: /^YDS/ }).click()
  await expect(table.locator('tbody tr').first()).toContainText('Charlie passer')
  await page.getByRole('button', { name: 'Rushing', exact: true }).click()
  await expect(table.getByText('Test runner')).toBeVisible()
  await page.getByRole('button', { name: 'Passing', exact: true }).click()
  await expect(table.locator('tbody tr').first()).toContainText('Charlie passer')
  await page.getByRole('combobox').selectOption('2023')
  await expect(page).toHaveURL(/source=bookmark.*season=2023/)
})

test('position views preserve looser qualifications and typed punting columns', async ({ page }) => {
  await mockLeaders(page)
  await page.goto('/leaders?season=2023&mode=positions&pos=qb')
  const table = page.getByRole('table')
  await expect(table.locator('tbody tr').first()).toContainText('Backup passer')
  await page.screenshot({ path: test.info().outputPath('leaders-positions.png'), fullPage: true })
  await page.getByRole('button', { name: 'P', exact: true }).click()
  await expect(table.getByText('Test punter')).toBeVisible()
  await expect(table.getByRole('cell', { name: '45.0', exact: true })).toBeVisible()
  await expect(table.getByRole('link', { name: 'Test punter' })).toHaveAttribute('href', '/players/punter')
})

test('numeric sorting uses raw values and keyboard activation keeps a two-way cycle', async ({ page }) => {
  await mockLeaders(page, [
    { ...players[0], pass_yards: 9900 },
    { ...players[1], pass_yards: 12000 },
    { ...players[2], pass_yards: 900 },
  ])
  await page.goto('/leaders?season=2023')
  const table = page.getByRole('table')
  const header = table.getByRole('columnheader', { name: 'YDS', exact: true })
  const button = header.getByRole('button', { name: 'YDS', exact: true })
  await expect(header).toHaveAttribute('aria-sort', 'descending')
  await expect(table.locator('tbody tr').first()).toContainText('Bravo passer')
  await expect(table.getByRole('cell', { name: '12,000', exact: true })).toBeVisible()
  await button.focus()
  await button.press('Enter')
  await expect(header).toHaveAttribute('aria-sort', 'ascending')
  await expect(table.locator('tbody tr').first()).toContainText('Charlie passer')
  await button.press('Space')
  await expect(header).toHaveAttribute('aria-sort', 'descending')
  await expect(table.locator('tbody tr').first()).toContainText('Bravo passer')
  await button.press('Enter')
  await expect(header).toHaveAttribute('aria-sort', 'ascending')
})

test('advanced values, ties, and single-column sorting preserve their meaning', async ({ page }) => {
  await mockLeaders(page, [
    { ...players[0], pass_yards: 5000, interceptions_thrown: 5, pass_epa: 100 },
    { ...players[1], pass_yards: 5000, interceptions_thrown: 10, pass_epa: -50 },
    { ...players[2], pass_yards: 5000, interceptions_thrown: 2, pass_epa: 0 },
  ])
  await page.goto('/leaders?season=2023')
  const table = page.getByRole('table')
  await expect(table.locator('tbody tr').first()).toContainText('Alpha passer')
  await expect(table.getByRole('columnheader', { name: 'Stats', exact: true })).toHaveAttribute('colspan', '11')
  await expect(table.getByRole('columnheader', { name: 'Advanced', exact: true })).toHaveAttribute('colspan', '2')
  await expect(table.getByText('-0.086', { exact: true })).toHaveClass(/text-data-loss/)
  await expect(table.getByText('+0.173', { exact: true })).toHaveClass(/text-data-win/)
  await expect(table.getByRole('cell', { name: '—', exact: true }).first()).toBeVisible()
  await table.getByRole('button', { name: 'INT', exact: true }).click()
  await expect(table.locator('tbody tr').first()).toContainText('Bravo passer')
  await table.getByRole('button', { name: 'EPA/Att', exact: true }).click({ modifiers: ['Shift'] })
  await expect(table.locator('thead th[aria-sort="descending"]')).toHaveCount(1)
  await expect(table.locator('tbody tr').first()).toContainText('Alpha passer')
  await table.getByRole('button', { name: 'YDS', exact: true }).click()
  await expect(table.locator('tbody tr').first()).toContainText('Alpha passer')
})

test('dashboard, podium, and historical awards retain their links and labels', async ({ page }) => {
  await mockLeaders(page)
  await page.goto('/leaders?season=2023')
  await expect(page.getByText('2023 Award Winners')).toBeVisible()
  await expect(page.getByText('Lamar Jackson', { exact: true })).toBeVisible()
  await expect(page.getByText('1st', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /Rushing Leader/ }).click()
  await expect(page).toHaveURL(/tab=rushing/)
  await expect(page.getByRole('table').getByText('Test runner')).toBeVisible()
})

test('WPA loads on demand, shares subtab data, and stays cached when reopened', async ({ page }) => {
  await mockLeaders(page)
  let requests = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/wpa-leaders') requests++ })
  await page.goto('/leaders?season=2023')
  await expect(page.getByRole('table')).toBeVisible()
  expect(requests).toBe(0)
  await page.getByRole('button', { name: 'WPA', exact: true }).click()
  await expect(page.getByRole('table').getByText('Air passer')).toBeVisible()
  const initialRequests = requests
  await page.getByRole('button', { name: 'rushing', exact: true }).click()
  await expect(page.getByRole('table').getByText('Rush runner')).toBeVisible()
  await page.getByRole('button', { name: 'Passing', exact: true }).first().click()
  await expect(page.getByRole('table').getByText('Alpha passer')).toBeVisible()
  await page.getByRole('button', { name: 'WPA', exact: true }).click()
  await expect(page.getByRole('table').getByText('Rush runner')).toBeVisible()
  expect(requests).toBe(initialRequests)
  await page.getByRole('button', { name: 'receiving', exact: true }).click()
  await expect(page.getByText('No WPA data for 2023.')).toBeVisible()
})

for (const resource of ['seasons', 'leaders', 'wpa-leaders'] as const) {
  test(`${resource} errors have a working retry`, async ({ page }) => {
    await mockLeaders(page)
    let fail = true
    await page.route(resource === 'seasons' ? '**/api/seasons' : `**/api/${resource}?*`, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Temporarily unavailable.' } }
      : { json: resource === 'seasons' ? seasons : resource === 'leaders' ? players : wpa }))
    await page.goto(`/leaders?season=2023${resource === 'wpa-leaders' ? '&tab=wpa' : ''}`)
    await expect(page.getByRole('alert')).toContainText('Temporarily unavailable.')
    fail = false
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByRole('table')).toBeVisible()
  })
}

test('unavailable links do not fetch statistics or WPA', async ({ page }) => {
  await mockLeaders(page)
  const requests: string[] = []
  page.on('request', request => {
    if (['/api/leaders', '/api/wpa-leaders'].includes(new URL(request.url()).pathname)) requests.push(request.url())
  })
  await page.goto('/leaders?season=2026&tab=wpa')
  await expect(page.getByRole('alert')).toContainText('That season is unavailable')
  expect(requests).toEqual([])
  await page.getByRole('combobox').selectOption('2023')
  await expect(page.getByRole('table').getByText('Air passer')).toBeVisible()
})

test('empty statistics end loading and invalid view parameters fall back consistently', async ({ page }) => {
  await mockLeaders(page, [])
  await page.goto('/leaders?season=2023&mode=invalid&tab=invalid')
  await expect(page.getByText('No Passing data for 2023.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Stat Leaders', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('button', { name: 'Passing', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('status')).toHaveCount(0)
})

test('fresh statistics are shared from Scores to Leaders', async ({ page }) => {
  await mockLeaders(page)
  let requests = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/leaders') requests++ })
  await page.goto('/?season=2023')
  await expect(page.getByText('Alpha passer', { exact: true })).toBeVisible()
  const initialRequests = requests
  await page.getByRole('link', { name: 'All leaders', exact: true }).click()
  await expect(page.getByRole('table')).toBeVisible()
  expect(requests).toBe(initialRequests)
})

test('season changes cancel both statistics and WPA requests', async ({ page }) => {
  await mockLeaders(page)
  const oldRoutes: Route[] = []
  await page.route(url => ['/api/leaders', '/api/wpa-leaders'].includes(url.pathname) && url.searchParams.get('season') === '2023', route => { oldRoutes.push(route) })
  await page.goto('/leaders?season=2023&tab=wpa')
  // StrictMode can probe/restart WPA when its panel first mounts.
  await expect.poll(() => new Set(oldRoutes.map(route => new URL(route.request().url()).pathname)).size).toBe(2)
  await page.getByRole('combobox').selectOption('2024')
  await expect(page.getByRole('table').getByText('Air passer')).toBeVisible()
  for (const route of oldRoutes) {
    await route.fulfill({ json: new URL(route.request().url()).pathname === '/api/leaders' ? [{ ...passer, player_name: 'Late passer' }] : { ...wpa, passing: [{ ...wpa.passing[0], player_name: 'Late WPA passer' }] } })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
  await expect(page.getByText('Late passer')).toHaveCount(0)
  await expect(page.getByText('Late WPA passer')).toHaveCount(0)
})

test('mobile tables scroll inside the page and preserve player links', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockLeaders(page)
  await page.goto('/leaders?season=2023')
  await expect(page.getByRole('table').getByRole('link', { name: 'Alpha passer' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('leaders-mobile.png'), fullPage: true })
})

test('WPA remains usable when ordinary player statistics fail', async ({ page }) => {
  await mockLeaders(page)
  await page.route('**/api/leaders?*', route => route.fulfill({ status: 503, json: { detail: 'Unavailable.' } }))
  await page.goto('/leaders?season=2023&tab=wpa')
  await expect(page.getByRole('alert')).toContainText('Could not load player statistics.')
  await expect(page.getByRole('table').getByText('Air passer')).toBeVisible()
})

for (const resource of ['leaders', 'wpa-leaders'] as const) {
  test(`failed background ${resource} refresh preserves cached data`, async ({ page }) => {
    await page.clock.install()
    await mockLeaders(page)
    let fail = false
    await page.route(`**/api/${resource}?*`, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Unavailable.' } }
      : { json: resource === 'leaders' ? players : wpa }))
    await page.goto(`/leaders?season=2023${resource === 'wpa-leaders' ? '&tab=wpa' : ''}`)
    const name = resource === 'leaders' ? 'Alpha passer' : 'Air passer'
    await expect(page.getByRole('table').getByText(name)).toBeVisible()
    await page.clock.fastForward(301_000)
    await page.clock.resume()
    await page.getByRole('combobox').selectOption('2024')
    await expect(page.getByText('2024 NFL Season')).toBeVisible()
    await expect(page.getByRole('table').getByText(name)).toBeVisible()
    fail = true
    await page.getByRole('combobox').selectOption('2023')
    await expect(page.getByRole('alert')).toContainText('Showing the last successful result.')
    await expect(page.getByRole('table').getByText(name)).toBeVisible()
  })
}
