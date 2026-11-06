import { expect, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockTeam, teamProfile } from './fixtures/teamProfile'

test('defaults to the newest published year instead of guessing recent calendar years', async ({ page }) => {
  await page.clock.install()
  await mockTeam(page, [
    { season: 2026, status: 'scheduled' }, { season: 2025, status: 'available' },
    { season: 2024, status: 'loading' }, { season: 2023, status: 'queued' },
    { season: 2022, status: 'error' }, { season: 2004, status: 'loaded' }, { season: 2010, status: 'loaded' },
  ])
  let metadataReads = 0
  const profileYears: number[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname === '/api/seasons') metadataReads++
    if (url.pathname === '/api/teams/BUF') profileYears.push(Number(url.searchParams.get('season')))
  })
  await page.goto('/teams/BUF')
  await expect(page.getByText('2010 Season', { exact: true })).toBeVisible()
  await expect(page.getByText('2 seasons loaded', { exact: false })).toBeVisible()
  const initialMetadata = metadataReads
  const initialProfiles = profileYears.length
  await page.clock.fastForward(20_000)
  expect(metadataReads).toBe(initialMetadata)
  expect(profileYears.length).toBe(initialProfiles)
  expect([...new Set(profileYears)].sort()).toEqual([2004, 2010])
  await expect(page.getByText(/Loading season data/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^202[2-6]/ })).toHaveCount(0)
})

for (const status of ['available', 'queued', 'loading', 'error', 'scheduled'] as const) {
  test(`only ${status} seasons ends loading without team requests or preparation`, async ({ page }) => {
    await mockTeam(page, [{ season: 2026, status }])
    const reads: string[] = []
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/teams/')) reads.push(request.url()) })
    await page.goto('/teams/BUF')
    await expect(page.getByText('No published season statistics are available for this team.')).toBeVisible()
    await expect(page.getByRole('status')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /Show \d{4}/ })).toHaveCount(0)
    expect(reads).toEqual([])
  })
}

test('older-season controls read only metadata-confirmed years and preserve game links', async ({ page }) => {
  const years = [2023, 2021, 2019, 2010, 2005, 2001, 1999]
  await mockTeam(page, years.map(season => ({ season, status: 'loaded' })))
  const fetched: number[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname === '/api/teams/BUF') fetched.push(Number(url.searchParams.get('season')))
  })
  await page.goto('/teams/BUF')
  await expect(page.getByText('5 seasons loaded', { exact: false })).toBeVisible()
  expect([...new Set(fetched)].sort()).toEqual(years.slice(0, 5).sort())
  await page.getByRole('button', { name: 'Show 2001', exact: true }).click()
  await expect(page.getByText('6 seasons loaded', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: /^2001/ }).click()
  await expect(page.getByText('2001 Season', { exact: true })).toBeVisible()
  await expect(page.locator('a[href^="/games/2001_01_BUF_MIA"]')).toBeVisible()
  await page.getByRole('button', { name: 'Show 1999', exact: true }).click()
  await expect(page.getByText('7 seasons loaded', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: /Show \d{4}/ })).toHaveCount(0)
  expect([...new Set(fetched)].sort()).toEqual([...years].sort())
})

test('season metadata failure is visible and retry recovers', async ({ page }) => {
  await mockTeam(page)
  let fail = true
  await page.route('**/api/seasons', route => route.fulfill(fail
    ? { status: 503, json: { detail: 'Season list is temporarily unavailable.' } }
    : { json: [{ season: 2023, status: 'loaded' }] }))
  await page.goto('/teams/BUF')
  await expect(page.getByRole('alert')).toContainText('Season list is temporarily unavailable.')
  fail = false
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
})

test('a failed latest profile does not show an older year in its place', async ({ page }) => {
  await mockTeam(page, [{ season: 2023, status: 'loaded' }, { season: 2022, status: 'loaded' }])
  let fail = true
  await page.route(url => url.pathname === '/api/teams/BUF' && url.searchParams.get('season') === '2023', route => route.fulfill(fail
    ? { status: 503, json: { detail: 'Unavailable.' } } : { json: teamProfile }))
  await page.goto('/teams/BUF')
  await expect(page.getByRole('alert')).toContainText('Could not load 2023 team profile.')
  await expect(page.getByText('2022 Season', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: /^2022/ }).click()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /^2023/ }).click()
  fail = false
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('a pending selected profile stays loading while another year remains usable', async ({ page }) => {
  await mockTeam(page, [{ season: 2023, status: 'loaded' }, { season: 2022, status: 'loaded' }])
  const pending: Route[] = []
  await page.route(url => url.pathname === '/api/teams/BUF' && url.searchParams.get('season') === '2023', route => { pending.push(route) })
  await page.goto('/teams/BUF')
  await expect(page.getByRole('status')).toHaveText('Loading team profile…')
  await page.getByRole('button', { name: /^2022/ }).click()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /^2023/ }).click()
  await expect(page.getByRole('status')).toHaveText('Loading team profile…')
  for (const route of pending) await route.fulfill({ json: teamProfile })
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
})

test('an empty published profile renders without fake historical loading', async ({ page }) => {
  await mockTeam(page)
  await page.route('**/api/teams/BUF?*', route => route.fulfill({ json: { ...teamProfile, games: [] } }))
  await page.goto('/teams/BUF')
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  await expect(page.getByText('0 games · 0-0', { exact: true })).toBeVisible()
  await expect(page.getByText(/Loading season data/)).toHaveCount(0)
})

test('mobile season selection and roster/stat controls stay usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockTeam(page, [{ season: 2023, status: 'loaded' }, { season: 2022, status: 'loaded' }])
  await page.goto('/teams/BUF')
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /^2022/ }).click()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Roster', exact: true }).click()
  await expect(page.getByText('No roster data available for this season.')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Full Stats', exact: true }).click()
  await expect(page.getByText('2022 Stats', { exact: true })).toBeVisible()
  await expect(page.getByText('Regular Season', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('an empty season list is an empty state instead of a loading loop', async ({ page }) => {
  const reads = await mockTeam(page, [])
  await page.goto('/teams/BUF')
  await expect(page.getByText('No published season statistics are available for this team.')).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  expect(reads.filter(path => path.startsWith('/api/teams/'))).toEqual([])
})
