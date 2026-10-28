import { expect, type Page } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockSplits, offensiveSplits, teamSplits } from './fixtures/splits'
import { passingFixture } from './fixtures/passing'

function section(page: Page, name: string) {
  return page.getByRole('button', { name: new RegExp(`^By ${name} `) }).locator('..')
}
function summary(page: Page) {
  return page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Player', exact: true }) })
}
async function ready(page: Page, url: string) {
  await mockSplits(page)
  await page.goto(url)
  await expect(section(page, 'Down').getByRole('cell', { name: '1st Down', exact: true })).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
}
async function capture(page: Page, name: string) {
  const directory = process.env.SPLITS_LAYOUT_CAPTURE
  await page.screenshot({ path: directory ? `${directory}/${name}.png` : test.info().outputPath(`${name}.png`), fullPage: true, animations: 'disabled' })
}

for (const mobile of [false, true]) {
  test(`${mobile ? 'mobile' : 'desktop'} single-player splits keep prepared totals, weighted rates, and standout cards`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await ready(page, '/splits?p=test-player&season=2023')
    await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toBeVisible()
    await expect(summary(page).getByRole('cell', { name: '+2.333', exact: true })).toBeVisible()
    await expect(section(page, 'Season').getByRole('cell', { name: '250', exact: true }).first()).toBeVisible()
    await expect(page.getByText('Where Test quarterback stands out', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await capture(page, `splits-single-${mobile ? 'mobile' : 'desktop'}`)
    await expect(page.getByRole('link', { name: 'Test quarterback game logs →', exact: true })).toHaveAttribute('href', '/players/test-player')
    await expect(section(page, 'Season').getByRole('button', { name: '▸', exact: true })).toHaveCount(0)
    await page.getByRole('combobox', { name: 'Season' }).selectOption('0')
    await expect(summary(page).getByRole('cell', { name: '550', exact: true })).toBeVisible()
    await expect(summary(page).getByRole('cell', { name: '+3.000', exact: true })).toBeVisible()
  })
}

for (const mobile of [false, true]) {
  test(`${mobile ? 'mobile' : 'desktop'} comparison keeps grouped columns, winner shading, and prepared season rows`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await ready(page, '/splits?p=test-player,other-player&season=2023')
    await expect(section(page, 'Down').getByRole('columnheader', { name: 'Second quarterback', exact: true })).toBeVisible()
    await expect(summary(page).getByRole('cell', { name: '500', exact: true })).toHaveClass(/text-data-win/)
    await expect(page.getByRole('link', { name: /game logs →/ })).toHaveCount(2)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await capture(page, `splits-comparison-${mobile ? 'mobile' : 'desktop'}`)
    const keyColumns = await section(page, 'Down').getByRole('columnheader').count()
    await page.getByRole('button', { name: 'All stats', exact: true }).click()
    expect(await section(page, 'Down').getByRole('columnheader').count()).toBeGreaterThan(keyColumns)
  })
}

