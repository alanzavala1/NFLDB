import { expect, type Page, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockSplits } from './fixtures/splits'

const published = [{ season: 2023, status: 'loaded' }, { season: 2022, status: 'loaded' }]

async function mockPublished(page: Page) {
  await mockSplits(page)
  await page.route('**/api/seasons', route => route.fulfill({ json: published }))
}

function summary(page: Page) {
  return page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Player', exact: true }) })
}

function dataReads(page: Page) {
  const reads: string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/players/') || url.pathname.startsWith('/api/teams/') || url.pathname === '/api/team-analytics') reads.push(url.pathname + url.search)
  })
  return reads
}

test('player defaults keep Career and offer only published years without rewriting the bookmark', async ({ page }) => {
  await mockPublished(page)
  await page.goto('/splits?p=test-player&campaign=phone')
  const season = page.getByRole('combobox', { name: 'Season' })
  await expect(season).toHaveValue('0')
  await expect(season.getByRole('option')).toHaveText(['Career', '2023', '2022'])
  await expect(summary(page).getByRole('cell', { name: '550', exact: true })).toBeVisible()
  expect(Object.fromEntries(new URL(page.url()).searchParams)).toEqual({ p: 'test-player', campaign: 'phone' })
})

test('bare team links use the newest published year and never request year zero or a guessed calendar year', async ({ page }) => {
  await mockPublished(page)
  const reads = dataReads(page)
  await page.goto('/splits?mode=teams&t=BUF&campaign=phone')
  await expect(page.getByRole('combobox', { name: 'Season' })).toHaveValue('2023')
  await expect(page.getByRole('cell', { name: '+0.200', exact: true }).first()).toBeVisible()
  expect(reads).toEqual(['/api/teams/BUF/splits?season=2023'])
  await expect(page.getByRole('option', { name: 'Career', exact: true })).toHaveCount(0)
  expect(new URL(page.url()).searchParams.has('season')).toBe(false)
})

