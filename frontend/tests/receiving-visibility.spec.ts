import { expect } from '@playwright/test'
import { test, mockApi } from './fixtures/scores'
import { passer } from './fixtures/players'
import { mockProfile, playerGame, playerProfile } from './fixtures/playerProfile'
import { mockTeamSections, teamProfile } from './fixtures/teamProfile'
import { mockGame, gameDetail, gamePlayer, playerChart } from './fixtures/gameDetail'
import { layoutGame, layoutLineup } from './fixtures/gameLayout'
import { hasReceivingActivity, hasReceivingProduction } from '../src/utils/receiving'
import { STAT_TABS, POS_TABS } from '../src/features/leaders/columns'
import { computeHighlightRanks } from '../src/features/players/rankings'
import { detectPos, sumGames } from '../src/features/players/stats'

const receiver = {
  ...passer, player_id: 'zero-target', player_name: 'Recorded receiver', position: 'WR',
  attempts: 0, completions: 0, pass_yards: 0, pass_tds: 0,
  targets: 0, receptions: 4, rec_yards: 52, rec_tds: 1,
}
const lateral = { ...receiver, player_id: 'lateral', player_name: 'Lateral recipient', receptions: 0, rec_yards: 20 }
const negative = { ...receiver, player_id: 'negative', player_name: 'Negative yardage', receptions: 0, rec_yards: -3, rec_tds: 0 }
const inactive = { ...receiver, player_id: 'inactive', player_name: 'No receiving activity', receptions: 0, rec_yards: 0, rec_tds: 0 }

test('receiving production qualifies without target counts, including zero-catch and signed plays', () => {
  for (const stats of [receiver, lateral, negative, { ...inactive, rec_tds: 1 }]) {
    expect(hasReceivingProduction(stats)).toBe(true)
    expect(hasReceivingActivity(stats, 20)).toBe(true)
    expect(STAT_TABS.find(t => t.key === 'receiving')!.filter(stats)).toBe(true)
    expect(POS_TABS.find(t => t.key === 'wr')!.filter(stats)).toBe(true)
  }
  expect(hasReceivingActivity(inactive)).toBe(false)
  expect(hasReceivingActivity({ ...inactive, targets: null })).toBe(false)
  expect(hasReceivingActivity({ ...receiver, targets: null })).toBe(true)
  expect(hasReceivingProduction({ ...inactive, rec_yards: Number.NaN })).toBe(false)
  expect(hasReceivingActivity({ ...inactive, targets: 5 })).toBe(true)
  expect(hasReceivingActivity({ ...inactive, targets: 5 }, 20)).toBe(false)
  expect(hasReceivingActivity({ ...inactive, targets: 20 }, 20)).toBe(true)
})

test('receiving-yard ranks survive zero targets while target-rate qualification stays separate', () => {
  const ranks = computeHighlightRanks('WR', receiver.player_id, [receiver, lateral], 2004)
  expect(ranks['Rec Yards']).toBe('1st in NFL · 2004')
  expect(ranks['Catch %']).toBeNull()
  expect(ranks['Y / Target']).toBeNull()
})

test('production supplies receiving columns for an unknown position without overriding known positions', () => {
  const totals = sumGames([{ ...playerGame, attempts: 0, carries: 0, targets: 0, receptions: 4, rec_yards: 52 }])
  expect(detectPos(totals, null)).toBe('WR')
  expect(detectPos(totals, 'CB')).toBe('DEF')
  expect(detectPos({ ...totals, carries: 30 }, 'WR')).toBe('WR')
  expect(detectPos({ ...totals, carries: 30 }, 'TE')).toBe('WR')
})

test('historical receiving leaderboard and position view retain production and exclude inactive rows', async ({ page }) => {
  await mockApi(page, [{ season: 2004, status: 'loaded' }])
  await page.route('**/api/leaders?*', route => route.fulfill({ json: [receiver, lateral, negative, inactive] }))
  await page.goto('/leaders?season=2004&tab=receiving')
  const table = page.getByRole('table')
  await expect(table.locator('a[href^="/players/"]')).toHaveText(['Recorded receiver', 'Lateral recipient', 'Negative yardage'])
  await expect(table.getByRole('row').filter({ hasText: 'Lateral recipient' })).toContainText('20')
  await expect(table.getByRole('row').filter({ hasText: 'Negative yardage' })).toContainText('-3')
  await expect(page.getByRole('button', { name: /Receiving Leader/ })).toContainText('Recorded receiver')
  await page.goto('/leaders?season=2004&mode=positions&pos=wr')
  await expect(table.locator('a[href^="/players/"]')).toHaveText(['Recorded receiver', 'Lateral recipient', 'Negative yardage'])
})