test('single-player sorting, situations, and section visibility retain their state', async ({ page }) => {
  await ready(page, '/splits?p=test-player&season=2023')
  const down = section(page, 'Down')
  await down.getByRole('columnheader', { name: /^YDS/ }).click()
  await expect(down.getByRole('row').nth(1)).toContainText('1st Down')
  await down.getByRole('columnheader', { name: /^YDS/ }).click()
  await expect(down.getByRole('row').nth(1)).toContainText('3rd Down')
  await page.getByRole('button', { name: '3rd Down', exact: true }).click()
  await expect(summary(page).getByRole('cell', { name: '50', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Overall', exact: true }).click()
  await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Down', exact: true }).click()
  await expect(page.getByRole('button', { name: /^By Down / })).toHaveCount(0)
  await page.getByRole('button', { name: 'Down', exact: true }).click()
  await expect(section(page, 'Down').getByRole('cell', { name: '1st Down', exact: true })).toBeVisible()
})

test('rushing retains its independent game-log drilldowns', async ({ page }) => {
  await ready(page, '/splits?p=test-player&cat=rushing&season=2023')
  await section(page, 'Season').getByRole('button', { name: '▸', exact: true }).click()
  await expect(section(page, 'Season').getByRole('link', { name: /2023 Wk 1/ })).toHaveAttribute('href', '/games/2023_01_BUF_MIA')
  await expect(section(page, 'Season').getByRole('link', { name: /Wk 19/ })).toHaveCount(0)
})

test('defensive player counts and fractional sacks remain independent from offensive metrics', async ({ page }) => {
  await ready(page, '/splits?p=test-player&cat=defense&season=2023')
  await expect(summary(page).getByRole('cell', { name: '1.5', exact: true })).toBeVisible()
  await expect(section(page, 'vs Pass/Run').getByRole('cell', { name: 'vs Pass', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /^By Season / })).toHaveCount(0)
  await capture(page, 'splits-defense')
})

test('team defense reverses efficiency winners while preserving team comparison columns', async ({ page }) => {
  await mockSplits(page)
  for (const team of ['BUF', 'SF']) await page.route(url => url.pathname === `/api/teams/${team}/splits`, route => route.fulfill({ json: [
    ...teamSplits, ...teamSplits.map(row => ({ ...row, side: 'defense', epa_play: team === 'BUF' ? -0.2 : 0.2 })),
  ] }))
  await page.goto('/splits?mode=teams&t=BUF,SF&side=defense&season=2023')
  await expect(page.getByRole('status')).toHaveCount(0)
  const table = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Team', exact: true }) })
  await expect(table.getByRole('cell', { name: '-0.200', exact: true })).toHaveClass(/text-data-win/)
  await expect(table.getByRole('cell', { name: '+0.200', exact: true })).not.toHaveClass(/text-data-win/)
  await capture(page, 'splits-team-defense')
})

test('empty-state examples and entity search still build comparisons', async ({ page }) => {
  await mockSplits(page)
  await page.goto('/splits')
  await expect(page.getByText('Compare anyone, in any situation', { exact: true })).toBeVisible()
  await capture(page, 'splits-empty')
  await page.getByPlaceholder('+ Add player…').fill('Second quarterback')
  await page.getByRole('button', { name: /^Second quarterback/ }).click()
  await expect(page.getByRole('button', { name: 'Remove Second quarterback', exact: true })).toBeVisible()
  await expect(page.getByPlaceholder('+ Add player…')).toHaveValue('')
  await page.getByRole('button', { name: 'Remove Second quarterback', exact: true }).click()
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Remove Second quarterback', exact: true })).toBeVisible()
})

test('equal values receive no winner shading and valid empty situation filters stay empty', async ({ page }) => {
  await mockSplits(page)
  await page.route(url => url.pathname === '/api/players/other-player/passing-splits', route => route.fulfill({ json: passingFixture(offensiveSplits, 'other-player') }))
  await page.goto('/splits?p=test-player,other-player&season=2023')
  await expect(summary(page).getByRole('cell', { name: '250', exact: true })).toHaveCount(2)
  for (const cell of await summary(page).getByRole('cell', { name: '250', exact: true }).all()) await expect(cell).not.toHaveClass(/text-data-win/)
  await page.getByRole('button', { name: 'Under Pressure', exact: true }).click()
  await expect(page.getByText('No split statistics for this selection.', { exact: true })).toBeVisible()
})

test('leaving before the search delay finishes clears the pending search timer', async ({ page }) => {
  await page.clock.install()
  await mockSplits(page)
  const searches: string[] = []
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/search') searches.push(request.url()) })
  await page.goto('/splits')
  await page.getByPlaceholder('+ Add player…').fill('Second quarterback')
  await page.getByRole('link', { name: 'Scores', exact: true }).click()
  await expect(page.locator('main')).toBeVisible()
  await page.clock.fastForward(500)
  expect(searches).toEqual([])
})
