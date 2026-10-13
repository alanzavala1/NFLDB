import { passer } from './fixtures/players'
import { expect, type Page, type Route } from '@playwright/test'
import type { DivisionStandings, PowerRankingRow } from '../src/types'
import { test, mockApi, seasonList, game } from './fixtures/scores'

const resources = ['schedule', 'standings', 'leaders', 'power-rankings'] as const
type Resource = typeof resources[number]

function result(resource: Resource, year: number) {
  const team = year === 2026 ? 'BUF' : 'MIA'
  if (resource === 'schedule') return [{ week: 1, games: [{ ...game, season: year, game_id: `${year}_game` }] }]
  if (resource === 'standings') return [{ division: 'AFC East', teams: [{
    team, w: 11, l: 6, t: 0, pct: 11 / 17, pf: 451, pa: 311,
    home: '7-2', away: '4-4', div: '4-2', strk: 'W5', gb: '—',
  }] }] satisfies DivisionStandings[]
  if (resource === 'leaders') return [{ ...passer, player_name: `${year} passer`, team }]
  return [{ rank: 1, team, record: '11-6', net_epa_play: 0.15, movement: 1 }] satisfies PowerRankingRow[]
}

async function populatedApi(page: Page) {
  await mockApi(page)
  await page.route(url => resources.some(resource => url.pathname === `/api/${resource}`), route => {
    const url = new URL(route.request().url())
    const resource = url.pathname.slice(5) as Resource
    return route.fulfill({ json: result(resource, Number(url.searchParams.get('season'))) })
  })
}

test('waits for season metadata before requesting all four independent resources', async ({ page }) => {
  await populatedApi(page)
  let release!: () => void
  const ready = new Promise<void>(resolve => { release = resolve })
  const reads: string[] = []
  page.on('request', request => {
    if (resources.some(resource => new URL(request.url()).pathname === `/api/${resource}`)) reads.push(request.url())
  })
  await page.route('**/api/seasons', async route => {
    await ready
    await route.fulfill({ json: seasonList })
  })
  await page.goto('/?season=2026')
  await expect(page.getByText('Loading seasons...')).toBeVisible()
  expect(reads).toEqual([])
  release()
  await expect(page.getByText('2026 passer', { exact: true })).toBeVisible()
  await expect.poll(() => reads.length).toBe(4)
})

for (const resource of resources) {
  test(`${resource} error ends loading, leaves other sections usable, and retry recovers`, async ({ page }) => {
    await populatedApi(page)
    let fail = true
    await page.route(`**/api/${resource}?*`, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Temporarily unavailable.' } }
      : { json: result(resource, 2026) }))
    await page.goto('/?season=2026')
    await expect(page.getByRole('alert').first()).toContainText('Temporarily unavailable.')
    if (resource !== 'schedule') await expect(page.locator('a[href="/games/2026_game"]').first()).toBeVisible()
    if (resource !== 'leaders') await expect(page.getByText('2026 passer', { exact: true })).toBeVisible()
    await expect(page.getByText(/^(Power rankings loading|Standings loading|Leaders loading|Loading schedule)/)).toHaveCount(0)
    fail = false
    await page.getByRole('button', { name: 'Try again' }).first().click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.locator('a[href="/games/2026_game"]').first()).toBeVisible()
    await expect(page.getByText('2026 passer', { exact: true })).toBeVisible()
  })
}

