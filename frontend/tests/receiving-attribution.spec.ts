import { readFileSync } from 'node:fs'
import { expect, type Page } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockSplits, offensiveSplit } from './fixtures/splits'
import { playerGame, playerProfile } from './fixtures/playerProfile'
import type { PlayerGame, PlayerSplit } from '../src/types'
import { receivingYardageDifferences, RECEIVING_YARDAGE_NOTE_ID } from '../src/features/splits/receivingAttribution'

type SourcePlayer = {
  player_id: string; player_name: string
  weekly_games: Pick<PlayerGame, 'season' | 'week' | 'game_id' | 'team' | 'opponent' | 'targets' | 'receptions' | 'rec_yards' | 'rec_tds'>[]
  down_splits: Pick<PlayerSplit, 'season' | 'split_dim' | 'split_value' | 'sort_order' | 'att' | 'cmp' | 'yards' | 'td'>[]
}
const { players } = JSON.parse(readFileSync(new URL('./fixtures/receivingAttribution.json', import.meta.url), 'utf8')) as { players: SourcePlayer[] }
const [gibbs, jefferson] = players
function games(player = gibbs): PlayerGame[] {
  return player.weekly_games.map(row => ({ ...playerGame, ...row, position: player === gibbs ? 'RB' : 'WR',
    game_type: 'REG', attempts: 0, completions: 0, pass_yards: 0, carries: 0 }))
}
function splits(player = gibbs): PlayerSplit[] {
  return player.down_splits.map(row => ({ ...offensiveSplit, ...row, category: 'receiving' }))
}
async function mockAttribution(page: Page, changeGames: (games: PlayerGame[]) => PlayerGame[] = games => games) {
  await mockSplits(page)
  await page.route(url => /^\/api\/players\/[^/]+$/.test(url.pathname), route => {
    const id = new URL(route.request().url()).pathname.split('/').at(-1)
    const player = players.find(player => player.player_id === id)!
    return route.fulfill({ json: { ...playerProfile, player_id: id, player_name: player.player_name,
      position: player === gibbs ? 'RB' : 'WR', games: changeGames(games(player)) } })
  })
  await page.route('**/api/players/*/splits', route => {
    const id = new URL(route.request().url()).pathname.split('/').at(-2)
    return route.fulfill({ json: splits(players.find(player => player.player_id === id)!) })
  })
}
const url = (ids = gibbs.player_id) => `/splits?p=${ids}&cat=receiving&season=2024`
const section = (page: Page, name: string) => page.getByRole('button', { name: new RegExp(`^By ${name} `) }).locator('..')

test('real Gibbs observations explain 41 lateral yards while the ordinary control matches', () => {
  const weekly = games(), down = splits()
  const before = JSON.stringify({ weekly, down })
  const [difference] = receivingYardageDifferences(gibbs.player_id, weekly, [...down, { ...down[0], split_dim: 'quarter', yards: 9999 }], 2024)
  expect(difference).toMatchObject({ weeklyYards: 517, splitYards: 476, difference: 41 })
  expect(difference.reviewedPlays?.reduce((sum, play) => sum + play.yards, 0)).toBe(41)
  expect(receivingYardageDifferences(jefferson.player_id, games(jefferson), splits(jefferson), 2024)).toEqual([])
  expect(JSON.stringify({ weekly, down })).toBe(before)
})

test('missing, invalid and unmatched observations never acquire the specific lateral explanation', () => {
  const weekly = games(), down = splits()
  for (const [gs, rows] of [[undefined, down], [weekly, undefined], [weekly, []], [weekly, [{ ...down[0], yards: null }]], [[{ ...weekly[0], rec_yards: Number.NaN }], down]] as const) {
    expect(receivingYardageDifferences(gibbs.player_id, gs, rows, 2024)).toEqual([])
  }
  const oldWeekly = weekly.map(g => g.week === 3 ? { ...g, rec_yards: 0 } : g)
  expect(receivingYardageDifferences(gibbs.player_id, oldWeekly, down, 2024)[0]).toMatchObject({ weeklyYards: 497, difference: 21, reviewedPlays: null })
  expect(receivingYardageDifferences('unreviewed-player', weekly, down, 2024)[0].reviewedPlays).toBeNull()
})

