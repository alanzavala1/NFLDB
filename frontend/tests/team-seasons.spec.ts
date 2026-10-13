import { expect, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockTeam } from './fixtures/teamProfile'

const years = [2023, 2021, 2019, 2010, 2005, 2001, 1999]
const published = years.map(season => ({ season, status: 'loaded' as const }))

test('an old-year bookmark opens that season, reveals its sidebar entry, and survives reload', async ({ page }) => {
  await mockTeam(page, published)
  const reads: number[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname === '/api/teams/BUF') reads.push(Number(url.searchParams.get('season')))
  })
  await page.goto('/teams/BUF?season=1999&campaign=phone')
  await expect(page.getByText('1999 Season', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /^1999/ })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('a[href^="/games/1999_01_BUF_MIA"]')).toBeVisible()
  await expect(page.getByText('6 seasons loaded', { exact: false })).toBeVisible()
  expect([...new Set(reads)].sort()).toEqual([...years.slice(0, 5), 1999].sort())
  await expect(page.getByRole('button', { name: 'Show 2001', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('1999 Season', { exact: true })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('campaign')).toBe('phone')
})

test('choosing a year updates only the season URL parameter', async ({ page }) => {
  await mockTeam(page, [{ season: 2023, status: 'loaded' }, { season: 2022, status: 'loaded' }])
  await page.goto('/teams/BUF?season=2023&campaign=phone&panel=stats')
  await page.getByRole('button', { name: /^2022/ }).click()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  expect(Object.fromEntries(new URL(page.url()).searchParams)).toEqual({ season: '2022', campaign: 'phone', panel: 'stats' })
  await expect(page.getByRole('button', { name: /^2022/ })).toHaveAttribute('aria-pressed', 'true')
})

test('bare links default to the latest publication and back/forward restores season choices from the cache', async ({ page }) => {
  await mockTeam(page, [{ season: 2023, status: 'loaded' }, { season: 2022, status: 'loaded' }])
  let profileReads = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/teams/BUF') profileReads++ })
  await page.goto('/teams/BUF?campaign=phone')
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  await expect(page.getByText('2 seasons loaded', { exact: false })).toBeVisible()
  expect(new URL(page.url()).searchParams.has('season')).toBe(false)
  const initialReads = profileReads
  await page.getByRole('button', { name: /^2022/ }).click()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /^2023/ }).click()
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  // Re-selecting the same year does not add a duplicate history entry.
  await page.getByRole('button', { name: /^2023/ }).click()
  await page.goBack()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  expect(new URL(page.url()).searchParams.has('season')).toBe(false)
  await page.goForward()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  await page.goForward()
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  expect(profileReads).toBe(initialReads)
})

for (const requested of ['banana', '', '2023.5', ' 2023 ', '2027']) {
  test(`invalid or unknown year '${requested}' never requests a substitute season`, async ({ page }) => {
    await mockTeam(page, published)
    const reads: string[] = []
    page.on('request', request => {
      if (new URL(request.url()).pathname.startsWith('/api/teams/') || new URL(request.url()).pathname === '/api/team-analytics') reads.push(request.url())
    })
    await page.goto(`/teams/BUF?season=${encodeURIComponent(requested)}`)
    await expect(page.getByRole('alert')).toContainText('That season is unavailable.')
    await expect(page.getByText('2023 Season', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { pressed: true })).toHaveCount(0)
    expect(reads).toEqual([])
    await page.getByRole('button', { name: /^2023/ }).click()
    await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
    expect(new URL(page.url()).searchParams.get('season')).toBe('2023')
  })
}

for (const status of ['available', 'loading', 'queued', 'error', 'scheduled'] as const) {
  test(`an explicit ${status} season stays unavailable until a published year is chosen`, async ({ page }) => {
    await mockTeam(page, [{ season: 2026, status }, { season: 2023, status: 'loaded' }])
    const reads: string[] = []
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/teams/')) reads.push(request.url()) })
    await page.goto('/teams/BUF?season=2026')
    await expect(page.getByRole('alert')).toContainText('That season is unavailable.')
    expect(reads).toEqual([])
    await expect(page.getByText('2023 Season', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^2026/ })).toHaveCount(0)
  })
}

test('bookmarked seasons wait for metadata and preserve the URL through a failed metadata request', async ({ page }) => {
  await mockTeam(page, published)
  const pending: Route[] = []
  const reads: string[] = []
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/teams/')) reads.push(request.url()) })
  await page.route('**/api/seasons', route => { pending.push(route) })
  await page.goto('/teams/BUF?season=1999&campaign=phone')
  await expect(page.getByRole('status')).toHaveText('Loading available seasons…')
  expect(reads).toEqual([])
  // Replace the holding route so Query's automatic retry receives the same failure.
  await page.route('**/api/seasons', route => route.fulfill({ status: 503, json: { detail: 'Season metadata unavailable.' } }))
  for (const route of pending) await route.fulfill({ status: 503, json: { detail: 'Season metadata unavailable.' } })
  await expect(page.getByRole('alert')).toContainText('Season metadata unavailable.')
  expect(reads).toEqual([])
  expect(new URL(page.url()).searchParams.get('season')).toBe('1999')
  await page.route('**/api/seasons', route => route.fulfill({ json: published }))
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByText('1999 Season', { exact: true })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('campaign')).toBe('phone')
})