test('fresh cache is shared with Standings and reused when returning to Scores', async ({ page }) => {
  await populatedApi(page)
  const counts: Record<string, number> = {}
  page.on('request', request => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/')) counts[path] = (counts[path] ?? 0) + 1
  })
  await page.goto('/?season=2023')
  await expect(page.getByText('2023 passer', { exact: true })).toBeVisible()
  await expect(page.locator('a[href="/games/2023_game"]').first()).toBeVisible()
  await expect(page.getByText('+0.15', { exact: true })).toBeVisible()
  await expect(page.getByText('+140', { exact: true })).toBeVisible()
  // React StrictMode may probe/cancel the first mount in development.
  // Once all results are ready, navigation must not add requests for fresh data.
  const initialCounts = { ...counts }
  await page.screenshot({ path: test.info().outputPath('scores-desktop.png'), fullPage: true })
  await page.getByRole('link', { name: 'Full standings' }).first().click()
  await expect(page.getByRole('table')).toBeVisible()
  await page.goBack()
  await expect(page.getByText('2023 passer', { exact: true })).toBeVisible()
  expect(counts['/api/seasons']).toBe(initialCounts['/api/seasons'])
  for (const resource of resources) expect(counts[`/api/${resource}`]).toBe(initialCounts[`/api/${resource}`])
})

test('switching seasons cancels all old requests without mixing any section data', async ({ page }) => {
  await populatedApi(page)
  const oldRoutes: Route[] = []
  await page.route(url => resources.some(resource => url.pathname === `/api/${resource}`) && url.searchParams.get('season') === '2023', route => {
    oldRoutes.push(route)
  })
  await page.goto('/?season=2023')
  await expect.poll(() => oldRoutes.length).toBe(4)
  await page.getByRole('combobox').selectOption('2026')
  await expect(page.getByText('2026 passer', { exact: true })).toBeVisible()
  await expect(page.locator('a[href="/games/2026_game"]').first()).toBeVisible()
  for (const route of oldRoutes) {
    await route.fulfill({ json: result(new URL(route.request().url()).pathname.slice(5) as Resource, 2023) })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
  await expect(page.getByText('2023 passer', { exact: true })).toHaveCount(0)
  await expect(page.locator('a[href="/games/2023_game"]')).toHaveCount(0)
  await expect(page.locator('main a[href="/teams/MIA"]')).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

for (const resource of resources) {
  test(`failed background ${resource} refresh retains cached results and warns`, async ({ page }) => {
    await page.clock.install()
    await populatedApi(page)
    let fail = false
    await page.route(`**/api/${resource}?*`, route => {
      const year = Number(new URL(route.request().url()).searchParams.get('season'))
      return route.fulfill(fail && year === 2023
        ? { status: 503, json: { detail: 'Unavailable.' } }
        : { json: result(resource, year) })
    })
    await page.goto('/?season=2023')
    await expect(page.getByText('2023 passer', { exact: true })).toBeVisible()
    await expect(page.locator('main a[href="/teams/MIA"]').first()).toBeVisible()
    await page.clock.fastForward(301_000)
    await page.clock.resume()
    await page.getByRole('combobox').selectOption('2026')
    await expect(page.getByText('2026 passer', { exact: true })).toBeVisible()
    fail = true
    await page.getByRole('combobox').selectOption('2023')
    await expect(page.getByRole('alert').first()).toContainText('Showing the last successful result.')
    await expect(page.getByText('2023 passer', { exact: true })).toBeVisible()
    await expect(page.locator('a[href="/games/2023_game"]').first()).toBeVisible()
    await expect(page.locator('main a[href="/teams/MIA"]').first()).toBeVisible()
  })
}

test('a cached empty rankings result still shows a failed-refresh warning', async ({ page }) => {
  await page.clock.install()
  await populatedApi(page)
  let fail = false
  await page.route('**/api/power-rankings?*', route => route.fulfill(fail
    ? { status: 503, json: { detail: 'Unavailable.' } }
    : { json: [] }))
  await page.goto('/?season=2023')
  await expect(page.getByText('No rankings found', { exact: true })).toBeVisible()
  await page.clock.fastForward(301_000)
  await page.clock.resume()
  await page.getByRole('combobox').selectOption('2026')
  await expect(page.getByText('2026 passer', { exact: true })).toBeVisible()
  fail = true
  await page.getByRole('combobox').selectOption('2023')
  await expect(page.getByRole('alert')).toContainText('Could not refresh power rankings. Showing the last successful result.')
  await expect(page.getByText('No rankings found', { exact: true })).toBeVisible()
})
