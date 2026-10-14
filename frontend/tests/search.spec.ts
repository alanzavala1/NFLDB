import { expect, type Page, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { mockSplits } from './fixtures/splits'
import type { SearchResult } from '../src/types'

const player: SearchResult = { type: 'player', id: 'test-player', name: 'Test quarterback', position: 'QB', team: 'BUF', headshot_url: null }
const team: SearchResult = { type: 'team', id: 'BUF', name: 'Buffalo Bills', position: null, team: 'BUF', headshot_url: null }
type Surface = 'navigation' | 'splits'

async function setup(page: Page) {
  await mockSplits(page)
  await page.goto('/splits?season=2023')
  await expect(page.getByText('Compare anyone, in any situation', { exact: true })).toBeVisible()
}

async function field(page: Page, surface: Surface) {
  if (surface === 'navigation') {
    await page.getByRole('button', { name: /Search Ctrl K/ }).click()
    const panel = page.getByRole('dialog', { name: 'Search players or teams' })
    return { input: panel.getByRole('textbox'), panel }
  }
  const input = page.getByRole('textbox', { name: 'Add player', exact: true })
  return { input, panel: input.locator('..') }
}

function searches(page: Page) {
  const terms: string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname === '/api/search') terms.push(url.searchParams.get('q') ?? '')
  })
  return terms
}

