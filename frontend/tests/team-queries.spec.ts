import { expect, type Page, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockTeam, mockTeamSections, teamProfile, analyticsRow, teamSplit, injury, starter, rosterPlayer } from './fixtures/teamProfile'

const resources = {
  profile: { path: '/api/teams/BUF', label: '2023 team profile', json: teamProfile },
  analytics: { path: '/api/team-analytics', label: 'team analytics', json: { season: 2023, league: [analyticsRow] } },
  splits: { path: '/api/teams/BUF/splits', label: 'situational splits', json: [teamSplit] },
  injuries: { path: '/api/teams/BUF/injuries', label: 'injury report', json: [injury] },
  depth: { path: '/api/teams/BUF/depth-chart', label: 'starting lineup', json: [starter] },
  roster: { path: '/api/teams/BUF/roster', label: 'roster', json: [rosterPlayer] },
}

async function loadedSections(page: Page) {
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Team Analytics', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Leading', exact: true })).toBeVisible()
  await expect(page.getByText('Injured quarterback', { exact: true })).toBeVisible()
  await expect(page.getByText('Starting quarterback', { exact: true })).toBeVisible()
}

async function openRoster(page: Page) {
  await page.getByRole('button', { name: 'Roster', exact: true }).click()
  await expect(page.getByText('2023 Roster', { exact: true })).toBeVisible()
}

async function searchTeam(page: Page, id: string) {
  await page.route('**/api/search?*', route => route.fulfill({ json: [{ type: 'team', id, name: id, position: null, team: id, headshot_url: null }] }))
  await page.getByRole('button', { name: /Search Ctrl K/ }).click()
  await page.getByPlaceholder('Search players or teams...').fill(id)
  await page.getByRole('button', { name: id === 'BUF' ? /Buffalo Bills/ : /San Francisco 49ers/ }).click()
}

test('roster loads on demand and reuses fresh results when reopened', async ({ page }) => {
  await mockTeamSections(page)
  let reads = 0
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/roster')) reads++ })
  await page.goto('/teams/BUF')
  await loadedSections(page)
  expect(reads).toBe(0)
  await openRoster(page)
  await expect(page.getByRole('link', { name: /Roster quarterback/ })).toBeVisible()
  const initialReads = reads
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  await openRoster(page)
  await expect(page.getByRole('link', { name: /Roster quarterback/ })).toBeVisible()
  expect(reads).toBe(initialReads)
})

test('roster entries with an unmapped position remain visible in Other', async ({ page }) => {
  await mockTeamSections(page)
  await page.route('**/api/teams/BUF/roster?*', route => route.fulfill({ json: [{ ...rosterPlayer, position: null }] }))
  await page.goto('/teams/BUF')
  await openRoster(page)
  await expect(page.getByText('Other', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /Roster quarterback/ })).toBeVisible()
  await expect(page.getByText('No roster data available for this season.')).toHaveCount(0)
})