test('running back career and game log retain catches, lateral yards and receiving touchdowns', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockProfile(page, {
    ...playerProfile, position: 'RB', games: [{
      ...playerGame, season: 2004, position: 'RB', attempts: 0, completions: 0, pass_yards: 0,
      targets: 0, receptions: 0, rec_yards: 20, rec_tds: 1,
    }],
  })
  await page.goto('/players/test-player')
  const log = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'REC TD', exact: true }) })
  const row = log.getByRole('row').filter({ has: page.getByRole('link', { name: 'vs MIA' }) })
  await expect(row).toBeVisible()
  const indexOf = async (label: string) => (await log.getByRole('columnheader').allTextContents()).indexOf(label)
  await expect(row.getByRole('cell').nth(await indexOf('REC'))).toHaveText('0')
  await expect(row.getByRole('cell').nth(await indexOf('REC YDS'))).toHaveText('20')
  await expect(row.getByRole('cell').nth(await indexOf('REC TD'))).toHaveText('1')
  const career = page.locator('section').filter({ has: page.getByText('Regular Season', { exact: true }) })
  await expect(career.getByRole('row').filter({ hasText: '2004' })).toContainText('20')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('scores receiving summary keeps a recorded receiver without targets', async ({ page }) => {
  await mockApi(page, [{ season: 2004, status: 'loaded' }])
  await page.route('**/api/leaders?*', route => route.fulfill({ json: [receiver, lateral, inactive] }))
  await page.goto('/?season=2004')
  await expect(page.getByRole('link', { name: /Recorded receiver/ })).toBeVisible()
  await expect(page.getByText('52', { exact: true })).toBeVisible()
})

test('team receiving tables keep signed production and correct totals', async ({ page }) => {
  await mockTeamSections(page)
  await page.route(url => url.pathname === '/api/teams/BUF', route => route.fulfill({ json: {
    ...teamProfile, leaders: [receiver, lateral, negative, inactive].map(p => ({ ...p, jersey_number: 10 })),
  } }))
  await page.goto('/teams/BUF')
  await expect(page.getByRole('link', { name: /Recorded receiver/ }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Full Stats', exact: true }).click()
  const table = page.getByRole('table', { name: 'Receiving statistics', exact: true })
  await expect(table.locator('tbody').getByRole('link')).toHaveText(['Recorded receiver', 'Lateral recipient', 'Negative yardage'])
  await expect(table.getByRole('row').filter({ hasText: 'Negative yardage' })).toContainText('-3')
  await expect(table.locator('tfoot')).toContainText('69')
})

test('game receiving stats and leader card show a zero-target lateral recipient', async ({ page }) => {
  await mockGame(page, { ...layoutGame, away: [{ ...gamePlayer, ...lateral, team: 'BUF' }], home: [] }, layoutLineup)
  await page.goto(`/games/${gameDetail.game_id}`)
  await expect(page.getByRole('link', { name: 'Lateral recipient', exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Stats', exact: true }).click()
  const table = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'REC/TGT', exact: true }) })
  await expect(table.getByRole('link', { name: 'Lateral recipient' })).toBeVisible()
  await expect(table.getByRole('row').filter({ hasText: 'Lateral recipient' })).toContainText('20')
})

test('running back popup shows secondary receiving production and negative yardage', async ({ page }) => {
  await mockGame(page, layoutGame, layoutLineup)
  await page.route('**/api/games/*/players/*/chart', route => route.fulfill({ json: {
    ...playerChart, role: 'rusher', stats: { carries: 3, rush_yards: 12, targets: 0, receptions: 0, rec_yards: -3, rec_tds: 0 },
  } }))
  await page.goto(`/games/${gameDetail.game_id}`)
  await page.getByRole('button', { name: 'Lineup', exact: true }).click()
  await page.getByTitle('Home quarterback', { exact: true }).click()
  const popup = page.getByRole('dialog')
  await expect(popup.getByText('Receiving yards', { exact: true })).toBeVisible()
  await expect(popup.getByText('-3', { exact: true })).toBeVisible()
})
