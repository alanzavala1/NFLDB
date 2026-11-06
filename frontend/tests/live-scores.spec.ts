import { expect, type Locator, type Page, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { liveBoard, mockLivePages } from './fixtures/liveScores'
import type { Scoreboard } from '../src/types'

function header(page: Page) {
  return page.getByRole('button', { name: 'Overview', exact: true }).locator('..').locator('..')
}
function score(page: Page) { return header(page).locator('[aria-live="polite"]') }

async function setup(page: Page) {
  await page.clock.install({ time: new Date('2026-10-14T18:00:00Z') })
  await page.clock.pauseAt(new Date('2026-10-14T18:01:00Z'))
  await mockLivePages(page)
}

// The clock is paused; advance notification timers while awaiting real HTTP/UI work.
async function show(page: Page, locator: Locator, text: string) {
  await expect.poll(async () => {
    await page.clock.runFor(100)
    return (await locator.allTextContents()).join(' ')
  }).toContain(text)
}

async function intercept(page: Page, respond: (index: number, route: Route) => unknown) {
  const requests: Route[] = []
  let completed = 0
  // StrictMode's cancelled mount probe may reach the interceptor. Do not consume
  // a fixture response or count it as a completed/active poll when that happens.
  await page.route(url => url.pathname === '/api/live/scoreboard', async route => {
    const index = completed
    requests.push(route)
    await respond(index, route)
    const response = await route.request().response()
    if (response && !(await response.finished()) && !route.request().failure()) completed = Math.max(completed, index + 1)
    else requests.splice(requests.indexOf(route), 1)
  })
  return requests
}

async function sequence(page: Page, payloads: Scoreboard[]) {
  return intercept(page, (index, route) => route.fulfill({ json: payloads[Math.min(index, payloads.length - 1)] }))
}

for (const period of [10, 60, 300]) {
  test(`live scores respect the server's ${period}-second interval and stop when it returns null`, async ({ page }) => {
    await setup(page)
    const requests = await sequence(page, [liveBoard(0, period), liveBoard(1, null, { clock: '5:00' })])
    await page.goto('/games/second-game')
    await show(page, score(page), 'Q3 · 5:42')
    expect(requests).toHaveLength(1)
    await page.clock.fastForward(period * 1000 - 1000)
    expect(requests).toHaveLength(1)
    await page.clock.fastForward(1500)
    await show(page, score(page), 'Q3 · 5:00')
    expect(requests).toHaveLength(2)
    await page.clock.fastForward(600_000)
    expect(requests).toHaveLength(2)
  })
}

test('polling adopts each new server interval instead of keeping the previous cadence', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(0, 60), liveBoard(1, 10, { clock: '5:00' }), liveBoard(2, null, { clock: '4:00' })])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.clock.fastForward(59_000)
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(1500)
  await show(page, score(page), 'Q3 · 5:00')
  await page.clock.fastForward(9000)
  expect(requests).toHaveLength(2)
  await page.clock.fastForward(1500)
  await show(page, score(page), 'Q3 · 4:00')
  expect(requests).toHaveLength(3)
})

test('a slow poll is never overlapped or cancelled by another timer and the next interval begins on completion', async ({ page }) => {
  await setup(page)
  const requests = await intercept(page, (index, route) => {
    if (index === 1) return
    return route.fulfill({ json: liveBoard(index, index === 0 ? 10 : null, { clock: index === 0 ? '5:42' : '4:00' }) })
  })
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.clock.fastForward(10_500)
  await expect.poll(() => requests.length).toBe(2)
  const slowRequest = requests[1]
  await page.clock.fastForward(40_000)
  expect(requests).toHaveLength(2)
  expect(requests[1]).toBe(slowRequest)
  expect(slowRequest.request().failure()).toBeNull()
  await slowRequest.fulfill({ json: liveBoard(2, 10, { clock: '5:00' }) })
  await show(page, score(page), 'Q3 · 5:00')
  await page.clock.fastForward(9000)
  expect(requests).toHaveLength(2)
  await page.clock.fastForward(1500)
  await show(page, score(page), 'Q3 · 4:00')
  expect(requests).toHaveLength(3)
})

