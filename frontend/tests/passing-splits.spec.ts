import { readFileSync } from 'node:fs'
import { expect, type Page, type Locator } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockSplits } from './fixtures/splits'
import { passingScope } from './fixtures/passing'
import { playerProfile } from './fixtures/playerProfile'
import type { PassingRow, PlayerPassingSplits } from '../src/types'
import { aggregatePlayerSplitRows, aggregateCareerByValue } from '../src/features/splits/aggregation'
import { preparedPassingRows, includePassingSeasons } from '../src/features/splits/passingModel'
import { preparedViewHasGaps } from '../src/features/splits/preparedCoverage'
import { PLAYER_SPLIT_CONFIG } from '../src/features/splits/playerConfig'

// Real read-only responses from the verified 28-season passing summary candidate.
const fixtures = JSON.parse(readFileSync(new URL('./fixtures/passingSplits.json', import.meta.url), 'utf8')) as Record<'vinny' | 'modern' | 'partial', PlayerPassingSplits>
const section = (page: Page, name: string) => page.getByRole('button', { name: new RegExp(`^By ${name} `) }).locator('..')
const summary = (page: Page) => page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Player', exact: true }) })
const base: PassingRow = { season: 2024, category: 'passing', split_dim: 'down', split_value: '1', sort_order: 1,
  att: 25, cmp: 20, yards: 250, td: 3, interceptions: 1, air_yards: 220, yac: 80, first_downs: 10,
  epa: .2, success_pct: 80, cpoe: 1, unavailable_metrics: {},
  aggregation: { epa_sum: 5, successes: 20, cpoe_sum: 2, cpoe_count: 2 } }

function data(rows: PassingRow[], overall = rows[0]): PlayerPassingSplits {
  return { player_id: 'test-player', scope: passingScope, seasons: [{ season: overall.season, status: 'prepared', reason: null,
    overall: { ...overall, split_dim: 'overall', split_value: 'all' }, rows, views: {}, game_coverage: null }] }
}
async function mockPassing(page: Page, payload: PlayerPassingSplits, name = 'Test passer') {
  await mockSplits(page)
  await page.route('**/api/seasons', route => route.fulfill({ json: [...new Set(payload.seasons.map(row => row.season))].map(season => ({ season, status: 'loaded' })) }))
  await page.route(url => /^\/api\/players\/[^/]+$/.test(url.pathname), route => route.fulfill({ json: { ...playerProfile, player_name: name } }))
  await page.route('**/api/players/*/passing-splits', route => route.fulfill({ json: payload }))
}
async function cell(table: Locator, row: Locator, label: string) {
  await expect(table).toBeVisible()
  const labels = await table.locator('thead tr').last().getByRole('columnheader').allTextContents()
  const index = labels.findIndex(text => text.replace(/[↑↓]/g, '').trim() === label)
  expect(index, label).toBeGreaterThanOrEqual(0)
  return row.getByRole('cell').nth(index)
}

test('CPOE uses modeled throws; EPA and success use their own full-precision sums', () => {
  const other = { ...base, split_value: '2', cmp: 15, yards: 150, first_downs: 7, epa: -.1, success_pct: 60, cpoe: 9,
    aggregation: { epa_sum: -2.5, successes: 15, cpoe_sum: 225, cpoe_count: 25 } }
  const before = JSON.stringify([base, other])
  const result = aggregatePlayerSplitRows([base, other]) as PassingRow
  expect(result.att).toBe(50)
  expect(result.yards).toBe(400)
  expect(result.epa).toBe(.05)
  expect(result.success_pct).toBe(70)
  expect(result.cpoe).toBeCloseTo(227 / 27, 12)
  expect(result.cpoe).not.toBe(5)
  expect(result.aggregation.cpoe_count).toBe(27)
  expect(JSON.stringify([base, other])).toBe(before)
})

test('sack-only EPA stays in combined totals and empty CPOE populations add no invented observations', () => {
  const sack = { ...base, split_value: '4', att: 0, cmp: 0, yards: 0, td: 0, interceptions: 0, first_downs: 0, air_yards: 0, yac: 0,
    epa: null, success_pct: null, cpoe: null, aggregation: { epa_sum: -2, successes: 0, cpoe_sum: 0, cpoe_count: 0 } }
  const result = aggregatePlayerSplitRows([base, sack]) as PassingRow
  expect(result.epa).toBe(.12)
  expect(result.success_pct).toBe(80)
  expect(result.cpoe).toBe(1)
  expect(aggregatePlayerSplitRows([sack])!.epa).toBeNull()
  const nested = aggregatePlayerSplitRows([result, base]) as PassingRow
  expect(nested.aggregation.epa_sum).toBe(8)
  expect(nested.epa).toBe(.16)
})

