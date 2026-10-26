import { expect, type Page, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockReceiving, preparedSeason, receivingFixtures, receivingScope } from './fixtures/receiving'
import { aggregatePlayerSplitRows, aggregateCareerByValue } from '../src/features/splits/aggregation'
import { includeReceivingSeasons, preparedReceivingRows, receivingViewHasGaps } from '../src/features/splits/receivingModel'
import { per, pct } from '../src/features/splits/metricFormatting'
import type { PlayerReceivingSplits, ReceivingRow } from '../src/types'

const section = (page: Page, name: string) => page.getByRole('button', { name: new RegExp(`^By ${name} `) }).locator('..')
const summary = (page: Page) => page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Player', exact: true }) })
const url = (id = receivingFixtures.gibbs.player_id, season = 2024) => `/splits?p=${id}&cat=receiving&season=${season}`

test('known production survives mixed history; missing numerators and positive-weight rates do not become zero', () => {
  const [historical, modern] = receivingFixtures.gonzalez.seasons.map(item => item.overall!)
  const before = JSON.stringify([historical, modern])
  const combined = aggregatePlayerSplitRows([historical, modern])!
  expect(combined.cmp).toBe(185)
  expect(combined.yards).toBe(2125)
  for (const field of ['att', 'yac', 'air_yards', 'epa', 'success_pct', 'interceptions', 'cpoe'] as const) expect(combined[field]).toBeNull()
  const missingAir = { ...modern, air_yards: null }
  const onlyAir = aggregatePlayerSplitRows([modern, missingAir])!
  expect(onlyAir.air_yards).toBeNull()
  expect(onlyAir.epa).toBe(modern.epa)
  expect(onlyAir.yac).toBe(modern.yac! * 2)
  expect(aggregatePlayerSplitRows([modern, { ...modern, epa: null }])!.epa).toBeNull()
  const zeroTargets = { ...modern, att: 0, cmp: 0, yards: 20, epa: null, success_pct: null }
  expect(aggregatePlayerSplitRows([modern, zeroTargets])!.epa).toBe(modern.epa)
  expect(aggregatePlayerSplitRows([{ ...modern, yac: 0 }])!.yac).toBe(0)
  expect(per(null, 10)).toBeNull()
  expect(pct(undefined, 10)).toBeNull()
  expect(per(0, 10)).toBe(0)
  expect(JSON.stringify([historical, modern])).toBe(before)
})

test('an unverified year never supplies zeroes to career buckets', () => {
  const row = receivingFixtures.gibbs.seasons[0].rows[0]
  const data: PlayerReceivingSplits = { player_id: 'test', scope: receivingScope, seasons: [
    preparedSeason(row), { season: 2023, status: 'unverified', reason: 'Not prepared.', overall: null, rows: [], game_coverage: null, views: {} },
  ] }
  const all = preparedReceivingRows(data)
  const values = aggregateCareerByValue(includeReceivingSeasons([row], all))
  expect(values[0].cmp).toBeNull()
  expect(values[0].yards).toBeNull()
  expect(all.find(item => item.season === 2024 && item.split_dim === 'overall')!.yards).toBe(row.yards)
})

test('an absent historical bucket cannot hide that season’s unknown target and YAC fields', () => {
  const all = preparedReceivingRows(receivingFixtures.gonzalez)
  const pressure = all.filter(row => row.split_dim === 'pressure')
  expect(pressure.every(row => row.season === 2009)).toBe(true)
  const combined = aggregateCareerByValue(includeReceivingSeasons(pressure, all))
  expect(combined.length).toBeGreaterThan(0)
  for (const row of combined) {
    expect(row.att).toBeNull()
    expect(row.yac).toBeNull()
    expect(row.epa).toBeNull()
    expect(row.cmp).toBe(pressure.find(original => original.split_value === row.split_value)!.cmp)
  }
})

test('only player-specific exclusions or unavailable coverage block a receiving standout', () => {
  expect(receivingViewHasGaps(receivingFixtures.partial.seasons, 'surface')).toBe(true)
  expect(receivingFixtures.gibbs.seasons[0].views.down.status).toBe('partial')
  expect(receivingViewHasGaps(receivingFixtures.gibbs.seasons, 'down')).toBe(false)
  expect(receivingViewHasGaps(receivingFixtures.gonzalez.seasons, 'pressure')).toBe(true)
})

