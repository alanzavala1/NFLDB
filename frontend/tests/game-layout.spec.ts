import { expect, type Page, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { gameDetail, lineupPath, mockGame, playerChart } from './fixtures/gameDetail'
import { layoutGame, layoutLineup } from './fixtures/gameLayout'

async function ready(page: Page) {
  await mockGame(page, layoutGame, layoutLineup)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto(`/games/${gameDetail.game_id}`)
  await expect(page.locator('.rail .pg')).toHaveCount(1)
  await expect(page.getByText('Away touchdown', { exact: true })).toBeVisible()
}
async function capture(page: Page, name: string, fullPage = true) {
  // Optional local before/after capture; artifacts never enter Git.
  const directory = process.env.GAME_LAYOUT_CAPTURE
  await page.screenshot({ path: directory ? `${directory}/${name}.png` : test.info().outputPath(`${name}.png`), fullPage, animations: 'disabled' })
}

for (const mobile of [false, true]) {
  test(`${mobile ? 'mobile' : 'desktop'} Game overview preserves scores, efficiency, leaders, plays, and chart`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await ready(page)
    await expect(page.getByText('Scoring by quarter', { exact: true })).toBeVisible()
    await expect(page.getByText('EPA / Play', { exact: true })).toBeVisible()
    await expect(page.getByText('+0.25', { exact: true })).toBeVisible()
    await expect(page.getByText('-0.15', { exact: true })).toBeVisible()
    await expect(page.getByText('Home interception', { exact: true })).toBeVisible()
    await expect(page.getByText('Decisive completion', { exact: true })).toBeVisible()
    await expect(page.getByText('Win Probability', { exact: true })).toBeVisible()
    await expect(page.locator('a[href="/players/home-player"]').first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    // Wait for the finite JS chart animation to finish before comparing layouts.
    let previous = '', stable = 0
    await expect.poll(async () => {
      const path = await page.locator('.recharts-area path').first().getAttribute('d') ?? ''
      stable = path && path === previous ? stable + 1 : 0
      previous = path
      return stable
    }, { intervals: [300], timeout: 5000 }).toBeGreaterThanOrEqual(3)
    await capture(page, `game-overview-${mobile ? 'mobile' : 'desktop'}`)
  })
}

test('all four player-stat sections retain qualification, ordering, ratios, and player links', async ({ page }) => {
  await ready(page)
  await page.getByRole('button', { name: 'Stats', exact: true }).click()
  const passing = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'C/ATT', exact: true }) })
  await expect(passing.getByRole('link')).toHaveText(['Test quarterback', 'Home quarterback'])
  await expect(passing.getByRole('row').filter({ has: page.getByRole('link', { name: 'Test quarterback', exact: true }) })).toContainText('8.3')
  const rushing = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Y/C', exact: true }) })
  await expect(rushing.getByRole('link')).toHaveText(['Away runner', 'Test quarterback', 'Home quarterback'])
  await expect(page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'REC/TGT', exact: true }) }).getByRole('link')).toHaveText(['Away runner'])
  await expect(page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'TOT', exact: true }) }).getByRole('row').filter({ has: page.getByRole('link', { name: 'Home defender' }) })).toContainText('7')
  await capture(page, 'game-stats')
})

for (const mobile of [false, true]) {
  test(`${mobile ? 'mobile' : 'desktop'} lineup and passing popup retain formation, grades, zones, and Escape close`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 })
    await ready(page)
    await page.getByRole('button', { name: 'Lineup', exact: true }).click()
    await expect(page.getByText('Dolphins offense', { exact: true })).toBeVisible()
    await expect(page.getByText('Bills defense', { exact: true })).toBeVisible()
    await expect(page.getByText('Away coach', { exact: true })).toBeVisible()
    await capture(page, `game-lineup-${mobile ? 'mobile' : 'desktop'}`)
    await page.getByTitle('Home quarterback', { exact: true }).click()
    const popup = page.getByRole('dialog')
    await expect(popup.getByText('Passing yards', { exact: true })).toBeVisible()
    await expect(popup.getByText('250', { exact: true })).toBeVisible()
    await expect(popup.getByText('1/1', { exact: true })).toBeVisible()
    await expect(popup.getByText('15.0', { exact: true })).toBeVisible()
    await capture(page, `game-popup-${mobile ? 'mobile' : 'desktop'}`, false)
    await page.keyboard.press('Escape')
    await expect(popup).toHaveCount(0)
    await page.getByRole('button', { name: 'Bills ball' }).click()
    await expect(page.getByText('Bills offense', { exact: true })).toBeVisible()
    await expect(page.getByTitle('Home defender', { exact: true })).toBeVisible()
  })
}