test('unknown ingredients preserve counts without becoming zero or a partial average', () => {
  const unknown = { ...base, epa: null, air_yards: null, yac: null,
    unavailable_metrics: { epa: 'Detailed passing credits and PBP player contributions disagree', air_yards: 'Unavailable before 2006', yac: 'Unavailable before 2006' },
    aggregation: { ...base.aggregation, epa_sum: null } }
  const result = aggregatePlayerSplitRows([base, unknown]) as PassingRow
  expect(result.att).toBe(50)
  expect(result.yards).toBe(500)
  expect(result.epa).toBeNull()
  expect(result.air_yards).toBeNull()
  expect(result.yac).toBeNull()
  expect(result.cpoe).toBe(1)
  expect(result.unavailable_metrics.epa).toContain('contributions disagree')
  const zeroRow: PassingRow = { ...base, aggregation: { ...base.aggregation, epa_sum: 0 }, epa: 0 }
  const zero = aggregatePlayerSplitRows([zeroRow, zeroRow])!
  expect(zero.epa).toBe(0)
})

test('unprepared seasons stay unknown in career buckets, including passer rating', () => {
  const payload = data([base])
  payload.seasons.push({ season: 2023, status: 'unverified', reason: 'Summary inputs not prepared.', overall: null, rows: [], views: {}, game_coverage: null })
  const all = preparedPassingRows(payload)
  const combined = aggregateCareerByValue(includePassingSeasons([base], all))[0]
  expect(combined.att).toBeNull()
  expect(combined.yards).toBeNull()
  expect(combined.epa).toBeNull()
  expect(PLAYER_SPLIT_CONFIG.passing.metrics.find(metric => metric.key === 'rate')!.value(combined)).toBeNull()
  expect(all.find(row => row.season === 2024 && row.split_dim === 'overall')!.yards).toBe(250)
})

test('career headline, season total and career bucket display the modeled CPOE average', async ({ page }) => {
  const first = data([base])
  const recent = { ...base, season: 2025, cmp: 15, yards: 150, first_downs: 7, epa: -.1, success_pct: 60, cpoe: 9,
    aggregation: { epa_sum: -2.5, successes: 15, cpoe_sum: 225, cpoe_count: 25 } }
  first.seasons.push(data([recent]).seasons[0])
  await mockPassing(page, first)
  await page.goto('/splits?p=test-player&season=0')
  const headline = summary(page)
  await expect(await cell(headline, headline.locator('tbody tr'), 'CPOE')).toHaveText('+8.4')
  const season = section(page, 'Season').getByRole('table')
  const total = season.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Qualifying seasons', exact: true }) })
  await expect(await cell(season, total, 'CPOE')).toHaveText('+8.4')
  const down = section(page, 'Down').getByRole('table')
  const bucket = down.getByRole('row').filter({ has: page.getByRole('cell', { name: '1st Down', exact: true }) })
  await expect(await cell(down, bucket, 'CPOE')).toHaveText('+8.4')
})

test('a sack-only bucket keeps its undefined row rate and contributes EPA to the shown total', async ({ page }) => {
  const sack = { ...base, split_value: '4', sort_order: 4, att: 0, cmp: 0, yards: 0, td: 0, interceptions: 0,
    first_downs: 0, air_yards: 0, yac: 0, epa: null, success_pct: null, cpoe: null,
    unavailable_metrics: { epa: 'No passing attempts in this bucket', success_pct: 'No passing attempts in this bucket', cpoe: 'No modeled CPOE observations' },
    aggregation: { epa_sum: -2, successes: 0, cpoe_sum: 0, cpoe_count: 0 } }
  const whole = { ...base, epa: .12, aggregation: { ...base.aggregation, epa_sum: 3 } }
  await mockPassing(page, data([base, sack], whole))
  await page.goto('/splits?p=test-player&season=2024')
  const table = section(page, 'Down').getByRole('table')
  const fourth = table.getByRole('row').filter({ has: page.getByRole('cell', { name: '4th Down', exact: true }) })
  await expect(fourth.getByRole('button', { name: 'EPA/att unavailable. Show explanation', exact: true })).toBeVisible()
  const total = table.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Shown total', exact: true }) })
  await expect(await cell(table, total, 'EPA/att')).toHaveText('+0.120')
})