test('older whole snapshots cannot rewind displayed games but their new polling interval is honored', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(5), liveBoard(1, 60, { clock: '8:00', away_score: 7 }), liveBoard(6, null, { clock: '4:00', away_score: 21 })])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.clock.fastForward(10_500)
  await expect.poll(() => requests.length).toBe(2)
  await requests[1].request().response().then(response => response?.finished())
  await page.clock.runFor(50)
  await show(page, score(page), 'Q3 · 5:42')
  await expect(score(page).getByText('14', { exact: true })).toBeVisible()
  await page.clock.fastForward(59_000)
  expect(requests).toHaveLength(2)
  await page.clock.fastForward(1500)
  await show(page, score(page), 'Q3 · 4:00')
  await expect(score(page).getByText('21', { exact: true })).toBeVisible()
})

for (const [name, changes] of [
  ['state', { state: 'pre', away_score: null, home_score: null, period: null, clock: null }],
  ['score', { away_score: 7, clock: '5:00' }],
  ['missing score', { away_score: null, clock: '5:00' }],
  ['period', { period: 2, clock: '1:00' }],
  ['clock', { clock: '6:00' }],
] as const) {
  test(`a newer snapshot cannot rewind a game's ${name}`, async ({ page }) => {
    await setup(page)
    const requests = await sequence(page, [liveBoard(0), liveBoard(1, 10, changes), liveBoard(2, null, { clock: '4:00' })])
    await page.goto('/games/second-game')
    await show(page, score(page), 'Q3 · 5:42')
    await page.clock.fastForward(10_500)
    await expect.poll(() => requests.length).toBe(2)
    await requests[1].request().response().then(response => response?.finished())
    await page.clock.runFor(50)
    await show(page, score(page), 'Q3 · 5:42')
    await expect(score(page).getByText('14', { exact: true })).toBeVisible()
    await page.clock.fastForward(10_500)
    await show(page, score(page), 'Q3 · 4:00')
    expect(requests).toHaveLength(3)
  })
}

test('quarter transitions allow a clock reset and completed games cannot restart', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(0), liveBoard(1, 10, { period: 4, clock: '15:00' }),
    liveBoard(2, 10, { state: 'post', period: 4, clock: '0:00', away_score: 21 }),
    liveBoard(3, null, { state: 'in', period: 4, clock: '0:10', away_score: 21 })])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.clock.fastForward(10_500)
  await show(page, score(page), 'Q4 · 15:00')
  await page.clock.fastForward(10_500)
  await show(page, header(page), 'Final')
  await page.clock.fastForward(10_500)
  await expect.poll(() => requests.length).toBe(4)
  await requests[3].request().response().then(response => response?.finished())
  await page.clock.runFor(50)
  await show(page, header(page), 'Final')
  await expect(score(page).getByText('21', { exact: true })).toBeVisible()
})

test('equal or unparseable timestamps and unknown clocks do not freeze legitimate updates', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(0), liveBoard(0, 10, { clock: '5:00' }),
    { ...liveBoard(1, 10, { clock: null, away_score: 21 }), fetched_at: 'unknown' },
    liveBoard(2, null, { clock: '4:00', away_score: 21 })])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.clock.fastForward(10_500)
  await show(page, score(page), 'Q3 · 5:00')
  await page.clock.fastForward(10_500)
  await show(page, score(page), '21')
  await expect(score(page).getByText('Q3', { exact: true })).toBeVisible()
  await page.clock.fastForward(10_500)
  await show(page, score(page), 'Q3 · 4:00')
  expect(requests).toHaveLength(4)
})

