import { expect } from '@playwright/test'
import type { TeamLeader } from '../src/types'
import { test } from './fixtures/scores'
import { mockTeamSections, teamGame, teamProfile } from './fixtures/teamProfile'
import { passer } from './fixtures/players'

const leader: TeamLeader = {
  ...passer, player_name: 'Season quarterback', jersey_number: 17, pass_epa: 3, rush_epa: 1, rec_epa: 0,
  air_yards: 0, yac: 0, carries: 25, rush_yards: 100, rush_tds: 1,
}
const profile = {
  ...teamProfile, leaders: [leader],
  playoff_leaders: [{ ...leader, player_name: 'Playoff quarterback', pass_yards: 300, rush_yards: 40 }],
  games: [teamGame, { ...teamGame, game_id: '2023_19_BUF_KC', week: 19, game_type: 'WC', home_team: 'KC', away_score: 20, home_score: 24 }],
}

async function mockLayout(page: Parameters<typeof mockTeamSections>[0]) {
  await mockTeamSections(page)
  await page.route(url => url.pathname === '/api/teams/BUF' && url.searchParams.get('season') === '2023', route => route.fulfill({ json: profile }))
}

for (const mobile of [false, true]) {
  test(`${mobile ? 'mobile' : 'desktop'} Team layout keeps season summary, supplemental panels, schedule and leaders`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await mockLayout(page)
    await page.goto('/teams/BUF')
    await expect(page.getByRole('heading', { name: 'Team Analytics', exact: true })).toBeVisible()
    await expect(page.getByText('Starting quarterback', { exact: true })).toBeVisible()
    await expect(page.getByText('Injured quarterback', { exact: true })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'Leading', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: /Wild Card/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /Season quarterback/ }).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`team-${mobile ? 'mobile' : 'desktop'}.png`), fullPage: true })
  })
}

test('regular/postseason tables use separate game counts and retain sorting', async ({ page }) => {
  await mockLayout(page)
  await page.route(url => url.pathname === '/api/teams/BUF' && url.searchParams.get('season') === '2023', route => route.fulfill({ json: {
    ...profile, leaders: [leader, { ...leader, player_id: 'backup', player_name: 'Backup quarterback', pass_yards: 100, carries: 0, rush_yards: 0 }],
  } }))
  await page.goto('/teams/BUF')
  await page.getByRole('button', { name: 'Full Stats', exact: true }).click()
  await expect(page.getByText('Regular Season', { exact: true })).toBeVisible()
  await expect(page.getByText('Postseason', { exact: true })).toBeVisible()
  // These summaries are grouped by regular/postseason; each has one completed game.
  const rushing = page.locator('div.mb-6').filter({ has: page.getByText('Rushing', { exact: true }) })
  await expect(rushing.nth(0).getByText('Y/G', { exact: true }).locator('..')).toContainText('100.0')
  await expect(rushing.nth(1).getByText('Y/G', { exact: true }).locator('..')).toContainText('40.0')
  await expect(page.getByRole('link', { name: /Season quarterback/ }).first()).toBeVisible()
  await expect(page.getByRole('link', { name: /Playoff quarterback/ }).first()).toBeVisible()
  const passing = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: /^C\/ATT/ }) }).first()
  await expect(passing.getByRole('link').first()).toContainText('Season quarterback')
  await passing.getByRole('columnheader', { name: /^YDS/ }).first().click()
  await expect(passing.getByRole('link').first()).toContainText('Backup quarterback')
  await page.keyboard.press('Escape')
  await expect(page.getByText('2023 Stats', { exact: true })).toHaveCount(0)
})

test('the point differential tooltip retains score and signed margin', async ({ page }) => {
  await mockLayout(page)
  await page.goto('/teams/BUF')
  await page.locator('.recharts-bar-rectangle').first().hover()
  await expect(page.locator('.recharts-tooltip-wrapper')).toContainText('24–17  (+7)')
})

test('changing seasons resets open modals and supplemental split choices', async ({ page }) => {
  await mockLayout(page)
  await page.goto('/teams/BUF')
  await expect(page.getByRole('cell', { name: 'Leading', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'defense', exact: true }).click()
  await expect(page.getByRole('cell', { name: 'Leading', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: /^2022/ }).click()
  await expect(page.getByText('2022 Season', { exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Leading', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Roster', exact: true }).click()
  await expect(page.getByText('2022 Roster', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /^2023/ }).click()
  await expect(page.getByText('2023 Season', { exact: true })).toBeVisible()
  await expect(page.getByText('2022 Roster', { exact: true })).toHaveCount(0)
})