for (const surface of ['navigation', 'splits'] as const) {
  test(`${surface} waits after rapid typing, trims the request, and supports one-character searches`, async ({ page }) => {
    await page.clock.install()
    await setup(page)
    await page.route(url => url.pathname === '/api/search', route => route.fulfill({ json: [player, team] }))
    const terms = searches(page)
    const { input, panel } = await field(page, surface)
    await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 1000)))
    await input.fill('Al')
    await input.fill('Alle')
    await input.fill(' Allen ')
    await expect(panel.getByRole('status')).toHaveText('Searching…')
    await expect(panel.getByText(/No results/)).toHaveCount(0)
    await page.clock.fastForward(299)
    expect(terms).toEqual([])
    await page.clock.fastForward(1)
    await expect.poll(() => terms).toEqual(['Allen'])
    await page.clock.resume()
    await expect(panel.getByRole('button', { name: /^Test quarterback/ })).toBeVisible()
    expect(terms).toEqual(['Allen'])
    await input.fill(' a ')
    await expect.poll(() => terms).toEqual(['Allen', 'a'])
    await expect(panel.getByRole('button', { name: /^Test quarterback/ })).toBeVisible()
    expect(terms).toEqual(['Allen', 'a'])
    await input.fill('   ')
    await page.clock.fastForward(500)
    await expect(panel.getByRole('status')).toHaveCount(0)
    await expect(panel.getByRole('button', { name: /^Test quarterback/ })).toHaveCount(0)
    expect(terms).toEqual(['Allen', 'a'])
  })

  test(`${surface} distinguishes a pending search from a successful empty result`, async ({ page }) => {
    await setup(page)
    const pending: Route[] = []
    await page.route(url => url.pathname === '/api/search', route => { pending.push(route) })
    const { input, panel } = await field(page, surface)
    await input.fill('Nobody')
    await expect.poll(() => pending.length).toBe(1)
    await expect(panel.getByRole('status')).toHaveText('Searching…')
    await expect(panel.getByText(/No results/)).toHaveCount(0)
    await pending[0].fulfill({ json: [] })
    await expect(panel.getByText(/No results for "Nobody"/)).toBeVisible()
    await expect(panel.getByRole('status')).toHaveCount(0)
    await expect(panel.getByRole('alert')).toHaveCount(0)
  })

  for (const nonJson of [false, true]) {
    test(`${surface} exposes ${nonJson ? 'non-JSON' : 'backend'} errors and retries the same search`, async ({ page }) => {
      await setup(page)
      let fail = true
      await page.route(url => url.pathname === '/api/search', route => route.fulfill(fail
        ? nonJson ? { status: 502, contentType: 'text/html', body: '<h1>Gateway error</h1>' }
          : { status: 503, json: { detail: 'Search is temporarily unavailable.' } }
        : { json: [player] }))
      const terms = searches(page)
      const { input, panel } = await field(page, surface)
      await input.fill('Allen')
      await expect(panel.getByRole('alert')).toContainText(nonJson ? 'Request failed (502). Please try again.' : 'Search is temporarily unavailable.')
      await expect(panel.getByText(/No results/)).toHaveCount(0)
      expect(terms).toEqual(['Allen', 'Allen'])
      fail = false
      await panel.getByRole('button', { name: 'Try again', exact: true }).click()
      await expect(panel.getByRole('button', { name: /^Test quarterback/ })).toBeVisible()
      await expect(panel.getByRole('alert')).toHaveCount(0)
      expect(terms).toEqual(['Allen', 'Allen', 'Allen'])
    })
  }

  test(`${surface} immediately hides old cached results and cancels a superseded pending request`, async ({ page }) => {
    await setup(page)
    const pending: Route[] = []
    await page.route(url => url.pathname === '/api/search', route => {
      const term = new URL(route.request().url()).searchParams.get('q')
      if (term === 'pending') { pending.push(route); return }
      return route.fulfill({ json: [{ ...player, name: term === 'new' ? 'New quarterback' : 'Old quarterback' }] })
    })
    const { input, panel } = await field(page, surface)
    await input.fill('old')
    await expect(panel.getByRole('button', { name: /^Old quarterback/ })).toBeVisible()
    await input.fill('pending')
    await expect(panel.getByRole('button', { name: /^Old quarterback/ })).toHaveCount(0)
    await expect.poll(() => pending.length).toBe(1)
    await input.fill('new')
    await expect.poll(() => pending[0].request().failure()?.errorText).toMatch(/ABORTED/)
    await pending[0].fulfill({ json: [{ ...player, name: 'Late quarterback' }] })
    await expect(panel.getByRole('button', { name: /^New quarterback/ })).toBeVisible()
    await expect(panel.getByRole('button', { name: /^Late quarterback/ })).toHaveCount(0)
  })

  test(`${surface} closing before the delay prevents a request and closing during a request cancels it`, async ({ page }) => {
    await page.clock.install()
    await setup(page)
    const pending: Route[] = []
    await page.route(url => url.pathname === '/api/search', route => { pending.push(route) })
    const terms = searches(page)
    let search = await field(page, surface)
    await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 1000)))
    await search.input.fill('Allen')
    await search.input.press('Escape')
    await page.clock.fastForward(500)
    expect(terms).toEqual([])
    search = surface === 'navigation' ? await field(page, surface) : search
    await search.input.focus()
    await search.input.fill('Mahomes')
    await page.clock.fastForward(300)
    await expect.poll(() => pending.length).toBe(1)
    await search.input.press('Escape')
    await expect.poll(() => pending[0].request().failure()?.errorText).toMatch(/ABORTED/)
    if (surface === 'navigation') await expect(page.getByRole('button', { name: /Search Ctrl K/ })).toBeFocused()
  })

  for (const empty of [false, true]) {
    test(`${surface} retains ${empty ? 'empty' : 'populated'} cached search results on failed refresh and retry recovers`, async ({ page }) => {
      await page.clock.install()
      await setup(page)
      let fail = false
      await page.route(url => url.pathname === '/api/search', route => route.fulfill(fail
        ? { status: 503, json: { detail: 'Search unavailable.' } } : { json: empty ? [] : [player] }))
      let search = await field(page, surface)
      await search.input.fill('Allen')
      if (empty) await expect(search.panel.getByText(/No results for "Allen"/)).toBeVisible()
      else await expect(search.panel.getByRole('button', { name: /^Test quarterback/ })).toBeVisible()
      await search.input.press('Escape')
      await page.clock.fastForward(61_000)
      await page.clock.resume()
      fail = true
      search = surface === 'navigation' ? await field(page, surface) : search
      await search.input.click()
      await search.input.fill('Allen')
      await expect(search.panel.getByRole('alert')).toContainText('Could not refresh search results. Showing the last successful result.')
      if (empty) await expect(search.panel.getByText(/No results for "Allen"/)).toBeVisible()
      else await expect(search.panel.getByRole('button', { name: /^Test quarterback/ })).toBeVisible()
      fail = false
      await search.panel.getByRole('button', { name: 'Try again', exact: true }).click()
      await expect(search.panel.getByRole('alert')).toHaveCount(0)
    })
  }
}

test('navigation and Splits share trimmed search cache while player/team filtering stays local', async ({ page }) => {
  await setup(page)
  await page.route(url => url.pathname === '/api/search', route => route.fulfill({ json: [player, team] }))
  const terms = searches(page)
  const inline = await field(page, 'splits')
  await inline.input.fill(' Allen ')
  await expect(inline.panel.getByRole('button', { name: /^Test quarterback/ })).toBeVisible()
  await expect(inline.panel.getByRole('button', { name: /^Buffalo Bills/ })).toHaveCount(0)
  await inline.input.press('Escape')
  const navigation = await field(page, 'navigation')
  await navigation.input.fill('Allen')
  await expect(navigation.panel.getByRole('button', { name: /^Buffalo Bills/ })).toBeVisible()
  await expect(navigation.panel.getByRole('button', { name: /^Test quarterback/ })).toBeVisible()
  expect(terms).toEqual(['Allen'])
  await navigation.input.press('Escape')
  await page.getByRole('button', { name: 'Teams', exact: true }).click()
  const teamInput = page.getByRole('textbox', { name: 'Add team', exact: true })
  await teamInput.fill('Allen')
  await expect(page.getByRole('button', { name: /^Buffalo Bills/ })).toBeVisible()
  expect(terms).toEqual(['Allen'])
  await page.getByRole('button', { name: /^Buffalo Bills/ }).click()
  await expect(page.getByRole('button', { name: 'Remove Buffalo Bills', exact: true })).toBeVisible()
})

