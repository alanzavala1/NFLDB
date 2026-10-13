import { expect } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockProfile, playerGame, playerProfile, comparable } from './fixtures/playerProfile'
import { passer } from './fixtures/players'

const career = {
  ...playerProfile, games_played: 3, awards: [{ season: 2023, award: 'MVP', team: 'BUF', position: 'QB' }],
  games: [...playerProfile.games, { ...playerGame, season: 2022, team: 'KC', game_id: '2022_01_KC_MIA', pass_yards: 200 }],
}

for (const mobile of [false, true]) {
  test(`${mobile ? 'mobile' : 'desktop'} multi-season profile preserves totals, awards, trajectory and team splits`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await mockProfile(page, career, [comparable])
    await page.goto('/players/test-player')
    await expect(page.getByText('No similar players are available.')).toHaveCount(0)
    await expect(page.getByRole('link', { name: /Second quarterback/ })).toBeVisible()
    await expect(page.getByText('★ MVP 2023')).toBeVisible()
    await expect(page.getByText('Career Trajectory', { exact: false })).toBeVisible()
    await expect(page.getByText('Career by Team', { exact: true })).toBeVisible()
    const regular = page.locator('section').filter({ has: page.getByText('Regular Season', { exact: true }) })
    await expect(regular.getByRole('cell', { name: '450', exact: true })).toBeVisible()
    // Postseason yardage stays out of regular-season career totals.
    await expect(regular.getByRole('cell', { name: '750', exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`player-${mobile ? 'mobile' : 'desktop'}.png`), fullPage: true })
  })
}

test('older game logs expand independently while the latest starts open', async ({ page }) => {
  await mockProfile(page, career)
  await page.goto('/players/test-player')
  await expect(page.locator('a[href="/games/2023_01_BUF_MIA"]')).toBeVisible()
  await expect(page.locator('a[href="/games/2022_01_KC_MIA"]')).toHaveCount(0)
  await page.getByRole('button', { name: /2022 KC/ }).click()
  await expect(page.locator('a[href="/games/2022_01_KC_MIA"]')).toBeVisible()
  await page.getByRole('button', { name: /2023 BUF/ }).click()
  await expect(page.locator('a[href="/games/2023_01_BUF_MIA"]')).toHaveCount(0)
  await expect(page.locator('a[href="/games/2022_01_KC_MIA"]')).toBeVisible()
})

test('punter columns and highlights use the generated punting fields', async ({ page }) => {
  await mockProfile(page, {
    ...playerProfile, position: 'P', games: [{ ...playerGame, position: 'P', attempts: 0, completions: 0, pass_yards: 0, pass_tds: 0, carries: 0, punts: 4, punt_yards: 180 }],
  })
  await page.route('**/api/leaders?*', route => route.fulfill({ json: [{ ...passer, player_id: 'test-player', position: 'P', attempts: 0, punts: 4 }] }))
  await page.goto('/players/test-player')
  const regular = page.locator('section').filter({ has: page.getByText('Regular Season', { exact: true }) })
  await expect(regular.getByRole('columnheader', { name: 'PUNTS', exact: true })).toBeVisible()
  await expect(regular.getByRole('cell', { name: '45.0', exact: true }).first()).toBeVisible()
  await expect(page.getByText('45.0 yds', { exact: true })).toBeVisible()
  await expect(page.getByText('1st in NFL · 2023', { exact: true })).toBeVisible()
})

test('game-log links preserve the player and originating-game route state', async ({ page }) => {
  const fromGame = { gameId: 'origin-game', season: 2023, week: 1, awayTeam: 'BUF', homeTeam: 'MIA', fromWeek: 1 }
  await page.addInitScript(origin => { history.replaceState({ ...history.state, usr: { fromGame: origin } }, '') }, fromGame)
  await mockProfile(page)
  await page.goto('/players/test-player')
  await page.locator('a[href="/games/2023_01_BUF_MIA"]').click()
  await expect(page).toHaveURL(/\/games\/2023_01_BUF_MIA$/)
  expect(await page.evaluate(() => history.state.usr)).toEqual({ fromPlayer: { playerId: 'test-player', playerName: 'Test quarterback', fromGame } })
})