test('an authoritative empty board removes the old overlay and unmatched game IDs are ignored', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(0), { ...liveBoard(1, null), games: [
    { ...liveBoard().games[0], game_id: null },
  ] }])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.clock.fastForward(10_500)
  await show(page, header(page), 'Upcoming')
  await expect(page.getByText('Q3 · 5:42', { exact: true })).toHaveCount(0)
  await page.clock.fastForward(600_000)
  expect(requests).toHaveLength(2)
})

for (const cached of [false, true]) {
  for (const nonJson of [false, true]) {
    test(`${cached ? 'cached' : 'initial'} ${nonJson ? 'non-JSON' : 'HTTP'} failures keep the page usable and recover at the one-minute cadence`, async ({ page }) => {
      await setup(page)
      const requests = await intercept(page, (index, route) => {
        const failureIndex = cached ? 1 : 0
        if (index === failureIndex) return route.fulfill(nonJson
          ? { status: 502, contentType: 'text/html', body: '<h1>Gateway error</h1>' }
          : { status: 503, json: { detail: 'Live scores unavailable.' } })
        return route.fulfill({ json: liveBoard(index, index === 0 && cached ? 10 : null, { clock: index > failureIndex ? '4:00' : '5:42' }) })
      })
      await page.goto('/games/second-game')
      if (cached) {
        await show(page, score(page), 'Q3 · 5:42')
        await page.clock.fastForward(10_500)
      } else await show(page, header(page), 'Upcoming')
      const failures = cached ? 2 : 1
      await expect.poll(() => requests.length).toBe(failures)
      await requests.at(-1)!.request().response().then(response => response?.finished())
      await page.clock.runFor(50)
      if (cached) await show(page, score(page), 'Q3 · 5:42')
      await expect(page.getByRole('alert')).toHaveCount(0)
      await page.clock.fastForward(50_000)
      expect(requests).toHaveLength(failures)
      await page.clock.fastForward(11_000)
      await show(page, score(page), 'Q3 · 4:00')
      expect(requests).toHaveLength(failures + 1)
    })
  }
}

test('Scores and Game share one board, preserve ordering and keep the same next-poll deadline during navigation', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(5), liveBoard(1, null, { clock: '8:00', away_score: 7 })])
  await page.goto('/?season=2026&week=1')
  const gameLink = page.locator('a[href="/games/second-game"]').first()
  await show(page, gameLink, 'Q3 · 5:42')
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(4000)
  await gameLink.click()
  await show(page, score(page), 'Q3 · 5:42')
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(5000)
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(1500)
  await expect.poll(() => requests.length).toBe(2)
  await requests[1].request().response().then(response => response?.finished())
  await page.clock.runFor(50)
  await show(page, score(page), 'Q3 · 5:42')
  await page.goBack()
  await show(page, gameLink, 'Q3 · 5:42')
  expect(requests).toHaveLength(2)
})

test('leaving Scores/Game stops polling and re-entering uses the remaining cached deadline', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(0), liveBoard(1, null, { clock: '4:00' })])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.clock.fastForward(4000)
  await page.getByRole('link', { name: 'Standings', exact: true }).click()
  await show(page, page.getByText('No standings data for 2023.', { exact: true }), 'No standings data for 2023.')
  await page.goBack()
  await show(page, score(page), 'Q3 · 5:42')
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(5000)
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(1500)
  await show(page, score(page), 'Q3 · 4:00')
  expect(requests).toHaveLength(2)
  await page.getByRole('link', { name: 'Standings', exact: true }).click()
  await show(page, page.getByText('No standings data for 2023.', { exact: true }), 'No standings data for 2023.')
  await page.clock.fastForward(600_000)
  expect(requests).toHaveLength(2)
})