test('a team-only match is an honest empty player picker and remains available to navigation', async ({ page }) => {
  await setup(page)
  await page.route(url => url.pathname === '/api/search', route => route.fulfill({ json: [team] }))
  const terms = searches(page)
  const inline = await field(page, 'splits')
  await inline.input.fill('BUF')
  await expect(inline.panel.getByText('No results for "BUF" among players.', { exact: true })).toBeVisible()
  const navigation = await field(page, 'navigation')
  await navigation.input.fill('BUF')
  await expect(navigation.panel.getByRole('button', { name: /^Buffalo Bills/ })).toBeVisible()
  expect(terms).toEqual(['BUF'])
  await navigation.panel.getByRole('button', { name: /^Buffalo Bills/ }).click()
  await expect(page).toHaveURL(/\/teams\/BUF$/)
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('navigation keyboard shortcuts and keyboard result selection still open player profiles on phones', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await setup(page)
  await page.route(url => url.pathname === '/api/search', route => route.fulfill({ json: [player] }))
  await page.keyboard.press('/')
  const dialog = page.getByRole('dialog', { name: 'Search players or teams' })
  await expect(dialog.getByRole('textbox')).toBeFocused()
  await dialog.getByRole('textbox').fill('Allen')
  await expect(dialog.getByRole('button', { name: /^Test quarterback/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await dialog.getByRole('textbox').press('Tab')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/players\/test-player$/)
  await expect(page.getByRole('button', { name: 'Game Log', exact: true })).toBeVisible()
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('dialog').getByRole('textbox')).toBeFocused()
})

test('clearing or leaving an inline search and changing mode cancels its unfinished request', async ({ page }) => {
  await setup(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === '/api/search', route => { pending.push(route) })
  const inline = await field(page, 'splits')
  for (const action of ['clear', 'mode', 'leave']) {
    const input = page.getByRole('textbox', { name: action === 'leave' ? 'Add team' : 'Add player', exact: true })
    await input.fill(action)
    await expect.poll(() => pending.length).toBe(action === 'clear' ? 1 : action === 'mode' ? 2 : 3)
    const request = pending.at(-1)!.request()
    if (action === 'clear') await input.fill('')
    else if (action === 'mode') await page.getByRole('button', { name: 'Teams', exact: true }).click()
    else await page.getByRole('link', { name: 'Scores', exact: true }).click()
    await expect.poll(() => request.failure()?.errorText).toMatch(/ABORTED/)
  }
  await expect(inline.panel).toHaveCount(0)
})

test('Splits examples reuse field results and cache each resolved name', async ({ page }) => {
  await setup(page)
  await page.route(url => url.pathname === '/api/search', route => {
    const name = new URL(route.request().url()).searchParams.get('q')!
    return route.fulfill({ json: [{ ...player, id: name === 'Josh Allen' ? 'test-player' : 'other-player', name }] })
  })
  const terms = searches(page)
  const inline = await field(page, 'splits')
  await inline.input.fill('Josh Allen')
  await expect(inline.panel.getByRole('button', { name: /^Josh Allen/ })).toBeVisible()
  await inline.input.press('Escape')
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Remove Josh Allen', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove Patrick Mahomes', exact: true })).toBeVisible()
  expect(terms).toEqual(['Josh Allen', 'Patrick Mahomes'])
})

for (const action of ['mode', 'leave']) {
  test(`an example cancels its unshared search on ${action} without adding late members`, async ({ page }) => {
    await setup(page)
    const pending: Route[] = []
    await page.route(url => url.pathname === '/api/search', route => { pending.push(route) })
    const terms = searches(page)
    await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
    await expect.poll(() => pending.length).toBe(1)
    if (action === 'mode') {
      await page.getByRole('button', { name: 'Teams', exact: true }).click()
      await expect(page.getByRole('button', { name: 'Teams', exact: true })).toHaveAttribute('aria-pressed', 'true')
    } else {
      await page.getByRole('link', { name: 'Scores', exact: true }).click()
      await expect(page.locator('main')).toBeVisible()
    }
    await expect.poll(() => pending[0].request().failure()?.errorText).toMatch(/ABORTED/)
    await pending[0].fulfill({ json: [player] })
    expect(terms).toEqual(['Josh Allen'])
    expect(new URL(page.url()).searchParams.has('p')).toBe(false)
  })
}

