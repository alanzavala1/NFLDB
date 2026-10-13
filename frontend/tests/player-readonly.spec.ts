import { expect, type Page } from '@playwright/test'
import type { PlayerProfile } from '../src/types'
import { test, mockApi } from './fixtures/scores'
import { playerGame, playerProfile } from './fixtures/playerProfile'

async function mockProfile(page: Page, profile: PlayerProfile = playerProfile) {
  await mockApi(page, [
    { season: 2026, status: 'loading' }, { season: 2025, status: 'available' },
    { season: 2024, status: 'loaded' }, { season: 2023, status: 'loaded' },
  ])
  await page.route('**/api/leaders?*', route => route.fulfill({ json: [] }))
  await page.route('**/api/players/*', route => route.fulfill({ json: profile }))
  await page.route('**/api/players/*/comparables', route => route.fulfill({ json: [] }))
}

test('opening a partial career reads the profile without seasonal preparation or polling', async ({ page }) => {
  await page.clock.install()
  await mockProfile(page)
  let seasonRequests = 0
  const profileReads: string[] = []
  page.on('request', request => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/seasons')) seasonRequests++
    if (path === '/api/players/test-player') profileReads.push(request.url())
  })
  await page.goto('/players/test-player')
  await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
  await expect(page.getByText('Regular Season', { exact: true })).toBeVisible()
  const initialReads = profileReads.length
  await page.clock.fastForward(20_000)
  expect(seasonRequests).toBe(0)
  expect(profileReads.length).toBe(initialReads)
  await expect(page.getByText('Loading historical seasons — stats will update automatically.')).toHaveCount(0)
})

test('a retired player is not repeatedly refetched for seasons they did not play', async ({ page }) => {
  await page.clock.install()
  await mockProfile(page, {
    ...playerProfile, entry_year: 2000, rookie_year: 2000,
    games: [{ ...playerGame, season: 2008, game_id: '2008_01_BUF_MIA' }],
  })
  let reads = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/players/test-player') reads++ })
  await page.goto('/players/test-player')
  await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
  const initialReads = reads
  await page.clock.fastForward(20_000)
  expect(reads).toBe(initialReads)
  await expect(page.getByText('Since 2000')).toBeVisible()
})

test('a known player without game statistics keeps their biography and ends loading', async ({ page }) => {
  await mockProfile(page, { ...playerProfile, games: [], games_played: 0 })
  await page.goto('/players/test-player')
  await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('No game statistics are available for this player yet.')
  await expect(page.getByText('Test college')).toBeVisible()
  await expect(page.getByText('Loading historical seasons — stats will update automatically.')).toHaveCount(0)
})

test('profile request failure is distinct from missing data and retry recovers', async ({ page }) => {
  await mockProfile(page)
  let fail = true
  await page.route('**/api/players/test-player', route => route.fulfill(fail
    ? { status: 503, json: { detail: 'Unavailable' } }
    : { json: playerProfile }))
  await page.goto('/players/test-player')
  await expect(page.getByRole('alert')).toContainText('Could not load player profile.')
  await expect(page.getByText('Player not found.')).toHaveCount(0)
  fail = false
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('available regular/postseason records and game links remain separate', async ({ page }) => {
  await mockProfile(page)
  await page.goto('/players/test-player')
  await expect(page.getByText('Postseason · 1 game', { exact: true })).toBeVisible()
  const regular = page.locator('section').filter({ has: page.getByText('Regular Season', { exact: true }) })
  const postseason = page.locator('section').filter({ has: page.getByText('Postseason · 1 game', { exact: true }) })
  await expect(regular.getByRole('cell', { name: '250', exact: true })).toBeVisible()
  await expect(postseason.getByRole('cell', { name: '300', exact: true })).toBeVisible()
  await expect(page.locator('a[href^="/games/2023_01_BUF_MIA"]').first()).toBeVisible()
  await expect(page.locator('a[href^="/games/2023_19_BUF_MIA"]').first()).toBeVisible()
})
