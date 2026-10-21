import { expect, type Locator } from '@playwright/test'
import { test, mockApi } from './fixtures/scores'
import { passer } from './fixtures/players'
import { mockProfile, playerGame, playerProfile } from './fixtures/playerProfile'
import { mockTeamSections, teamProfile } from './fixtures/teamProfile'
import { mockGame, gameDetail, gamePlayer, playerChart } from './fixtures/gameDetail'
import { layoutGame, layoutLineup } from './fixtures/gameLayout'
import { mockSplits, offensiveSplit } from './fixtures/splits'
import { sumGames, aggregateSituational } from '../src/features/players/stats'
import { aggregateTotals } from '../src/features/teams/stats'
import { aggregatePlayerSplitRows, gameToSplitRow } from '../src/features/splits/aggregation'
import { STAT_TABS } from '../src/features/leaders/columns'
import { REC_COLS } from '../src/features/teams/columns'

const receiver = { ...passer, player_id: 'historical', player_name: 'Historical receiver', position: 'WR',
  attempts: 0, completions: 0, pass_yards: 0, targets: null, receptions: 4, rec_yards: 52, rec_tds: 1 }
const historical = { ...playerGame, game_id: '2004_01_BUF_MIA', season: 2004, position: 'WR',
  attempts: 0, carries: 0, targets: null, receptions: 4, rec_yards: 52, rec_tds: 1 }
const modern = { ...historical, game_id: '2009_01_BUF_MIA', season: 2009, targets: 20, receptions: 10, rec_yards: 100 }
const profile = { ...playerProfile, position: 'WR', games: [historical, modern] }
const split = { ...offensiveSplit, season: 2004, category: 'receiving', att: null, cmp: 4,
  yards: 52, td: 1, epa: null, success_pct: null }

async function cell(table: Locator, row: Locator, label: string) {
  await expect(table).toBeVisible()
  const labels = await table.locator('thead tr').last().getByRole('columnheader').allTextContents()
  const index = labels.findIndex(text => text.replace(/[↑↓]/g, '').trim() === label)
  expect(index, `column ${label}`).toBeGreaterThanOrEqual(0)
  return row.getByRole('cell').nth(index)
}

test('career, team and split totals propagate unavailable targets without losing production', () => {
  const total = sumGames([historical, modern])
  expect(total.targets).toBeNull()
  expect(total.receptions).toBe(14)
  expect(total.rec_yards).toBe(152)
  expect(sumGames([modern]).targets).toBe(20)
  expect(sumGames([{ ...historical, targets: 0 }]).targets).toBe(0)
  expect(aggregateTotals([{ ...receiver, jersey_number: 10 }, { ...receiver, targets: 20, jersey_number: 10 }]).targets).toBeNull()
  const combined = aggregatePlayerSplitRows([split, { ...split, season: 2009, att: 20, epa: 1, success_pct: 50 }])!
  expect(combined.att).toBeNull()
  expect(combined.epa).toBeNull()
  expect(combined.success_pct).toBeNull()
  expect(combined.cmp).toBe(8)
  expect(gameToSplitRow(historical, 'receiving').att).toBeNull()
  expect(aggregateSituational({ 2004: { rz_targets: null, third_targets: null }, 2009: { rz_targets: 20, third_targets: 10 } }).rz_targets).toBeNull()
})

test('unavailable rates remain distinct from real zero in render and sorting values', () => {
  const columns = STAT_TABS.find(tab => tab.key === 'receiving')!.cols
  for (const key of ['tgt', 'cpct', 'ytgt', 'epat']) {
    const col = columns.find(col => col.key === key)!
    expect(col.render(receiver)).toBeNull()
    expect(col.sortVal(receiver)).toBeNull()
  }
  const targets = columns.find(col => col.key === 'tgt')!
  expect(targets.render({ ...receiver, targets: 0 })).toBe(0)
  const teamTargets = REC_COLS.find(col => col.key === 'tgt')!
  const zero = { ...receiver, targets: 0, jersey_number: 10 }
  expect(teamTargets.render(zero, aggregateTotals([zero]))).toBe(0)
})

test('receiving leaderboard explains unavailable targets and disables empty rate sorting', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockApi(page, [{ season: 2004, status: 'loaded' }])
  await page.route('**/api/leaders?*', route => route.fulfill({ json: [receiver] }))
  await page.goto('/leaders?season=2004&tab=receiving')
  await expect(page.getByRole('complementary', { name: 'Receiving data availability' })).toContainText('Receptions, receiving yards and touchdowns are still shown.')
  const table = page.getByRole('table')
  const row = table.locator('tbody tr')
  for (const key of ['TGT', 'CTH%', 'Y/TGT', 'EPA/Tgt']) await expect(await cell(table, row, key)).toHaveText('—')
  await expect(await cell(table, row, 'YDS')).toHaveText('52')
  await expect(table.getByRole('button', { name: 'CTH%', exact: true })).toBeDisabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('historical-receiving-mobile.png'), fullPage: true })
})