test('closing navigation leaves its shared search alive for an example still using it', async ({ page }) => {
  await page.clock.install()
  await setup(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === '/api/search', route => {
    if (new URL(route.request().url()).searchParams.get('q') === 'Josh Allen') { pending.push(route); return }
    return route.fulfill({ json: [{ ...player, id: 'other-player', name: 'Patrick Mahomes' }] })
  })
  const terms = searches(page)
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect.poll(() => pending.length).toBe(1)
  const navigation = await field(page, 'navigation')
  await navigation.input.fill('Josh Allen')
  await page.clock.fastForward(301)
  await navigation.input.press('Escape')
  await pending[0].fulfill({ json: [{ ...player, name: 'Josh Allen' }] })
  await expect(page.getByRole('button', { name: 'Remove Josh Allen', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove Patrick Mahomes', exact: true })).toBeVisible()
  expect(terms).toEqual(['Josh Allen', 'Patrick Mahomes'])
})

test('cancelling an example leaves its shared search alive for navigation still using it', async ({ page }) => {
  await page.clock.install()
  await mockSplits(page)
  await page.goto('/splits?mode=teams&t=BUF&season=2023')
  await page.getByRole('button', { name: 'Players', exact: true }).click()
  await expect(page.getByText('Compare anyone, in any situation', { exact: true })).toBeVisible()
  const pending: Route[] = []
  await page.route(url => url.pathname === '/api/search', route => { pending.push(route) })
  const terms = searches(page)
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect.poll(() => pending.length).toBe(1)
  const navigation = await field(page, 'navigation')
  await navigation.input.fill('Josh Allen')
  await page.clock.fastForward(301)
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Teams', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await pending[0].fulfill({ json: [{ ...player, name: 'Josh Allen' }] })
  await expect(navigation.panel.getByRole('button', { name: /^Josh Allen/ })).toBeVisible()
  expect(terms).toEqual(['Josh Allen'])
  expect(new URL(page.url()).searchParams.has('p')).toBe(false)
})

test('examples preserve best-effort selection when one name fails and the next resolves', async ({ page }) => {
  await setup(page)
  await page.route(url => url.pathname === '/api/search', route => {
    const name = new URL(route.request().url()).searchParams.get('q')
    return route.fulfill(name === 'Josh Allen'
      ? { status: 503, json: { detail: 'Search unavailable.' } }
      : { json: [{ ...player, id: 'other-player', name: 'Patrick Mahomes' }] })
  })
  const terms = searches(page)
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Remove Patrick Mahomes', exact: true })).toBeVisible()
  expect(new URL(page.url()).searchParams.get('p')).toBe('other-player')
  expect(terms).toEqual(['Josh Allen', 'Josh Allen', 'Patrick Mahomes'])
})

test('a newer example cancels the previous example and commits only its own members and category', async ({ page }) => {
  await setup(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === '/api/search', route => {
    const name = new URL(route.request().url()).searchParams.get('q')!
    if (name === 'Josh Allen') { pending.push(route); return }
    return route.fulfill({ json: [{ ...player, id: name === 'Justin Jefferson' ? 'test-player' : 'other-player', name }] })
  })
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect.poll(() => pending.length).toBe(1)
  await page.getByRole('button', { name: 'Jefferson vs Chase', exact: true }).click()
  await expect.poll(() => pending[0].request().failure()?.errorText).toMatch(/ABORTED/)
  await pending[0].fulfill({ json: [{ ...player, name: 'Late Allen' }] })
  await expect(page.getByRole('button', { name: 'Remove Justin Jefferson', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: "Remove Ja'Marr Chase", exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove Late Allen', exact: true })).toHaveCount(0)
  expect(new URL(page.url()).searchParams.get('cat')).toBe('receiving')
})

test('a shared example request is cancelled once its final navigation consumer closes', async ({ page }) => {
  await page.clock.install()
  await mockSplits(page)
  await page.goto('/splits?mode=teams&t=BUF&season=2023')
  await page.getByRole('button', { name: 'Players', exact: true }).click()
  await expect(page.getByText('Compare anyone, in any situation', { exact: true })).toBeVisible()
  const pending: Route[] = []
  await page.route(url => url.pathname === '/api/search', route => { pending.push(route) })
  await page.getByRole('button', { name: 'Allen vs Mahomes', exact: true }).click()
  await expect.poll(() => pending.length).toBe(1)
  const navigation = await field(page, 'navigation')
  await navigation.input.fill('Josh Allen')
  await page.clock.fastForward(301)
  await page.goBack()
  await expect(page.getByRole('button', { name: 'Teams', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await navigation.input.press('Escape')
  await expect.poll(() => pending[0].request().failure()?.errorText).toMatch(/ABORTED/)
})