test('an idle null interval makes no background calls but a later mount checks the live source again', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [{ ...liveBoard(0, null), games: [] }, liveBoard(1, null)])
  await page.goto('/games/second-game')
  await show(page, header(page), 'Upcoming')
  await page.clock.fastForward(600_000)
  expect(requests).toHaveLength(1)
  await page.getByRole('link', { name: 'Standings', exact: true }).click()
  await show(page, page.getByText('No standings data for 2023.', { exact: true }), 'No standings data for 2023.')
  await page.goBack()
  await show(page, score(page), 'Q3 · 5:42')
  expect(requests).toHaveLength(2)
})

test('leaving during an unfinished live request aborts it and prevents its late result from populating the next visit', async ({ page }) => {
  await setup(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === '/api/live/scoreboard', route => { pending.push(route) })
  await page.goto('/games/second-game')
  await show(page, header(page), 'Upcoming')
  await expect.poll(() => pending.length).toBeGreaterThan(0)
  await page.getByRole('link', { name: 'Standings', exact: true }).click()
  await show(page, page.getByText('No standings data for 2023.', { exact: true }), 'No standings data for 2023.')
  for (const route of pending) {
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
    await route.fulfill({ json: liveBoard(100, null, { clock: '1:00', away_score: 50 }) })
  }
  await page.route(url => url.pathname === '/api/live/scoreboard', route => route.fulfill({ json: liveBoard(0, null) }))
  await page.goBack()
  await show(page, score(page), 'Q3 · 5:42')
  await expect(score(page).getByText('50', { exact: true })).toHaveCount(0)
})

test('re-entering after an HTTP failure cannot bypass the recovery delay', async ({ page }) => {
  await setup(page)
  const requests = await intercept(page, (index, route) => route.fulfill(index === 0
    ? { status: 503, json: { detail: 'Unavailable.' } } : { json: liveBoard(0, null) }))
  await page.goto('/games/second-game')
  await show(page, header(page), 'Upcoming')
  await requests[0].request().response().then(response => response?.finished())
  await page.clock.runFor(50)
  await page.clock.fastForward(30_000)
  await page.getByRole('link', { name: 'Standings', exact: true }).click()
  await show(page, page.getByText('No standings data for 2023.', { exact: true }), 'No standings data for 2023.')
  await page.goBack()
  await show(page, header(page), 'Upcoming')
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(20_000)
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(11_000)
  await show(page, score(page), 'Q3 · 5:42')
  expect(requests).toHaveLength(2)
})

test('focus and reconnect events do not create polls ahead of the server deadline', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(0, 60), liveBoard(1, null, { clock: '4:00' })])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.evaluate(() => {
    window.dispatchEvent(new Event('offline'))
    window.dispatchEvent(new Event('online'))
    window.dispatchEvent(new Event('focus'))
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await page.clock.fastForward(50_000)
  expect(requests).toHaveLength(1)
  await page.clock.fastForward(11_000)
  await show(page, score(page), 'Q3 · 4:00')
  expect(requests).toHaveLength(2)
})

test('an active polling board makes no requests while its route group is unmounted and refreshes when overdue on return', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(0), liveBoard(1, null, { clock: '4:00' })])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.getByRole('link', { name: 'Standings', exact: true }).click()
  await show(page, page.getByText('No standings data for 2023.', { exact: true }), 'No standings data for 2023.')
  await page.clock.fastForward(60_000)
  expect(requests).toHaveLength(1)
  await page.goBack()
  await show(page, score(page), 'Q3 · 4:00')
  expect(requests).toHaveLength(2)
})

test('background and offline events preserve the existing paced attempt instead of pausing the live loop', async ({ page }) => {
  await setup(page)
  const requests = await sequence(page, [liveBoard(0), liveBoard(1, null, { clock: '4:00' })])
  await page.goto('/games/second-game')
  await show(page, score(page), 'Q3 · 5:42')
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    window.dispatchEvent(new Event('offline'))
  })
  await page.clock.fastForward(10_500)
  await show(page, score(page), 'Q3 · 4:00')
  expect(requests).toHaveLength(2)
})