test('old player bookmarks survive reload and season history restores data from the same cached resource', async ({ page }) => {
  await mockPublished(page)
  await page.goto('/splits?p=test-player&season=2022&campaign=phone')
  await expect(summary(page).getByRole('cell', { name: '300', exact: true })).toBeVisible()
  await page.reload()
  await expect(summary(page).getByRole('cell', { name: '300', exact: true })).toBeVisible()
  const reads = dataReads(page)
  const season = page.getByRole('combobox', { name: 'Season' })
  await season.selectOption('2023')
  await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toBeVisible()
  await season.selectOption('0')
  await expect(summary(page).getByRole('cell', { name: '550', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Passing', exact: true }).click()
  await page.goBack()
  await expect(season).toHaveValue('2023')
  await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toBeVisible()
  await page.goBack()
  await expect(season).toHaveValue('2022')
  await expect(summary(page).getByRole('cell', { name: '300', exact: true })).toBeVisible()
  await page.goForward()
  await expect(season).toHaveValue('2023')
  expect(reads.filter(path => path.startsWith('/api/players/'))).toEqual([])
  expect(new URL(page.url()).searchParams.get('campaign')).toBe('phone')
})

test('situations, category, mode and side update atomically and back/forward restores the comparison', async ({ page }) => {
  await mockPublished(page)
  await page.goto('/splits?p=test-player&t=BUF&season=0&campaign=phone')
  await expect(summary(page).getByRole('cell', { name: '550', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '3rd Down', exact: true }).click()
  await expect(summary(page).getByRole('cell', { name: '50', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Rushing', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Overall', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(summary(page).getByRole('cell', { name: '15', exact: true })).toBeVisible()
  expect(new URL(page.url()).searchParams.has('sit')).toBe(false)
  await page.getByRole('button', { name: 'Teams', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Season' })).toHaveValue('2023')
  expect(new URL(page.url()).searchParams.has('season')).toBe(false)
  await page.getByRole('button', { name: 'Defense', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Defense', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Offense', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Rushing', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('combobox', { name: 'Season' })).toHaveValue('0')
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Passing', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('button', { name: '3rd Down', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(summary(page).getByRole('cell', { name: '50', exact: true })).toBeVisible()
  await page.goForward()
  await expect(page.getByRole('button', { name: 'Rushing', exact: true })).toHaveAttribute('aria-pressed', 'true')
  expect(new URL(page.url()).searchParams.get('campaign')).toBe('phone')
  expect(new URL(page.url()).searchParams.get('t')).toBe('BUF')
})

test('adding/removing members preserves unrelated URL fields and history restores their cached data', async ({ page }) => {
  await mockPublished(page)
  await page.goto('/splits?p=test-player&season=2023&campaign=phone')
  await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: 'Add player' }).fill('Second quarterback')
  await page.getByRole('button', { name: /^Second quarterback/ }).click()
  await expect(summary(page).getByRole('cell', { name: '500', exact: true })).toBeVisible()
  const reads = dataReads(page)
  await page.getByRole('button', { name: 'Remove Test quarterback', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Remove Test quarterback', exact: true })).toHaveCount(0)
  expect(new URL(page.url()).searchParams.get('p')).toBe('other-player')
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Remove Test quarterback', exact: true })).toBeVisible()
  await expect(summary(page).getByRole('cell', { name: '500', exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Remove Second quarterback', exact: true })).toHaveCount(0)
  await page.goForward()
  await expect(summary(page).getByRole('cell', { name: '500', exact: true })).toBeVisible()
  expect(reads.filter(path => path.startsWith('/api/players/'))).toEqual([])
  expect(new URL(page.url()).searchParams.get('campaign')).toBe('phone')
})

for (const mode of ['players', 'teams']) {
  for (const year of ['banana', '', '2023.5', ' 2023 ', '2027', ...(mode === 'teams' ? ['0'] : [])]) {
    test(`${mode} invalid or unpublished season '${year}' makes no data requests and can be corrected`, async ({ page }) => {
      await mockPublished(page)
      const reads = dataReads(page)
      await page.goto(`/splits?mode=${mode}&p=test-player&t=BUF&season=${encodeURIComponent(year)}&campaign=phone`)
      await expect(page.getByRole('alert')).toContainText('That season is unavailable.')
      await expect(page.getByRole('table')).toHaveCount(0)
      expect(reads).toEqual([])
      expect(new URL(page.url()).searchParams.get('season')).toBe(year)
      await page.getByRole('combobox', { name: 'Season' }).selectOption('2023')
      await expect(page.getByRole('alert')).toHaveCount(0)
      await expect(page.getByRole('table').first()).toBeVisible()
      expect(new URL(page.url()).searchParams.get('campaign')).toBe('phone')
    })
  }
}

for (const status of ['available', 'loading', 'queued', 'error', 'scheduled'] as const) {
  test(`a ${status} year is excluded from player and team comparisons`, async ({ page }) => {
    await mockPublished(page)
    await page.route('**/api/seasons', route => route.fulfill({ json: [{ season: 2026, status }, ...published] }))
    const reads = dataReads(page)
    for (const mode of ['players', 'teams']) {
      await page.goto(`/splits?mode=${mode}&p=test-player&t=BUF&season=2026`)
      await expect(page.getByRole('alert')).toContainText('That season is unavailable.')
      await expect(page.getByRole('option', { name: '2026', exact: true })).toHaveCount(0)
    }
    expect(reads).toEqual([])
  })
}

test('pending/failed season metadata starts no data queries, preserves the bookmark, and retries', async ({ page }) => {
  await mockPublished(page)
  const pending: Route[] = []
  const reads = dataReads(page)
  await page.route('**/api/seasons', route => { pending.push(route) })
  await page.goto('/splits?mode=teams&t=BUF&season=2022&campaign=phone')
  await expect(page.getByRole('status')).toHaveText('Loading available seasons…')
  await expect(page.getByRole('combobox', { name: 'Season' })).toBeDisabled()
  expect(reads).toEqual([])
  await page.route('**/api/seasons', route => route.fulfill({ status: 503, json: { detail: 'Metadata unavailable.' } }))
  for (const route of pending) await route.fulfill({ status: 503, json: { detail: 'Metadata unavailable.' } })
  await expect(page.getByRole('alert')).toContainText('Metadata unavailable.')
  await expect(page.getByRole('status')).toHaveCount(0)
  expect(reads).toEqual([])
  expect(new URL(page.url()).searchParams.get('season')).toBe('2022')
  await page.route('**/api/seasons', route => route.fulfill({ json: published }))
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Season' })).toHaveValue('2022')
  await expect(page.getByRole('table').first()).toBeVisible()
  expect(reads).toEqual(['/api/teams/BUF/splits?season=2022'])
  expect(new URL(page.url()).searchParams.get('campaign')).toBe('phone')
})

test('no published seasons gives an empty state and disables both comparison modes without data requests', async ({ page }) => {
  await mockPublished(page)
  await page.route('**/api/seasons', route => route.fulfill({ json: [] }))
  const reads = dataReads(page)
  await page.goto('/splits?p=test-player&t=BUF')
  await expect(page.getByText('No published seasons are available for comparisons.', { exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Season' })).toBeDisabled()
  await page.getByRole('button', { name: 'Teams', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Season' })).toBeDisabled()
  await expect(page.getByRole('table')).toHaveCount(0)
  expect(reads).toEqual([])
})

test('mobile selection recovers an unavailable player year through Career and preserves its link', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockPublished(page)
  await page.goto('/splits?p=test-player&season=2026&campaign=phone')
  await expect(page.getByRole('alert')).toContainText('or Career')
  await page.getByRole('combobox', { name: 'Season' }).selectOption('0')
  await expect(summary(page).getByRole('cell', { name: '550', exact: true })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('season')).toBe('0')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

for (const empty of [false, true]) {
  test(`failed metadata refresh retains ${empty ? 'empty' : 'published'} cached availability and retry uses the new publication list`, async ({ page }) => {
    await page.clock.install()
    await mockPublished(page)
    let fail = false
    let years = empty ? [] : published
    await page.route('**/api/seasons', route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Metadata unavailable.' } } : { json: years }))
    await page.goto('/splits?p=test-player&season=2023&campaign=phone')
    if (empty) await expect(page.getByText('No published seasons are available for comparisons.', { exact: true })).toBeVisible()
    else await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toBeVisible()
    await page.getByRole('link', { name: 'Scores', exact: true }).click()
    await expect(page.locator('main')).toBeVisible()
    await page.clock.fastForward(31_000)
    await page.clock.resume()
    fail = true
    await page.goBack()
    await expect(page.getByRole('alert')).toContainText('Could not refresh available seasons. Showing the last successful result.')
    if (empty) await expect(page.getByText('No published seasons are available for comparisons.', { exact: true })).toBeVisible()
    else await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toBeVisible()
    fail = false
    years = [{ season: 2022, status: 'loaded' }]
    await page.getByRole('button', { name: 'Try again', exact: true }).click()
    await expect(page.getByRole('alert')).toHaveText('That season is unavailable. Choose a published season or Career above.')
    await expect(page.getByRole('table')).toHaveCount(0)
    expect(new URL(page.url()).searchParams.get('season')).toBe('2023')
    await page.getByRole('combobox', { name: 'Season' }).selectOption('2022')
    await expect(summary(page).getByRole('cell', { name: '300', exact: true })).toBeVisible()
  })
}

test('duplicate or oversized bookmarked member lists create at most six unique observers', async ({ page }) => {
  await mockPublished(page)
  const reads = dataReads(page)
  await page.goto('/splits?p=one,one,two,three,four,five,six,seven&season=2023')
  await expect(page.getByRole('button', { name: /^Remove Test quarterback/ })).toHaveCount(6)
  await expect(page.getByRole('status')).toHaveCount(0)
  expect(reads.filter(path => path.endsWith('/splits')).sort()).toEqual(['one', 'two', 'three', 'four', 'five', 'six'].map(id => `/api/players/${id}/splits`).sort())
})

test('a multi-player example creates one history entry with both resolved members', async ({ page }) => {
  await mockPublished(page)
  await page.route(url => url.pathname === '/api/search', route => route.fulfill({ json: [{
    type: 'player', id: new URL(route.request().url()).searchParams.get('q') === 'Josh Allen' ? 'test-player' : 'other-player',
    name: new URL(route.request().url()).searchParams.get('q'), position: 'QB', team: 'BUF', headshot_url: null,
  }] }))
  await page.goto('/splits?campaign=phone')
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Remove Josh Allen', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove Patrick Mahomes', exact: true })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('p')).toBe('test-player,other-player')
  await page.goBack()
  await expect(page.getByText('Compare anyone, in any situation', { exact: true })).toBeVisible()
  expect(Object.fromEntries(new URL(page.url()).searchParams)).toEqual({ campaign: 'phone' })
})

test('an unfinished example cannot overwrite a later mode selection', async ({ page }) => {
  await mockPublished(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === '/api/search', route => { pending.push(route) })
  await page.goto('/splits?campaign=phone')
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect.poll(() => pending.length).toBe(1)
  await page.getByRole('button', { name: 'Teams', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Teams', exact: true })).toHaveAttribute('aria-pressed', 'true')
  for (const route of pending) await route.fulfill({ json: [{ type: 'player', id: 'test-player', name: 'Late player', position: 'QB', team: 'BUF', headshot_url: null }] })
  await expect(page.getByText('Compare anyone, in any situation', { exact: true })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('mode')).toBe('teams')
  expect(new URL(page.url()).searchParams.has('p')).toBe(false)
  expect(new URL(page.url()).searchParams.get('campaign')).toBe('phone')
})