for (const mobile of [false, true]) {
  test(`${mobile ? 'phone' : 'desktop'} official Gibbs totals include the previously omitted 41 lateral yards throughout the page`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await mockReceiving(page)
    const reads: string[] = []
    page.on('request', request => { reads.push(new URL(request.url()).pathname) })
    await page.goto(url())
    await expect(summary(page).getByRole('cell', { name: '517', exact: true })).toBeVisible()
    for (const name of ['Season', 'Down']) {
      const total = section(page, name).getByRole('row').filter({ hasText: name === 'Season' ? 'Season total' : 'Shown total' })
      await expect(total.getByRole('cell', { name: '517', exact: true })).toBeVisible()
    }
    await expect(page.getByRole('complementary', { name: 'Receiving yardage sources' })).toHaveCount(0)
    expect(reads.some(path => /\/players\/[^/]+\/splits$/.test(path))).toBe(false)
    await expect(page.getByRole('link', { name: 'Jahmyr Gibbs game logs →', exact: true })).toHaveAttribute('href', `/players/${receivingFixtures.gibbs.player_id}`)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: test.info().outputPath(`receiving-gibbs-${mobile ? 'phone' : 'desktop'}.png`), fullPage: true })
  })
}

test('partial surface counts stay labelled while independent season totals remain whole', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockReceiving(page, [receivingFixtures.partial])
  await page.goto(url(receivingFixtures.partial.player_id, 2026))
  await expect(summary(page).getByRole('cell', { name: '494', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /^By Surface / }).click()
  const surface = section(page, 'Surface')
  await expect(surface).toContainText('23 catches')
  await expect(surface).toContainText('retained in season totals')
  const shown = surface.getByRole('row').filter({ hasText: 'Shown total' })
  const expected = receivingFixtures.partial.seasons[0].overall!.yards! - receivingFixtures.partial.seasons[0].views.surface.excluded.yards
  await expect(shown.getByRole('cell', { name: String(expected), exact: true })).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Receiving coverage' })).toContainText('Play data is present for 92 games')
  await expect(page.getByText('Where Current receiver stands out').locator('..')).not.toContainText('Surface')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: test.info().outputPath('receiving-partial-phone.png'), fullPage: true })
})

