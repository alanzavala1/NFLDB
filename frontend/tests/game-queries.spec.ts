import { expect, type Page, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { chartPath, gameDetail, gameLineup, gamePath, lineupPath, mockGame, playerChart } from './fixtures/gameDetail'

const gameUrl = `/games/${gameDetail.game_id}`
const resources = {
  game: { path: gamePath, label: 'game', json: gameDetail },
  lineup: { path: lineupPath, label: 'lineup', json: gameLineup },
  schedule: { path: '/api/schedule', label: 'game schedule', json: [{ week: 1, games: [gameDetail] }] },
  chart: { path: chartPath, label: 'player chart', json: playerChart },
}
async function openChart(page: Page, playerName = 'Home quarterback') {
  await page.getByRole('button', { name: 'Lineup', exact: true }).click()
  await page.getByTitle(playerName, { exact: true }).click()
  return page.getByRole('dialog')
}
async function gameLoaded(page: Page) {
  await expect(page.getByRole('button', { name: 'Lineup', exact: true })).toBeEnabled()
  await expect(page.locator('.rail .pg')).toHaveCount(1)
  await expect(page.getByRole('status')).toHaveCount(0)
}

// Exercise a change between game routes without unmounting through another page.
// Router observes this browser history event just as it observes back/forward.
async function changeGame(page: Page, url: string) {
  await page.evaluate(url => {
    window.history.pushState({ ...window.history.state, idx: window.history.state.idx + 1 }, '', url)
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }))
  }, url)
}

test('the main game can render while independent lineup and schedule requests are pending', async ({ page }) => {
  await mockGame(page)
  const pending: Route[] = []
  await page.route(url => [lineupPath, '/api/schedule'].includes(url.pathname), route => { pending.push(route) })
  await page.goto(gameUrl)
  await expect(page.getByRole('button', { name: 'Stats', exact: true })).toBeEnabled()
  await expect(page.getByText('Loading lineup…', { exact: true })).toBeVisible()
  await expect.poll(() => new Set(pending.map(route => new URL(route.request().url()).pathname)).size).toBe(2)
  for (const route of pending.filter(route => new URL(route.request().url()).pathname === lineupPath)) await route.fulfill({ json: gameLineup })
  await expect(page.getByText('Loading game schedule…', { exact: true })).toBeVisible()
  for (const route of pending.filter(route => new URL(route.request().url()).pathname === '/api/schedule')) await route.fulfill({ json: resources.schedule.json })
  await gameLoaded(page)
})

