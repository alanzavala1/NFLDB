import { expect, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { comparable, mockProfile, playerProfile } from './fixtures/playerProfile'
import { passer } from './fixtures/players'

test('similar-player loading is independent and an empty result is explicit', async ({ page }) => {
  await mockProfile(page)
  const pending: Route[] = []
  await page.route('**/api/players/test-player/comparables', route => { pending.push(route) })
  await page.goto('/players/test-player')
  await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('Loading similar players…')
  for (const route of pending) await route.fulfill({ json: [] })
  await expect(page.getByText('No similar players are available.')).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
})

for (const resource of ['profile', 'comparables', 'leaders'] as const) {
  test(`${resource} backend error detail is visible and retry recovers independently`, async ({ page }) => {
    await mockProfile(page, playerProfile, [comparable])
    let fail = true
    const pattern = resource === 'profile' ? '**/api/players/test-player'
      : resource === 'comparables' ? '**/api/players/test-player/comparables' : '**/api/leaders?*'
    await page.route(pattern, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Published statistics are temporarily unavailable.' } }
      : { json: resource === 'profile' ? playerProfile : resource === 'comparables' ? [comparable] : [] }))
    await page.goto('/players/test-player')
    await expect(page.getByRole('alert')).toContainText('Published statistics are temporarily unavailable.')
    if (resource !== 'profile') {
      await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
      await expect(page.getByText('Regular Season', { exact: true })).toBeVisible()
    }
    if (resource === 'leaders') await expect(page.getByRole('link', { name: /Second quarterback/ })).toBeVisible()
    fail = false
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByRole('link', { name: /Second quarterback/ })).toBeVisible()
  })
}

test('non-JSON profile errors use the shared readable fallback', async ({ page }) => {
  await mockProfile(page)
  await page.route('**/api/players/test-player', route => route.fulfill({ status: 502, contentType: 'text/html', body: '<h1>Bad gateway</h1>' }))
  await page.goto('/players/test-player')
  await expect(page.getByRole('alert')).toContainText('Request failed (502). Please try again.')
})

test('player identities have separate caches and fresh profile/comparables are reused on return', async ({ page }) => {
  await mockProfile(page, playerProfile, [comparable])
  await page.route('**/api/players/other-player', route => route.fulfill({ json: { ...playerProfile, player_id: 'other-player', player_name: 'Second quarterback' } }))
  await page.route('**/api/players/other-player/comparables', route => route.fulfill({ json: [{ ...comparable, player_id: 'test-player', player_name: 'Test quarterback' }] }))
  const reads: string[] = []
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/players/')) reads.push(request.url())
  })
  await page.goto('/players/test-player')
  await page.getByRole('link', { name: /Second quarterback/ }).click()
  await expect(page.getByText('Second quarterback', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /Test quarterback/ })).toBeVisible()
  const initialReads = reads.length
  await page.getByRole('link', { name: /Test quarterback/ }).click()
  await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /Second quarterback/ })).toBeVisible()
  expect(reads.length).toBe(initialReads)
})

for (const resource of ['profile', 'comparables', 'leaders'] as const) {
  test(`leaving the profile cancels pending ${resource} requests`, async ({ page }) => {
    await mockProfile(page)
    const pending: Route[] = []
    const pattern = resource === 'profile' ? '**/api/players/test-player'
      : resource === 'comparables' ? '**/api/players/test-player/comparables' : '**/api/leaders?season=2023'
    await page.route(pattern, route => { pending.push(route) })
    await page.goto('/players/test-player')
    await expect.poll(() => pending.length).toBeGreaterThan(0)
    await page.getByRole('link', { name: 'Scores', exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('combobox', { name: 'Season', exact: true })).toBeVisible()
    for (const route of pending) {
      await route.fulfill({ json: resource === 'profile' ? { ...playerProfile, player_name: 'Late quarterback' } : [] })
      await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
    }
    await expect(page.getByText('Late quarterback')).toHaveCount(0)
  })
}

for (const resource of ['profile', 'comparables', 'empty comparables', 'leaders'] as const) {
  test(`failed background ${resource} refresh retains the cached result`, async ({ page }) => {
    await page.clock.install()
    const comps = resource === 'empty comparables' ? [] : [comparable]
    const leaders = [{ ...passer, player_id: 'test-player' }]
    await mockProfile(page, playerProfile, comps)
    await page.route('**/api/leaders?*', route => route.fulfill({ json: leaders }))
    let fail = false
    const pattern = resource === 'profile' ? '**/api/players/test-player'
      : resource === 'leaders' ? '**/api/leaders?*' : '**/api/players/test-player/comparables'
    await page.route(pattern, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Unavailable.' } }
      : { json: resource === 'profile' ? playerProfile : resource === 'leaders' ? leaders : comps }))
    await page.goto('/players/test-player')
    await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
    if (comps.length) await expect(page.getByRole('link', { name: /Second quarterback/ })).toBeVisible()
    else await expect(page.getByText('No similar players are available.')).toBeVisible()
    await expect(page.getByText('1st in NFL · 2023', { exact: true }).first()).toBeVisible()
    await page.clock.fastForward(301_000)
    await page.clock.resume()
    await page.getByRole('link', { name: 'Scores', exact: true }).click()
    await expect(page.getByRole('combobox', { name: 'Season', exact: true })).toBeVisible()
    fail = true
    await page.goBack()
    await expect(page.getByRole('alert')).toContainText('Showing the last successful result.')
    await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
    if (comps.length) await expect(page.getByRole('link', { name: /Second quarterback/ })).toBeVisible()
    if (resource === 'leaders') await expect(page.getByText('1st in NFL · 2023', { exact: true }).first()).toBeVisible()
    fail = false
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    if (!comps.length) await expect(page.getByText('No similar players are available.')).toBeVisible()
  })
}

test('Splits and the profile page share fresh player records', async ({ page }) => {
  await mockProfile(page)
  await page.route('**/api/players/test-player/splits', route => route.fulfill({ json: [] }))
  await page.route('**/api/search?*', route => route.fulfill({ json: [{ type: 'player', id: 'test-player', name: 'Test quarterback', position: 'QB', team: 'BUF', headshot_url: null }] }))
  let profileReads = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/players/test-player') profileReads++ })
  await page.goto('/splits?p=test-player&cat=passing')
  await expect(page.getByText('Test quarterback', { exact: true }).first()).toBeVisible()
  const initialReads = profileReads
  await page.getByRole('button', { name: /Search Ctrl K/ }).click()
  await page.getByPlaceholder('Search players or teams...').fill('Test quarterback')
  await page.getByRole('button', { name: /Test quarterback/ }).click()
  await expect(page).toHaveURL(/\/players\/test-player$/)
  await expect(page.getByText('Regular Season', { exact: true })).toBeVisible()
  await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
  expect(profileReads).toBe(initialReads)
})