test('historical career retains production and explains each unavailable stat on phone and keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 })
  await mockReceiving(page, [receivingFixtures.gonzalez])
  await page.goto(url(receivingFixtures.gonzalez.player_id, 0))
  await expect(summary(page).getByRole('cell', { name: '2125', exact: true })).toBeVisible()
  const trigger = summary(page).getByRole('button', { name: 'TGT unavailable. Show explanation', exact: true })
  await trigger.focus()
  await page.keyboard.press('Enter')
  const note = page.getByRole('dialog', { name: 'TGT availability', exact: true })
  await expect(note).toContainText('2003–2008')
  const box = await note.boundingBox()
  expect(box!.width).toBeLessThanOrEqual(288)
  expect(box!.x).toBeGreaterThanOrEqual(0)
  await page.screenshot({ path: test.info().outputPath('receiving-unavailable-phone.png') })
  await page.keyboard.press('Escape')
  await expect(note).not.toBeVisible()
  await page.getByRole('button', { name: 'Under Pressure', exact: true }).click()
  await expect(summary(page).getByRole('button', { name: 'TGT unavailable. Show explanation', exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: 'Season' }).selectOption('2009')
  await page.getByRole('button', { name: 'Overall', exact: true }).click()
  await expect(summary(page).getByRole('cell', { name: '135', exact: true })).toBeVisible()
  await expect(summary(page).getByRole('button', { name: 'TGT unavailable. Show explanation', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('receiving comparison uses prepared rows and per-player coverage in grouped tables', async ({ page }) => {
  await mockReceiving(page, [receivingFixtures.gibbs, receivingFixtures.jefferson])
  await page.goto(url(`${receivingFixtures.gibbs.player_id},${receivingFixtures.jefferson.player_id}`))
  await expect(summary(page).getByRole('cell', { name: '1533', exact: true })).toBeVisible()
  await expect(section(page, 'Season').getByRole('cell', { name: '517', exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'All stats', exact: true }).click()
  await expect(section(page, 'Down').getByRole('columnheader', { name: 'Jahmyr Gibbs', exact: true })).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
})

test('unverified and empty receiving responses are explained without falling back to legacy totals', async ({ page }) => {
  const data: PlayerReceivingSplits = { player_id: 'old', scope: receivingScope, seasons: [{
    season: 2024, status: 'unverified', reason: 'No prepared totals.', overall: null, rows: [], game_coverage: null, views: {},
  }] }
  await mockReceiving(page, [data])
  await page.goto(url('old'))
  await expect(page.getByRole('complementary', { name: 'Receiving coverage' })).toContainText('Receiving splits have not been verified')
  await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toHaveCount(0)
  await page.goto(url('empty'))
  await expect(page.getByText('No split statistics for this selection.', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('mixed verified/unverified careers keep the known season visible and combined columns unavailable', async ({ page }) => {
  const data = structuredClone(receivingFixtures.gibbs)
  data.seasons.push({ season: 2023, status: 'unverified', reason: 'Not prepared.', overall: null, rows: [], game_coverage: null, views: {} })
  await mockReceiving(page, [data])
  await page.goto(url(data.player_id, 0))
  await expect(summary(page).getByRole('button', { name: 'YDS unavailable. Show explanation', exact: true })).toBeVisible()
  await expect(section(page, 'Season').getByRole('cell', { name: '517', exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: 'Season' }).selectOption('2024')
  await expect(summary(page).getByRole('cell', { name: '517', exact: true })).toBeVisible()
})

test('receiving failure retry and cache stay independent from the legacy split resource', async ({ page }) => {
  await mockReceiving(page)
  let fail = true
  let reads = 0
  await page.route('**/api/players/*/receiving-splits', route => {
    reads++
    return route.fulfill(fail ? { status: 503, json: { detail: 'Prepared receiving unavailable.' } } : { json: receivingFixtures.gibbs })
  })
  await page.goto(url())
  await expect(page.getByRole('alert')).toContainText('Prepared receiving unavailable.')
  fail = false
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(summary(page).getByRole('cell', { name: '517', exact: true })).toBeVisible()
  const initial = reads
  await page.getByRole('combobox', { name: 'Season' }).selectOption('0')
  await page.getByRole('button', { name: 'Passing', exact: true }).click()
  await page.getByRole('button', { name: 'Receiving', exact: true }).click()
  await expect(summary(page).getByRole('cell', { name: '517', exact: true })).toBeVisible()
  expect(reads).toBe(initial)
})

test('leaving cancels an unfinished receiving request', async ({ page }) => {
  await mockReceiving(page)
  const pending: Route[] = []
  await page.route('**/api/players/*/receiving-splits', route => { pending.push(route) })
  await page.goto(url())
  await expect(page.getByRole('status').filter({ hasText: 'Loading Jahmyr Gibbs split statistics' })).toBeVisible()
  await expect.poll(() => pending.length).toBeGreaterThan(0)
  await page.getByRole('link', { name: 'Scores', exact: true }).click()
  await expect(page.locator('main')).toBeVisible()
  for (const route of pending) {
    await route.fulfill({ json: receivingFixtures.gibbs })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
})

test('one missing play-data game is distinguished from an unconfirmed schedule', async ({ page }) => {
  const data = structuredClone(receivingFixtures.gibbs)
  data.seasons[0].game_coverage = { status: 'partial', supplied_games: 16, recorded_completed_games: 17,
    missing_game_ids: ['missing'], unconfirmed_game_ids: [], reason: 'Missing supplied play data.' }
  await mockReceiving(page, [data])
  await page.goto(url())
  const note = page.getByRole('complementary', { name: 'Receiving coverage' })
  await expect(note).toContainText('1 completed game lacks play data')
  await expect(note).not.toContainText('Play data is present')
  await expect(summary(page).getByRole('cell', { name: '517', exact: true })).toBeVisible()
})

test('a failed receiving comparison member leaves the other player usable', async ({ page }) => {
  await mockReceiving(page, [receivingFixtures.gibbs, receivingFixtures.jefferson])
  await page.route(url => url.pathname === `/api/players/${receivingFixtures.jefferson.player_id}/receiving-splits`,
    route => route.fulfill({ status: 503, json: { detail: 'Prepared data unavailable.' } }))
  await page.goto(url(`${receivingFixtures.gibbs.player_id},${receivingFixtures.jefferson.player_id}`))
  await expect(page.getByRole('alert')).toContainText('Justin Jefferson')
  await expect(summary(page).getByRole('cell', { name: '517', exact: true })).toBeVisible()
})

test('zero-target lateral production has no target rate but keeps signed receiving yards', async ({ page }) => {
  const base = receivingFixtures.gibbs.seasons[0].overall!
  const lateral: ReceivingRow = { ...base, att: 0, cmp: 0, yards: -3, td: 1, yac: -3, first_downs: 0, air_yards: 0,
    epa: null, success_pct: null, unavailable_metrics: { epa: 'No recorded targets in this row.', success_pct: 'No recorded targets in this row.' } }
  await mockReceiving(page, [{ player_id: 'lateral', scope: receivingScope, seasons: [preparedSeason(lateral)] }])
  await page.goto(url('lateral'))
  await expect(summary(page).getByRole('cell', { name: '-3', exact: true })).toHaveCount(2)
  await expect(summary(page).getByRole('button', { name: 'EPA/tgt unavailable. Show explanation', exact: true })).toBeVisible()
  await expect(page.getByText('NaN', { exact: true })).toHaveCount(0)
})