for (const [name, resource] of Object.entries(resources)) {
  test(`${name} failures display details and retry independently`, async ({ page }) => {
    await mockGame(page)
    let fail = true
    const reads: string[] = []
    page.on('request', request => { reads.push(new URL(request.url()).pathname) })
    await page.route(url => url.pathname === resource.path, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Published data is unavailable.' } } : { json: resource.json }))
    await page.goto(gameUrl)
    if (name === 'chart') await openChart(page)
    await expect(page.getByRole('alert')).toContainText(`Could not load ${resource.label}. Published data is unavailable.`)
    await expect(page.getByRole('status')).toHaveCount(0)
    if (name !== 'game') await expect(page.getByRole('button', { name: 'Stats', exact: true })).toBeEnabled()
    if (name === 'lineup') {
      await page.getByRole('button', { name: 'Lineup', exact: true }).click()
      await expect(page.getByText('Loading lineup…')).toHaveCount(0)
    }
    const initialReads = reads.length
    fail = false
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    if (name === 'chart') await expect(page.getByRole('dialog').getByText('Passing yards', { exact: true })).toBeVisible()
    else await gameLoaded(page)
    if (name !== 'game') expect(reads.slice(initialReads)).toEqual([resource.path])
  })
}

test('an unknown game is a readable server error with a retry', async ({ page }) => {
  await mockGame(page)
  await page.goto('/games/unknown-game')
  await expect(page.getByRole('alert')).toContainText('Could not load game. Game not found.')
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
})

for (const [name, resource] of [['game', resources.game], ['chart', resources.chart]] as const) {
  test(`${name} non-JSON failures use the shared fallback`, async ({ page }) => {
    await mockGame(page)
    await page.route(url => url.pathname === resource.path, route => route.fulfill({ status: 502, contentType: 'text/html', body: '<h1>Bad gateway</h1>' }))
    await page.goto(gameUrl)
    if (name === 'chart') await openChart(page)
    await expect(page.getByRole('alert')).toContainText('Request failed (502). Please try again.')
  })
}

test('successful empty lineup, schedule, and chart responses end loading honestly', async ({ page }) => {
  await mockGame(page, gameDetail, { ...gameLineup, teams: [] })
  await page.route('**/api/schedule?*', route => route.fulfill({ json: [] }))
  await page.goto(gameUrl)
  await page.getByRole('button', { name: 'Lineup', exact: true }).click()
  await expect(page.getByText('No lineup data is available for this game.')).toBeVisible()
  await expect(page.getByText('No other game results are available for this round.')).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  await page.getByRole('link', { name: 'Scores', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Season' })).toBeVisible()
  await mockGame(page)
  await page.route(url => url.pathname === chartPath, route => route.fulfill({ json: { ...playerChart, events: [], stats: {} } }))
  // A new document avoids intentionally fresh cached empty lineup data.
  await page.goto(gameUrl)
  await openChart(page)
  await expect(page.getByText('No chart data is available for this player in this game.')).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('player charts load only on selection, expose pending state, and reuse fresh data on reopening', async ({ page }) => {
  await mockGame(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === chartPath, route => { pending.push(route) })
  await page.goto(gameUrl)
  await gameLoaded(page)
  expect(pending).toHaveLength(0)
  await openChart(page)
  await expect(page.getByRole('status')).toHaveText('Loading player chart…')
  await expect.poll(() => pending.length).toBeGreaterThan(0)
  for (const route of pending) await route.fulfill({ json: playerChart })
  await expect(page.getByRole('dialog').getByText('250', { exact: true })).toBeVisible()
  const initialReads = pending.length
  await page.getByRole('button', { name: 'Close player chart' }).click()
  await openChart(page)
  await expect(page.getByRole('dialog').getByText('250', { exact: true })).toBeVisible()
  expect(pending).toHaveLength(initialReads)
})

test('charts for different players have separate cache entries', async ({ page }) => {
  await mockGame(page)
  await page.goto(gameUrl)
  await openChart(page)
  await expect(page.getByRole('dialog').getByText('250', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Bills ball' }).click()
  await openChart(page, 'Test quarterback')
  await expect(page.getByRole('dialog').getByText('310', { exact: true })).toBeVisible()
  await expect(page.getByRole('dialog').getByText('250', { exact: true })).toHaveCount(0)
})

test('a player without a canonical ID has no chart request or endless loading', async ({ page }) => {
  const home = gameLineup.teams.find(team => team.side === 'home')!
  await mockGame(page, gameDetail, { ...gameLineup, teams: [gameLineup.teams[0], {
    ...home, offense: [{ ...home.offense[0], player_id: null, pfr_player_id: 'pfr-only' }],
  }] })
  const charts: string[] = []
  page.on('request', request => { if (request.url().endsWith('/chart')) charts.push(request.url()) })
  await page.goto(gameUrl)
  await openChart(page)
  await expect(page.getByText('No chart is available for this player.')).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  expect(charts).toEqual([])
})

for (const [name, resource] of Object.entries(resources)) {
  test(`leaving cancels unfinished ${name} requests`, async ({ page }) => {
    await mockGame(page)
    const pending: Route[] = []
    await page.route(url => url.pathname === resource.path, route => { pending.push(route) })
    await page.goto(gameUrl)
    if (name === 'chart') await openChart(page)
    await expect.poll(() => pending.length).toBeGreaterThan(0)
    if (name === 'chart') {
      await page.keyboard.press('Escape')
      await expect(page.getByRole('dialog')).toHaveCount(0)
    } else {
      await page.getByRole('link', { name: 'Leaders', exact: true }).click()
      await expect(page.getByRole('combobox', { name: 'Season' })).toBeVisible()
    }
    for (const route of pending) {
      await route.fulfill({ json: resource.json })
      await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
    }
  })
}

for (const [name, resource] of Object.entries(resources)) {
  for (const empty of name === 'game' ? [false] : [false, true]) {
    test(`failed background ${name} refresh retains ${empty ? 'empty' : 'populated'} cached data`, async ({ page }) => {
      await page.clock.install()
      await mockGame(page)
      let fail = false
      const json = !empty ? resource.json : name === 'lineup' ? { ...gameLineup, teams: [] }
        : name === 'chart' ? { ...playerChart, stats: {}, events: [] } : []
      await page.route(url => url.pathname === resource.path, route => route.fulfill(fail
        ? { status: 503, json: { detail: 'Unavailable.' } } : { json }))
      await page.goto(gameUrl)
      if (name === 'chart') {
        await openChart(page)
        await expect(page.getByRole('dialog').getByText(empty ? 'No chart data is available for this player in this game.' : 'Passing yards', { exact: true })).toBeVisible()
      } else {
        if (name === 'lineup') {
          await page.getByRole('button', { name: 'Lineup', exact: true }).click()
          await expect(page.getByText(empty ? 'No lineup data is available for this game.' : 'Dolphins offense', { exact: true })).toBeVisible()
        } else if (empty) await expect(page.getByText('No other game results are available for this round.')).toBeVisible()
        else await gameLoaded(page)
      }
      await page.clock.fastForward(301_000)
      await page.clock.resume()
      if (name === 'chart') await page.keyboard.press('Escape')
      else {
        await page.getByRole('link', { name: 'Leaders', exact: true }).click()
        await expect(page.getByRole('combobox', { name: 'Season' })).toBeVisible()
      }
      fail = true
      if (name === 'chart') await openChart(page)
      else await page.goBack()
      await expect(page.getByRole('alert')).toContainText(`Could not refresh ${resource.label}. Showing the last successful result.`)
      if (name === 'lineup') {
        await page.getByRole('button', { name: 'Lineup', exact: true }).click()
        await expect(page.getByText(empty ? 'No lineup data is available for this game.' : 'Dolphins offense', { exact: true })).toBeVisible()
      } else if (name === 'chart') {
        await expect(page.getByRole('dialog').getByText(empty ? 'No chart data is available for this player in this game.' : 'Passing yards', { exact: true })).toBeVisible()
      } else if (empty) await expect(page.getByText('No other game results are available for this round.')).toBeVisible()
      else await expect(page.getByRole('button', { name: 'Stats', exact: true })).toBeEnabled()
      fail = false
      await page.getByRole('button', { name: 'Try again' }).click()
      await expect(page.getByRole('alert')).toHaveCount(0)
    })
  }
}

test('game links and browser back reuse game and season caches and keep navigation context', async ({ page }) => {
  await mockGame(page)
  const reads: string[] = []
  page.on('request', request => { reads.push(new URL(request.url()).pathname) })
  await page.goto('/?season=2023')
  await expect(page.locator(`a[href="${gameUrl}"]`).first()).toBeVisible()
  const scoresReads = reads.length
  await page.locator(`a[href="${gameUrl}"]`).first().click()
  await gameLoaded(page)
  expect(reads.slice(scoresReads).filter(path => path === '/api/schedule')).toEqual([])
  const initialReads = reads.length
  await page.locator('main a[href="/players/test-player"]').first().click()
  await expect(page).toHaveURL(/\/players\/test-player$/)
  await expect(page.getByText('Regular Season', { exact: true })).toBeVisible()
  await expect(page.getByText('Test quarterback', { exact: true })).toBeVisible()
  const state = await page.evaluate(() => window.history.state.usr)
  expect(state.fromGame).toMatchObject({ gameId: gameDetail.game_id, season: 2023, week: 1, awayTeam: 'BUF', homeTeam: 'MIA' })
  await page.goBack()
  await gameLoaded(page)
  expect(reads.slice(initialReads).filter(path => [gamePath, lineupPath, '/api/schedule'].includes(path))).toEqual([])
})

test('route changes isolate games and reset the lineup tab instead of showing an old game', async ({ page }) => {
  await mockGame(page)
  const nextGame = { ...gameDetail, game_id: '2023_19_BUF_MIA', week: 19, game_type: 'WC', stadium: 'Playoff stadium' }
  const pending: Route[] = []
  await page.route(url => url.pathname === `/api/games/${nextGame.game_id}`, route => { pending.push(route) })
  await page.route(url => url.pathname === `/api/games/${nextGame.game_id}/lineup`, route => route.fulfill({ json: { ...gameLineup, game_id: nextGame.game_id, week: 19 } }))
  await page.goto(gameUrl)
  await gameLoaded(page)
  await page.getByRole('button', { name: 'Lineup', exact: true }).click()
  await changeGame(page, `/games/${nextGame.game_id}`)
  await expect(page.getByText('Loading game…', { exact: true })).toBeVisible()
  await expect(page.getByText(/Test stadium/)).toHaveCount(0)
  await expect.poll(() => pending.length).toBeGreaterThan(0)
  for (const route of pending) await route.fulfill({ json: nextGame })
  await expect(page.getByText(/Playoff stadium/).first()).toBeVisible()
  await expect(page.getByText('Dolphins offense', { exact: true })).toHaveCount(0)
  await page.goBack()
  await expect(page.getByText(/Test stadium/).first()).toBeVisible()
  await expect(page.getByText('Dolphins offense', { exact: true })).toHaveCount(0)
})

test('late detail and lineup responses from the previous game cannot replace the new game', async ({ page }) => {
  await mockGame(page)
  const pending: Route[] = []
  await page.route(url => [gamePath, lineupPath].includes(url.pathname), route => { pending.push(route) })
  const nextGame = { ...gameDetail, game_id: '2023_02_BUF_MIA', week: 2, stadium: 'Second stadium' }
  await page.route(url => url.pathname === `/api/games/${nextGame.game_id}`, route => route.fulfill({ json: nextGame }))
  await page.route(url => url.pathname === `/api/games/${nextGame.game_id}/lineup`, route => route.fulfill({ json: { ...gameLineup, game_id: nextGame.game_id, week: 2 } }))
  await page.goto(gameUrl)
  await expect.poll(() => new Set(pending.map(route => new URL(route.request().url()).pathname)).size).toBe(2)
  await changeGame(page, `/games/${nextGame.game_id}`)
  await expect(page.getByText(/Second stadium/).first()).toBeVisible()
  for (const route of pending) {
    await route.fulfill({ json: new URL(route.request().url()).pathname === gamePath ? gameDetail : gameLineup })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
  await expect(page.getByText(/Test stadium/)).toHaveCount(0)
  await expect(page.getByText(/Second stadium/).first()).toBeVisible()
})

test('the same player has separate charts for different games and reuses each cached result', async ({ page }) => {
  await mockGame(page)
  const nextGame = { ...gameDetail, game_id: '2023_02_BUF_MIA', week: 2, stadium: 'Second stadium' }
  await page.route(url => url.pathname === `/api/games/${nextGame.game_id}`, route => route.fulfill({ json: nextGame }))
  await page.route(url => url.pathname === `/api/games/${nextGame.game_id}/lineup`, route => route.fulfill({ json: { ...gameLineup, game_id: nextGame.game_id, week: 2 } }))
  let reads = 0
  page.on('request', request => { if (request.url().endsWith('/chart')) reads++ })
  await page.route(url => url.pathname === `/api/games/${nextGame.game_id}/players/home-player/chart`, route => route.fulfill({ json: {
    ...playerChart, game_id: nextGame.game_id, stats: { pass_yards: 580, attempts: 40 },
  } }))
  await page.goto(gameUrl)
  await openChart(page)
  await expect(page.getByRole('dialog').getByText('250', { exact: true })).toBeVisible()
  await changeGame(page, `/games/${nextGame.game_id}`)
  await expect(page.getByText(/Second stadium/).first()).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await openChart(page)
  await expect(page.getByRole('dialog').getByText('580', { exact: true })).toBeVisible()
  const initialReads = reads
  await page.goBack()
  await expect(page.getByText(/Test stadium/).first()).toBeVisible()
  await openChart(page)
  await expect(page.getByRole('dialog').getByText('250', { exact: true })).toBeVisible()
  expect(reads).toBe(initialReads)
})

test('Scores completes a pending schedule transition and Games reuses its result', async ({ page }) => {
  await mockGame(page)
  const pending: Route[] = []
  await page.route('**/api/schedule?*', route => { pending.push(route) })
  await page.goto(gameUrl)
  await expect(page.getByText('Loading game schedule…')).toBeVisible()
  await expect.poll(() => pending.length).toBeGreaterThan(0)
  await page.getByRole('link', { name: 'Scores', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Season' })).toBeVisible()
  await expect(page.getByText('Loading schedule...', { exact: true })).toBeVisible()
  // A gap between observers can cancel/restart the request. Fulfill the routes
  // after the destination has mounted, then verify the resulting shared cache.
  for (const route of pending) await route.fulfill({ json: resources.schedule.json })
  await expect(page.locator(`a[href="${gameUrl}"]`).first()).toBeVisible()
  const initialReads = pending.length
  await page.locator(`a[href="${gameUrl}"]`).first().click()
  await gameLoaded(page)
  expect(pending).toHaveLength(initialReads)
})

test('the existing live overlay supplies scores while ordinary detail data is uncharted', async ({ page }) => {
  await mockGame(page, { ...gameDetail, away: [], away_score: null, home_score: null })
  await page.route('**/api/live/scoreboard', route => route.fulfill({ json: {
    games: [{ game_id: gameDetail.game_id, away_team: 'BUF', home_team: 'MIA', gameday: '2023-09-10',
      state: 'in', away_score: 10, home_score: 14, period: 2, clock: '5:00', possession: 'BUF', detail: 'Live',
      away_periods: [7, 3], home_periods: [7, 7], down_distance: null, red_zone: false,
      last_play: null, away_timeouts: 3, home_timeouts: 2, leaders: [], }],
    source: 'espn', poll_after: null, fetched_at: '2026-10-13T12:00:00Z',
  } }))
  await page.goto(gameUrl)
  await expect(page.getByText('Q2 · 5:00', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Lineup', exact: true })).toBeDisabled()
  await expect(page.locator('[aria-live="polite"]').first()).toContainText('10')
  await expect(page.locator('[aria-live="polite"]').first()).toContainText('14')
})