test('rushing and defensive charts retain role-specific maps and secondary receiving stats', async ({ page }) => {
  await ready(page)
  await page.route(url => url.pathname.endsWith('/players/home-runner/chart'), route => route.fulfill({ json: {
    ...playerChart, player_id: 'home-runner', role: 'rusher', stats: { carries: 3, rush_yards: 18, rush_epa: -1.2, targets: 2, receptions: 2, rec_yards: 25 },
    events: [{ ...playerChart.events[0], role: 'rusher', lane: 'left tackle', yards: 18, outcome: 'TD' }],
  } }))
  await page.getByRole('button', { name: 'Lineup', exact: true }).click()
  await page.getByTitle('Home runner', { exact: true }).click()
  const popup = page.getByRole('dialog')
  await expect(popup.getByText('Carry map', { exact: true })).toBeVisible()
  await expect(popup.getByText('Receiving', { exact: true })).toBeVisible()
  await expect(popup.getByText('25', { exact: true })).toBeVisible()
  await expect(popup.getByText('-1.2', { exact: true })).toBeVisible()
  await capture(page, 'game-rushing-popup', false)
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Bills ball' }).click()
  await page.route(url => url.pathname.endsWith('/players/home-defender/chart'), route => route.fulfill({ json: { ...playerChart, role: 'defender', stats: { tackles: 7, sacks: 1.5 }, events: [] } }))
  await page.getByTitle('Home defender', { exact: true }).click()
  await expect(popup.getByText('Defense', { exact: true })).toBeVisible()
  await expect(popup.getByText('1.5', { exact: true })).toBeVisible()
  await expect(popup.locator('.target-map')).toHaveCount(0)
})

test('win-probability tooltip preserves both teams, percentage, clock, and description', async ({ page }) => {
  await ready(page)
  const chart = page.locator('.recharts-wrapper')
  await chart.scrollIntoViewIfNeeded()
  const box = (await chart.boundingBox())!
  await chart.hover({ position: { x: box.width / 2, y: box.height / 2 } })
  const tooltip = page.locator('.recharts-tooltip-wrapper')
  await expect(tooltip).toContainText('BUF')
  await expect(tooltip).toContainText('MIA')
  await expect(tooltip).toContainText('%')
  await expect(tooltip).toContainText(/Q[1-4]/)
})

for (const tab of ['Overview', 'Stats']) {
  test(`${tab} player links keep keyboard focus when an independent lineup request finishes`, async ({ page }) => {
    await mockGame(page, layoutGame, layoutLineup)
    const pending: Route[] = []
    await page.route(url => url.pathname === lineupPath, route => { pending.push(route) })
    await page.goto(`/games/${gameDetail.game_id}`)
    await expect(page.getByText('Loading lineup…', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: tab, exact: true }).click()
    const player = page.locator('main a[href="/players/test-player"]').first()
    await player.focus()
    await expect(player).toBeFocused()
    await expect.poll(() => pending.length).toBeGreaterThan(0)
    for (const route of pending) await route.fulfill({ json: layoutLineup })
    await expect(page.locator('.rail .pg')).toHaveCount(1)
    await expect(page.getByText('Loading lineup…')).toHaveCount(0)
    await expect(player).toBeFocused()
  })
}