test('mixed career shows complete production and no partial career target rates', async ({ page }) => {
  await mockProfile(page, profile)
  await page.goto('/players/test-player')
  await expect(page.getByRole('complementary', { name: 'Receiving data availability' })).toContainText('any included season is affected')
  const table = page.locator('section').filter({ has: page.getByText('Regular Season', { exact: true }) }).getByRole('table')
  const career = table.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Career', exact: true }) })
  for (const label of ['TGT', 'CTH%', 'Y/TGT']) await expect(await cell(table, career, label)).toHaveText('—')
  await expect(await cell(table, career, 'REC')).toHaveText('14')
  await expect(await cell(table, career, 'YDS')).toHaveText('152')
  const modernRow = table.getByRole('row').filter({ has: page.getByRole('cell', { name: '2009', exact: true }) })
  await expect(await cell(table, modernRow, 'TGT')).toHaveText('20')
  await expect(await cell(table, modernRow, 'CTH%')).toHaveText('50.0')
  await expect(page.getByText('NaN', { exact: true })).toHaveCount(0)
})

test('team receiving totals and summary show dashes without hiding production', async ({ page }) => {
  await mockTeamSections(page)
  await page.route(url => url.pathname === '/api/teams/BUF', route => route.fulfill({ json: {
    ...teamProfile, season: 2004, leaders: [{ ...receiver, jersey_number: 10 }],
  } }))
  await page.goto('/teams/BUF')
  await page.getByRole('button', { name: 'Full Stats', exact: true }).click()
  await expect(page.getByRole('complementary', { name: 'Receiving data availability' }).last()).toBeVisible()
  const table = page.getByRole('table', { name: 'Receiving statistics', exact: true })
  await expect(await cell(table, table.locator('tfoot tr'), 'TGT')).toHaveText('—')
  await expect(await cell(table, table.locator('tfoot tr'), 'CTH%')).toHaveText('—')
  await expect(table.locator('tbody')).toContainText('Historical receiver')
  await expect(table.locator('tfoot')).toContainText('52')
  await expect(page.getByText('4/—', { exact: true })).toBeVisible()
})

test('game receiving line and chart explain target gaps without showing a partial target map', async ({ page }) => {
  await mockGame(page, { ...layoutGame, away: [{ ...gamePlayer, ...receiver, team: 'BUF' }], home: [] }, layoutLineup)
  await page.route('**/api/games/*/players/*/chart', route => route.fulfill({ json: {
    ...playerChart, role: 'receiver', stats: { targets: null, receptions: 4, rec_yards: 52, rec_tds: 1 },
  } }))
  await page.goto(`/games/${gameDetail.game_id}`)
  await expect(page.getByText('4/— TGT, 1 TD', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Lineup', exact: true }).click()
  await page.getByTitle('Home quarterback', { exact: true }).click()
  const popup = page.getByRole('dialog')
  await expect(popup.getByRole('complementary', { name: 'Receiving data availability' })).toBeVisible()
  await expect(popup.getByText('Receiving yards', { exact: true })).toBeVisible()
  await expect(popup.locator('.target-map')).toHaveCount(0)
})

test('receiving split careers retain affected game rows and unavailable totals', async ({ page }) => {
  await mockSplits(page)
  await page.route(url => /^\/api\/players\/[^/]+$/.test(url.pathname), route => route.fulfill({ json: profile }))
  await page.route('**/api/players/*/splits', route => route.fulfill({ json: [split, { ...split, season: 2009, att: 20 }] }))
  await page.goto('/splits?p=test-player&cat=receiving&season=0')
  await expect(page.getByRole('complementary', { name: 'Receiving data availability' })).toBeVisible()
  const season = page.getByRole('button', { name: /^By Season / }).locator('..')
  await expect(season.getByRole('cell', { name: /2004/ })).toBeVisible()
  await expect(season.getByRole('cell', { name: '52', exact: true })).toBeVisible()
  const table = season.getByRole('table')
  const total = table.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Total', exact: true }) })
  await expect(await cell(table, total, 'TGT')).toHaveText('—')
  await expect(await cell(table, total, 'Catch%')).toHaveText('—')
})

test('modern receiving data keeps numeric targets and rates without a gap notice', async ({ page }) => {
  await mockApi(page, [{ season: 2024, status: 'loaded' }])
  await page.route('**/api/leaders?*', route => route.fulfill({ json: [{ ...receiver, targets: 20 }] }))
  await page.goto('/leaders?season=2024&tab=receiving')
  await expect(page.getByRole('complementary', { name: 'Receiving data availability' })).toHaveCount(0)
  const table = page.getByRole('table')
  await expect(await cell(table, table.locator('tbody tr'), 'TGT')).toHaveText('20')
  await expect(await cell(table, table.locator('tbody tr'), 'CTH%')).toHaveText('20.0')
})