test('career comparison keeps opposite season differences separate and excludes postseason', () => {
  const weekly = games(), down = splits()
  const future = { ...weekly[0], season: 2025, rec_yards: 476 }
  const futureSplit = { ...down[0], season: 2025, yards: 517 }
  const result = receivingYardageDifferences(gibbs.player_id,
    [...weekly, future, { ...future, game_type: 'POST', rec_yards: 9999 }], [...down, futureSplit], 0)
  expect(result.map(row => [row.season, row.difference])).toEqual([[2025, -41], [2024, 41]])
  expect(receivingYardageDifferences(gibbs.player_id, weekly, down, 2023)).toEqual([])
  expect(receivingYardageDifferences(gibbs.player_id, weekly, down, null)).toEqual([])
})

for (const mobile of [false, true]) {
  test(`${mobile ? 'mobile' : 'desktop'} Gibbs note keeps both yard totals, flags situational columns and links reviewed plays`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await mockAttribution(page)
    await page.goto(url())
    const note = page.getByRole('complementary', { name: 'Receiving yardage sources' })
    await expect(note).toContainText('Jahmyr Gibbs · 2024')
    await expect(note.getByText('517 yds', { exact: true })).toBeVisible()
    await expect(note.getByText('476 yds', { exact: true })).toBeVisible()
    await expect(note.getByText('+41 yds', { exact: true })).toBeVisible()
    await expect(note).toContainText('Two reviewed lateral plays')
    await expect(section(page, 'Season').getByRole('row').filter({ hasText: 'Total' })).toContainText('517')
    await expect(section(page, 'Down').getByRole('row').filter({ hasText: 'Total' })).toContainText('476')
    await expect(section(page, 'Down').locator(`th[aria-describedby="${RECEIVING_YARDAGE_NOTE_ID}"]`)).toHaveText(['YDS†', 'Y/R†', 'Y/Tgt†'])
    await expect(section(page, 'Season').locator('sup')).toHaveCount(0)
    await note.getByText('Reviewed lateral plays', { exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(note.getByRole('link', { name: 'Week 3 at Arizona' })).toHaveAttribute('href', '/games/2024_03_DET_ARI')
    await expect(note.getByRole('link', { name: 'Week 15 vs Buffalo' })).toHaveAttribute('href', '/games/2024_15_BUF_DET')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await note.screenshot({ path: test.info().outputPath(`receiving-sources-${mobile ? 'mobile' : 'desktop'}.png`) })
  })
}

test('matching receiver gets all existing splits without a discrepancy note or marker', async ({ page }) => {
  await mockAttribution(page)
  await page.goto(url(jefferson.player_id))
  await expect(section(page, 'Down').getByRole('row').filter({ hasText: 'Total' })).toContainText('1533')
  await expect(page.getByRole('complementary', { name: 'Receiving yardage sources' })).toHaveCount(0)
  await expect(page.locator('sup')).toHaveCount(0)
})

test('side-by-side comparison identifies Gibbs while leaving matching player columns unmarked', async ({ page }) => {
  await mockAttribution(page)
  await page.goto(url(`${gibbs.player_id},${jefferson.player_id}`))
  const note = page.getByRole('complementary', { name: 'Receiving yardage sources' })
  await expect(note).toContainText('Jahmyr Gibbs')
  await expect(note).not.toContainText('Justin Jefferson')
  await page.getByRole('button', { name: 'All stats', exact: true }).click()
  await expect(section(page, 'Down').locator('sup')).toHaveCount(3)
  await expect(section(page, 'Season').locator('sup')).toHaveCount(0)
})

test('older weekly totals show the observed difference without claiming the reviewed 41-yard cause', async ({ page }) => {
  await mockAttribution(page, rows => rows.map(g => g.week === 3 ? { ...g, rec_yards: 0 } : g))
  await page.goto(url())
  const note = page.getByRole('complementary', { name: 'Receiving yardage sources' })
  await expect(note.getByText('497 yds', { exact: true })).toBeVisible()
  await expect(note.getByText('+21 yds', { exact: true })).toBeVisible()
  await expect(note).toContainText('cause has not been confirmed for these values')
  await expect(note.getByText('Reviewed lateral plays', { exact: true })).toHaveCount(0)
})
