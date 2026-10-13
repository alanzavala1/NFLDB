import { expect, type Page } from '@playwright/test'
import type { TeamLeader } from '../src/types'
import { test } from './fixtures/scores'
import { mockTeamSections, teamGame, teamProfile } from './fixtures/teamProfile'
import { passer } from './fixtures/players'

const alpha: TeamLeader = {
  ...passer, player_id: 'alpha', player_name: 'Alpha player', jersey_number: 17,
  games_played: 10, attempts: 500, completions: 400, pass_yards: 5000, pass_tds: 30,
  pass_epa: 5, rush_epa: 3, rec_epa: 2, carries: 100, rush_yards: 1000, rush_tds: 5,
  targets: 50, receptions: 30, rec_yards: 300, rec_tds: 2, air_yards: 400, yac: 100,
  solo_tackles: 10, assist_tackles: 5,
}
const beta: TeamLeader = {
  ...alpha, player_id: 'beta', player_name: 'Beta player', attempts: 100, completions: 50,
  pass_yards: 900, pass_epa: -1, rush_yards: 2000, rec_yards: 500, solo_tackles: 30, assist_tackles: 10,
}
const twin: TeamLeader = {
  ...alpha, player_id: 'twin', player_name: 'Tied player', attempts: 600, completions: 300,
  pass_epa: 6, rush_yards: 300, solo_tackles: 5,
}

async function openStats(page: Page, players: TeamLeader[] = [alpha, beta, twin]) {
  await mockTeamSections(page)
  await page.route(url => url.pathname === '/api/teams/BUF' && url.searchParams.get('season') === '2023', route => route.fulfill({ json: {
    ...teamProfile, leaders: players,
    playoff_leaders: players.map(player => ({ ...player, player_name: `Post ${player.player_name}` })),
    games: [teamGame, { ...teamGame, game_id: '2023_19_BUF_KC', week: 19, game_type: 'WC', home_team: 'KC' }],
  } }))
  await page.goto('/teams/BUF')
  await page.getByRole('button', { name: 'Full Stats', exact: true }).click()
  await expect(page.getByText('2023 Stats', { exact: true })).toBeVisible()
}

function tableFor(page: Page, title: string, postseason = false) {
  return page.getByRole('table', { name: `${title} statistics`, exact: true }).nth(postseason ? 1 : 0)
}

for (const mobile of [false, true]) {
  test(`${mobile ? 'mobile' : 'desktop'} full-stats layout preserves grouped columns, totals and player links`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await openStats(page)
    await expect(page.getByRole('link', { name: 'Tied player', exact: true }).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`team-stats-${mobile ? 'mobile' : 'desktop'}.png`), animations: 'disabled' })
  })
}

test('numeric sorting, ratios and signed ties use raw values and keyboard controls stay two-way', async ({ page }) => {
  await openStats(page)
  const table = tableFor(page, 'Passing')
  const names = table.locator('tbody').getByRole('link')
  await expect(names).toHaveText(['Alpha player', 'Tied player', 'Beta player'])
  await expect(table.getByRole('cell', { name: '5,000', exact: true })).toHaveCount(2)
  const yards = table.getByRole('columnheader', { name: 'YDS', exact: true })
  await expect(yards).toHaveAttribute('aria-sort', 'descending')
  await yards.getByRole('button').focus()
  await page.keyboard.press('Enter')
  await expect(yards).toHaveAttribute('aria-sort', 'ascending')
  await expect(names).toHaveText(['Beta player', 'Alpha player', 'Tied player'])
  await page.keyboard.press('Space')
  await expect(yards).toHaveAttribute('aria-sort', 'descending')
  await expect(names).toHaveText(['Alpha player', 'Tied player', 'Beta player'])
  await table.getByRole('button', { name: 'Y/A', exact: true }).click()
  await expect(names).toHaveText(['Alpha player', 'Beta player', 'Tied player'])
  await table.getByRole('button', { name: 'EPA/Att', exact: true }).click({ modifiers: ['Shift'] })
  await expect(names).toHaveText(['Alpha player', 'Tied player', 'Beta player'])
  await expect(table.locator('th[aria-sort="descending"]')).toHaveCount(1)
  await expect(yards).toHaveAttribute('aria-sort', 'none')
  await expect(table.getByRole('cell', { name: '-0.010', exact: true })).toHaveClass(/text-data-loss/)
})

test('each section and regular/postseason group keep independent sorting state', async ({ page }) => {
  await openStats(page)
  const passing = tableFor(page, 'Passing')
  const rushing = tableFor(page, 'Rushing')
  const postPassing = tableFor(page, 'Passing', true)
  await passing.getByRole('button', { name: 'YDS', exact: true }).click()
  await expect(passing.locator('tbody').getByRole('link').first()).toHaveText('Beta player')
  await expect(postPassing.locator('tbody').getByRole('link').first()).toHaveText('Post Alpha player')
  await rushing.getByRole('button', { name: 'YDS', exact: true }).click()
  await expect(rushing.locator('tbody').getByRole('link').first()).toHaveText('Tied player')
  await expect(passing.locator('tbody').getByRole('link').first()).toHaveText('Beta player')
  await postPassing.getByRole('button', { name: 'Y/A', exact: true }).click()
  await expect(postPassing.locator('tbody').getByRole('link').first()).toHaveText('Post Alpha player')
  await expect(passing.getByRole('columnheader', { name: 'YDS', exact: true })).toHaveAttribute('aria-sort', 'ascending')
  await expect(postPassing.getByRole('columnheader', { name: 'Y/A', exact: true })).toHaveAttribute('aria-sort', 'descending')
})

test('show-more limits follow sorting while totals include every qualified player', async ({ page }) => {
  const players = Array.from({ length: 16 }, (_, index) => ({
    ...alpha, player_id: `player-${index + 1}`, player_name: `Player ${String(index + 1).padStart(2, '0')}`,
    attempts: 0, completions: 0, pass_yards: 0, pass_epa: 0, targets: 0, receptions: 0, rec_yards: 0,
    carries: 1, rush_yards: index + 1, solo_tackles: index + 1, assist_tackles: 0,
  }))
  await openStats(page, players)
  const scrimmage = tableFor(page, 'Scrimmage')
  const defense = tableFor(page, 'Defense')
  await expect(scrimmage.locator('tbody').getByRole('link')).toHaveCount(10)
  await expect(defense.locator('tbody').getByRole('link')).toHaveCount(15)
  await expect(scrimmage.locator('tbody').getByRole('link').first()).toHaveText('Player 16')
  await expect(scrimmage.locator('tfoot').getByRole('cell', { name: '136', exact: true }).first()).toBeVisible()
  await scrimmage.getByRole('button', { name: /6 more/ }).click()
  await expect(scrimmage.locator('tbody').getByRole('link')).toHaveCount(16)
  await scrimmage.getByRole('button', { name: 'SCRIM', exact: true }).click()
  await expect(scrimmage.locator('tbody').getByRole('link').first()).toHaveText('Player 01')
  await scrimmage.getByRole('button', { name: /show less/ }).click()
  await expect(scrimmage.locator('tbody').getByRole('link')).toHaveCount(10)
  await expect(scrimmage.locator('tbody').getByRole('link').first()).toHaveText('Player 01')
  await expect(scrimmage.locator('tfoot').getByRole('cell', { name: '136', exact: true }).first()).toBeVisible()
  await defense.getByRole('button', { name: /1 more/ }).click()
  await expect(defense.locator('tbody').getByRole('link')).toHaveCount(16)
})