test('fresh league analytics are shared between team pages while team-specific data stays separate', async ({ page }) => {
  await mockTeamSections(page)
  let analyticsReads = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/team-analytics') analyticsReads++ })
  await page.goto('/teams/BUF')
  await loadedSections(page)
  const initialReads = analyticsReads
  await searchTeam(page, 'SF')
  await expect(page.getByText('San Francisco 49ers', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Team Analytics', exact: true })).toBeVisible()
  await expect(page.getByText('No starting lineup is available for this season.')).toBeVisible()
  await expect(page.getByText('Starting quarterback', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Injured quarterback', { exact: true })).toHaveCount(0)
  expect(analyticsReads).toBe(initialReads)
})

test('Splits and the Team page share fresh team split results', async ({ page }) => {
  await mockTeamSections(page)
  let splitReads = 0
  page.on('request', request => { if (new URL(request.url()).pathname === resources.splits.path) splitReads++ })
  await page.goto('/splits?mode=teams&t=BUF&season=2023')
  await expect(page.getByRole('cell', { name: 'Leading', exact: true })).toBeVisible()
  const initialReads = splitReads
  await searchTeam(page, 'BUF')
  await expect(page.getByRole('heading', { name: 'Situational Splits', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Leading', exact: true })).toBeVisible()
  expect(splitReads).toBe(initialReads)
})

for (const [name, resource] of Object.entries(resources)) {
  test(`${name} errors expose backend details and retry only the failed resource`, async ({ page }) => {
    await mockTeamSections(page)
    let fail = true
    const reads: string[] = []
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) reads.push(request.url()) })
    await page.route(url => url.pathname === resource.path && url.searchParams.get('season') === '2023', route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Published data is temporarily unavailable.' } } : { json: resource.json }))
    await page.goto('/teams/BUF')
    if (name === 'roster') await openRoster(page)
    await expect(page.getByRole('alert')).toContainText(`Could not load ${resource.label}. Published data is temporarily unavailable.`)
    if (name !== 'profile' && name !== 'roster') {
      await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
      await expect(page.locator('a[href^="/games/2023_01_BUF_MIA"]')).toBeVisible()
    }
    const readCount = reads.length
    fail = false
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    if (name === 'roster') await expect(page.getByRole('link', { name: /Roster quarterback/ })).toBeVisible()
    else await loadedSections(page)
    const retried = reads.slice(readCount).map(url => new URL(url).pathname)
    if (name !== 'profile') expect(retried).toEqual([resource.path])
  })
}

test('each successful empty section has an honest message', async ({ page }) => {
  await mockTeam(page)
  await page.goto('/teams/BUF')
  await expect(page.getByText('Analytics unavailable for this season.')).toBeVisible()
  await expect(page.getByText('No situational splits are available for this season.')).toBeVisible()
  await expect(page.getByText('No injury report is available for this season.')).toBeVisible()
  await expect(page.getByText('No starting lineup is available for this season.')).toBeVisible()
  await openRoster(page)
  await expect(page.getByText('No roster data available for this season.')).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('non-JSON profile failures use the shared fallback', async ({ page }) => {
  await mockTeam(page)
  await page.route('**/api/teams/BUF?*', route => route.fulfill({ status: 502, contentType: 'text/html', body: '<h1>Bad gateway</h1>' }))
  await page.goto('/teams/BUF')
  await expect(page.getByRole('alert')).toContainText('Request failed (502). Please try again.')
})

for (const [name, resource] of Object.entries(resources)) {
  test(`leaving the ${name === 'roster' ? 'modal' : 'page'} cancels unfinished ${name} requests`, async ({ page }) => {
    await mockTeamSections(page)
    const pending: Route[] = []
    await page.route(url => url.pathname === resource.path && url.searchParams.get('season') === '2023', route => { pending.push(route) })
    await page.goto('/teams/BUF')
    if (name === 'roster') await openRoster(page)
    await expect.poll(() => pending.length).toBeGreaterThan(0)
    if (name === 'roster') {
      await page.getByRole('button', { name: 'Close', exact: true }).click()
      await expect(page.getByText('2023 Roster', { exact: true })).toHaveCount(0)
    } else {
      await page.getByRole('link', { name: 'Scores', exact: true }).click()
      await expect(page.getByRole('combobox', { name: 'Season', exact: true })).toBeVisible()
    }
    for (const route of pending) {
      await route.fulfill({ json: resource.json })
      await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
    }
  })
}

test('season switching cancels old section requests and late responses cannot replace the new season', async ({ page }) => {
  await mockTeamSections(page)
  const pending: Route[] = []
  const paths = [resources.analytics.path, resources.splits.path, resources.injuries.path, resources.depth.path]
  await page.route(url => paths.includes(url.pathname) && url.searchParams.get('season') === '2023', route => { pending.push(route) })
  await page.goto('/teams/BUF')
  await expect.poll(() => new Set(pending.map(route => new URL(route.request().url()).pathname)).size).toBe(4)
  await page.getByRole('button', { name: /^2022/ }).click()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  await expect(page.getByText('Starting quarterback', { exact: true })).toBeVisible()
  for (const route of pending) {
    const resource = Object.values(resources).find(resource => resource.path === new URL(route.request().url()).pathname)!
    await route.fulfill({ json: resource.json })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
  await expect(page.getByText('2023 Season', { exact: true })).toHaveCount(0)
})

for (const [name, resource] of Object.entries(resources)) {
  test(`failed background ${name} refresh keeps the cached section and retry recovers`, async ({ page }) => {
    await page.clock.install()
    await mockTeamSections(page)
    let fail = false
    await page.route(url => url.pathname === resource.path && url.searchParams.get('season') === '2023', route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Unavailable.' } } : { json: resource.json }))
    await page.goto('/teams/BUF')
    await loadedSections(page)
    if (name === 'roster') {
      await openRoster(page)
      await expect(page.getByRole('link', { name: /Roster quarterback/ })).toBeVisible()
      await page.getByRole('button', { name: 'Close', exact: true }).click()
    }
    await page.clock.fastForward(301_000)
    await page.clock.resume()
    await page.getByRole('link', { name: 'Scores', exact: true }).click()
    await expect(page.getByRole('combobox', { name: 'Season', exact: true })).toBeVisible()
    fail = true
    await page.goBack()
    if (name === 'roster') await openRoster(page)
    await expect(page.getByRole('alert')).toContainText(`Could not refresh ${resource.label}. Showing the last successful result.`)
    if (name === 'roster') await expect(page.getByRole('link', { name: /Roster quarterback/ })).toBeVisible()
    else await loadedSections(page)
    fail = false
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
}

for (const [name, resource] of Object.entries(resources).filter(([name]) => name !== 'profile')) {
  test(`cached empty ${name} results still warn when refresh fails`, async ({ page }) => {
    await page.clock.install()
    await mockTeam(page)
    let fail = false
    const empty = name === 'analytics' ? { season: 2023, league: [] } : []
    await page.route(url => url.pathname === resource.path, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Unavailable.' } } : { json: empty }))
    await page.goto('/teams/BUF')
    await expect(page.getByText('No starting lineup is available for this season.')).toBeVisible()
    await expect(page.getByText('Analytics unavailable for this season.')).toBeVisible()
    await expect(page.getByText('No injury report is available for this season.')).toBeVisible()
    await expect(page.getByText('No situational splits are available for this season.')).toBeVisible()
    if (name === 'roster') {
      await openRoster(page)
      await expect(page.getByText('No roster data available for this season.')).toBeVisible()
      await page.getByRole('button', { name: 'Close', exact: true }).click()
    }
    await page.clock.fastForward(301_000)
    await page.clock.resume()
    await page.getByRole('link', { name: 'Scores', exact: true }).click()
    await expect(page.getByRole('combobox', { name: 'Season', exact: true })).toBeVisible()
    fail = true
    await page.goBack()
    if (name === 'roster') await openRoster(page)
    await expect(page.getByRole('alert')).toContainText(`Could not refresh ${resource.label}. Showing the last successful result.`)
  })
}