for (const mobile of [false, true]) {
  test(`${mobile ? 'phone' : 'desktop'} real modern passing totals and all metrics use prepared data without legacy split requests`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await mockPassing(page, fixtures.modern)
    const reads: string[] = []
    page.on('request', request => reads.push(new URL(request.url()).pathname))
    await page.goto(`/splits?p=${fixtures.modern.player_id}&season=2024`)
    const overall = fixtures.modern.seasons[0].overall!
    for (const table of [summary(page), section(page, 'Season').getByRole('table')]) {
      const row = table.locator('tbody tr').first()
      for (const metric of PLAYER_SPLIT_CONFIG.passing.metrics) {
        const value = metric.value(overall)
        if (value != null) await expect(await cell(table, row, metric.label)).toHaveText(metric.fmt(value))
      }
    }
    expect(reads.some(path => /\/players\/[^/]+\/splits$/.test(path))).toBe(false)
    await expect(page.getByRole('link', { name: 'Test passer game logs →', exact: true })).toHaveAttribute('href', `/players/${fixtures.modern.player_id}`)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`passing-modern-${mobile ? 'phone' : 'desktop'}.png`), fullPage: true })
  })
}

test('historical passing counts stay visible and each unavailable field has a phone/keyboard explanation', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 })
  await mockPassing(page, fixtures.vinny, 'Vinny Testaverde')
  await page.goto(`/splits?p=${fixtures.vinny.player_id}&season=2004`)
  const table = summary(page)
  await expect(table.getByRole('cell', { name: '3532', exact: true })).toBeVisible()
  const trigger = table.getByRole('button', { name: 'EPA/att unavailable. Show explanation', exact: true })
  await trigger.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'EPA/att availability', exact: true })
  await expect(dialog).toContainText('official stats disagree with the play-by-play')
  await expect(dialog).toContainText('Verified counts are still shown.')
  const box = await dialog.boundingBox()
  expect(box!.width).toBeLessThanOrEqual(288)
  expect(box!.x).toBeGreaterThanOrEqual(0)
  await page.screenshot({ path: test.info().outputPath('passing-vinny-phone.png') })
  await page.keyboard.press('Escape')
  const down = section(page, 'Down').getByRole('row').filter({ has: page.getByRole('cell', { name: '1st Down', exact: true }) })
  await expect(await cell(section(page, 'Down').getByRole('table'), down, 'YDS')).toHaveText('1466')
  await expect(await cell(section(page, 'Down').getByRole('table'), down, 'ATT')).toHaveText('206')
})

test('partial play action keeps classified values, omitted production and independent season totals distinct', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockPassing(page, fixtures.partial, 'Current passer')
  await page.goto(`/splits?p=${fixtures.partial.player_id}&season=2026`)
  const season = fixtures.partial.seasons[0]
  const excluded = season.views.play_action.excluded
  expect(excluded.att).toBeGreaterThan(0)
  expect(preparedViewHasGaps([season], 'play_action')).toBe(true)
  await expect(await cell(summary(page), summary(page).locator('tbody tr'), 'YDS')).toHaveText(String(season.overall!.yards))
  await page.getByRole('button', { name: /^By Play Action / }).click()
  const view = section(page, 'Play Action')
  await expect(view).toContainText(`${excluded.att.toLocaleString()} attempts`)
  await expect(view).toContainText('retained in season totals')
  const total = view.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Shown total', exact: true }) })
  await expect(await cell(view.getByRole('table'), total, 'YDS')).toHaveText(String(season.overall!.yards! - excluded.yards))
  await expect(page.getByText('Where Current passer stands out').locator('..')).not.toContainText('Play Action')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('passing-partial-phone.png'), fullPage: true })
})

test('whole summary is independent of missing Down labels and profile game values', async ({ page }) => {
  const whole = { ...base, yards: 300 }
  const payload = data([base], whole)
  payload.seasons[0].views.down = { status: 'partial', reason: 'Missing Down.', definition: 'Recorded down.',
    excluded: { att: 0, cmp: 0, yards: 50, td: 0, interceptions: 0, first_downs: 0, sacks: 0 } }
  await mockPassing(page, payload)
  await page.goto('/splits?p=test-player&season=2024')
  await expect(await cell(summary(page), summary(page).locator('tbody tr'), 'YDS')).toHaveText('300')
  await expect(section(page, 'Season').getByRole('cell', { name: '300', exact: true }).first()).toBeVisible()
  await expect(section(page, 'Down').getByRole('cell', { name: '250', exact: true }).first()).toBeVisible()
})

test('an unverified career year keeps verified season rows visible and combined columns unknown', async ({ page }) => {
  const payload = data([base])
  payload.seasons.push({ season: 2023, status: 'unverified', reason: 'Summary inputs not prepared.', overall: null, rows: [], views: {}, game_coverage: null })
  await mockPassing(page, payload)
  await page.goto('/splits?p=test-player&season=0')
  await expect(summary(page).getByRole('button', { name: 'YDS unavailable. Show explanation', exact: true })).toBeVisible()
  await expect(section(page, 'Season').getByRole('cell', { name: '250', exact: true }).first()).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Passing coverage' })).toContainText('have not been verified')
})
