import { expect, type Page, type Route } from '@playwright/test'
import { test } from './fixtures/scores'
import { playerProfile } from './fixtures/playerProfile'
import { defensiveSplits, mockSplits, offensiveSplits, splitAnalytics, teamSplits } from './fixtures/splits'

const resources = {
  offense: { path: '/api/players/test-player/splits', label: 'Test quarterback offensive splits', json: offensiveSplits, url: '/splits?p=test-player&season=2023' },
  defense: { path: '/api/players/test-player/def-splits', label: 'Test quarterback defensive splits', json: defensiveSplits, url: '/splits?p=test-player&cat=defense&season=2023' },
  profile: { path: '/api/players/test-player', label: 'test-player player profile', json: playerProfile, url: '/splits?p=test-player&season=2023' },
  team: { path: '/api/teams/BUF/splits', label: 'Buffalo Bills team splits', json: teamSplits, url: '/splits?mode=teams&t=BUF&season=2023' },
  ranks: { path: '/api/team-analytics', label: 'opponent defensive ranks', json: splitAnalytics, url: '/splits?p=test-player&season=2023' },
}
function section(page: Page, name: string) {
  return page.getByRole('button', { name: new RegExp(`^By ${name} `) }).locator('..')
}
async function loaded(page: Page) {
  await expect(page.getByRole('status')).toHaveCount(0)
  await expect(section(page, 'Down').getByRole('cell', { name: '1st Down', exact: true })).toBeVisible()
}

test('offensive splits and game-log sections load independently', async ({ page }) => {
  await mockSplits(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === resources.offense.path, route => { pending.push(route) })
  await page.goto(resources.offense.url)
  await expect(section(page, 'Season').getByRole('cell', { name: /2023/ })).toBeVisible()
  await expect(section(page, 'Down').getByRole('status')).toHaveText('Loading split statistics…')
  await expect.poll(() => pending.length).toBeGreaterThan(0)
  for (const route of pending) await route.fulfill({ json: offensiveSplits })
  await loaded(page)
})

test('game records do not look empty while the profile is still loading', async ({ page }) => {
  await mockSplits(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === resources.profile.path, route => { pending.push(route) })
  await page.goto(resources.offense.url)
  await expect(section(page, 'Down').getByRole('cell', { name: '1st Down', exact: true })).toBeVisible()
  await expect(section(page, 'Season').getByRole('status')).toHaveText('Loading game records…')
  await expect(section(page, 'Season')).not.toContainText('No game records')
  for (const route of pending) await route.fulfill({ json: playerProfile })
  await expect(section(page, 'Season').getByRole('cell', { name: /2023/ })).toBeVisible()
  await loaded(page)
})

for (const [name, resource] of Object.entries(resources)) {
  test(`${name} failures show backend details and retry independently`, async ({ page }) => {
    await mockSplits(page)
    let fail = true
    const reads: string[] = []
    page.on('request', request => {
      const path = new URL(request.url()).pathname
      if (path.startsWith('/api/')) reads.push(path)
    })
    await page.route(url => url.pathname === resource.path, route => route.fulfill(fail
      ? { status: 503, json: { detail: 'Published data is temporarily unavailable.' } } : { json: resource.json }))
    await page.goto(resource.url)
    await expect(page.getByRole('alert')).toContainText(`Could not load ${resource.label}. Published data is temporarily unavailable.`)
    await expect(page.getByRole('status')).toHaveCount(0)
    if (name === 'offense') {
      await expect(section(page, 'Season').getByRole('cell', { name: /2023/ })).toBeVisible()
      await expect(section(page, 'Down')).toContainText('The split statistics are unavailable')
      await expect(section(page, 'Down')).not.toContainText('No split statistics')
    } else if (name === 'profile') {
      await expect(section(page, 'Down').getByRole('cell', { name: '1st Down', exact: true })).toBeVisible()
      await expect(section(page, 'Season')).toContainText('The game records are unavailable')
    } else if (name === 'ranks') await expect(section(page, 'Opponent').getByRole('cell', { name: /MIA/ })).toBeVisible()
    const initialReads = reads.length
    fail = false
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await loaded(page)
    expect(reads.slice(initialReads)).toEqual([resource.path])
  })
}

for (const name of ['offense', 'defense'] as const) {
  test(`${name} non-JSON errors use the shared readable fallback`, async ({ page }) => {
    await mockSplits(page)
    const resource = resources[name]
    await page.route(url => url.pathname === resource.path, route => route.fulfill({ status: 502, contentType: 'text/html', body: '<h1>Bad gateway</h1>' }))
    await page.goto(resource.url)
    await expect(page.getByRole('alert')).toContainText('Request failed (502). Please try again.')
  })
}

test('a failed comparison member leaves the other player and both game logs usable', async ({ page }) => {
  await mockSplits(page)
  await page.route(url => url.pathname === '/api/players/other-player/splits', route => route.fulfill({ status: 503, json: { detail: 'Unavailable.' } }))
  await page.goto('/splits?p=test-player,other-player&season=2023')
  await expect(page.getByRole('alert')).toContainText('Could not load Second quarterback offensive splits. Unavailable.')
  await expect(section(page, 'Down').getByRole('cell', { name: '1st Down', exact: true })).toBeVisible()
  await expect(section(page, 'Season').getByRole('cell', { name: /2023/ })).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
})

for (const [name, resource] of Object.entries(resources)) {
  test(`${name} empty successful results are distinct from failures`, async ({ page }) => {
    await mockSplits(page)
    const json = name === 'profile' ? { ...playerProfile, games: [] } : name === 'ranks' ? { season: 2023, league: [] } : []
    await page.route(url => url.pathname === resource.path, route => route.fulfill({ json }))
    await page.goto(resource.url)
    await expect(page.getByRole('status')).toHaveCount(0)
    await expect(page.getByRole('alert')).toHaveCount(0)
    if (name === 'profile') await expect(section(page, 'Season')).toContainText('No game records for this selection.')
    else if (name === 'ranks') await expect(section(page, 'Opponent').getByRole('cell', { name: '—', exact: true }).first()).toBeVisible()
    else await expect(section(page, 'Down')).toContainText('No split statistics for this selection.')
  })
}

test('offensive categories and career/season filters reuse one resource while defense uses its own cache', async ({ page }) => {
  await mockSplits(page)
  const reads: string[] = []
  page.on('request', request => { if (/\/(splits|def-splits)$/.test(new URL(request.url()).pathname)) reads.push(new URL(request.url()).pathname) })
  await page.goto(resources.offense.url)
  await loaded(page)
  const initialReads = reads.length
  await page.getByRole('button', { name: 'Rushing', exact: true }).click()
  await loaded(page)
  await page.getByRole('combobox', { name: 'Season' }).selectOption('0')
  await loaded(page)
  await page.getByRole('button', { name: 'Passing', exact: true }).click()
  await loaded(page)
  expect(reads).toHaveLength(initialReads)
  await page.getByRole('button', { name: 'Defense', exact: true }).click()
  await loaded(page)
  expect(reads.slice(initialReads)).toEqual([resources.defense.path])
  const afterDefense = reads.length
  await page.getByRole('button', { name: 'Passing', exact: true }).click()
  await loaded(page)
  await page.getByRole('button', { name: 'Defense', exact: true }).click()
  await loaded(page)
  expect(reads).toHaveLength(afterDefense)
})

test('teams in a player URL and players in a team URL do not trigger inactive queries', async ({ page }) => {
  await mockSplits(page)
  const reads: string[] = []
  page.on('request', request => { reads.push(new URL(request.url()).pathname) })
  await page.goto('/splits?p=test-player&t=BUF&season=2023')
  await loaded(page)
  expect(reads.filter(path => path.startsWith('/api/teams/'))).toEqual([])
  reads.length = 0
  await page.goto('/splits?mode=teams&p=test-player&t=BUF&season=2023')
  await loaded(page)
  expect(reads.filter(path => path.startsWith('/api/players/'))).toEqual([])
  expect(reads.filter(path => path === '/api/team-analytics')).toEqual([])
})

test('no comparison, career offense, and player defense start no opponent-rank request', async ({ page }) => {
  await mockSplits(page)
  const reads: string[] = []
  page.on('request', request => { reads.push(new URL(request.url()).pathname) })
  await page.goto('/splits?season=2023')
  await expect(page.getByText('Compare anyone, in any situation', { exact: true })).toBeVisible()
  expect(reads.filter(path => path.includes('/api/players/') || path === '/api/team-analytics')).toEqual([])
  await page.goto('/splits?p=test-player')
  await loaded(page)
  await page.goto(resources.defense.url)
  await loaded(page)
  expect(reads.filter(path => path === '/api/team-analytics')).toEqual([])
})

for (const [name, resource] of Object.entries(resources)) {
  test(`leaving cancels unfinished ${name} requests`, async ({ page }) => {
    await mockSplits(page)
    const pending: Route[] = []
    await page.route(url => url.pathname === resource.path, route => { pending.push(route) })
    await page.goto(resource.url)
    await expect.poll(() => pending.length).toBeGreaterThan(0)
    await page.getByRole('link', { name: 'Scores', exact: true }).click()
    await expect(page.locator('main')).toBeVisible()
    await expect(page.getByRole('combobox', { name: 'Season' })).toBeVisible()
    for (const route of pending) {
      await route.fulfill({ json: resource.json })
      await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
    }
  })
}

test('removing a comparison member cancels its requests and late results cannot return it', async ({ page }) => {
  await mockSplits(page)
  const pending: Route[] = []
  await page.route(url => ['/api/players/other-player', '/api/players/other-player/splits'].includes(url.pathname), route => { pending.push(route) })
  await page.goto('/splits?p=test-player,other-player&season=2023')
  await expect.poll(() => new Set(pending.map(route => new URL(route.request().url()).pathname)).size).toBe(2)
  await page.getByRole('button', { name: 'Remove other-player', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Remove other-player', exact: true })).toHaveCount(0)
  for (const route of pending) {
    await route.fulfill({ json: new URL(route.request().url()).pathname.endsWith('/splits') ? offensiveSplits : { ...playerProfile, player_name: 'Late player' } })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
  await loaded(page)
  await expect(page.getByText('Late player')).toHaveCount(0)
})

test('switching to defense cancels offensive splits and late data cannot replace defensive totals', async ({ page }) => {
  await mockSplits(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === resources.offense.path, route => { pending.push(route) })
  await page.goto(resources.offense.url)
  await expect(page.getByRole('button', { name: 'Remove Test quarterback', exact: true })).toBeVisible()
  await expect.poll(() => pending.length).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Defense', exact: true }).click()
  await loaded(page)
  for (const route of pending) {
    await route.fulfill({ json: offensiveSplits })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
  await expect(section(page, 'Down').getByRole('cell', { name: '1.5', exact: true }).first()).toBeVisible()
  await expect(section(page, 'Down').getByRole('columnheader', { name: /^Tackles/ })).toBeVisible()
})

test('comparison members keep separate cached totals when the first player is removed', async ({ page }) => {
  await mockSplits(page)
  const reads: string[] = []
  page.on('request', request => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/players/')) reads.push(path)
  })
  await page.goto('/splits?p=test-player,other-player&season=2023')
  await loaded(page)
  const summary = page.getByRole('table').filter({ has: page.getByRole('columnheader', { name: 'Player', exact: true }) })
  await expect(summary.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Test quarterback', exact: true }) }).getByRole('cell').nth(3)).toHaveText('250')
  await expect(summary.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Second quarterback', exact: true }) }).getByRole('cell').nth(3)).toHaveText('500')
  const initialReads = reads.length
  await page.getByRole('button', { name: 'Remove Test quarterback', exact: true }).click()
  await loaded(page)
  await expect(summary.getByRole('cell', { name: 'Second quarterback', exact: true })).toBeVisible()
  await expect(summary.getByRole('cell', { name: '500', exact: true })).toBeVisible()
  expect(reads).toHaveLength(initialReads)
})

test('switching modes cancels pending player resources and hides their late results', async ({ page }) => {
  await mockSplits(page)
  const pending: Route[] = []
  await page.route(url => [resources.offense.path, resources.profile.path].includes(url.pathname), route => { pending.push(route) })
  await page.goto('/splits?p=test-player&t=BUF&season=2023')
  await expect.poll(() => new Set(pending.map(route => new URL(route.request().url()).pathname)).size).toBe(2)
  await page.getByRole('button', { name: 'Teams', exact: true }).click()
  await loaded(page)
  await expect(page.getByRole('button', { name: 'Remove Buffalo Bills' })).toBeVisible()
  for (const route of pending) {
    await route.fulfill({ json: new URL(route.request().url()).pathname === resources.offense.path ? offensiveSplits : { ...playerProfile, player_name: 'Late player' } })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
  await expect(page.getByText('Late player')).toHaveCount(0)
})

test('team season changes cancel old splits and late responses cannot replace the new year', async ({ page }) => {
  await mockSplits(page)
  const pending: Route[] = []
  await page.route(url => url.pathname === resources.team.path && url.searchParams.get('season') === '2023', route => { pending.push(route) })
  await page.route(url => url.pathname === resources.team.path && url.searchParams.get('season') === '2022', route => route.fulfill({ json: teamSplits.map(row => ({ ...row, split_value: row.split_dim === 'game_script' ? 'trailing' : row.split_value })) }))
  await page.goto(resources.team.url)
  await expect.poll(() => pending.length).toBeGreaterThan(0)
  await page.getByRole('combobox', { name: 'Season' }).selectOption('2022')
  await loaded(page)
  await expect(section(page, 'Game Script').getByRole('cell', { name: 'Trailing', exact: true })).toBeVisible()
  for (const route of pending) {
    await route.fulfill({ json: teamSplits })
    await expect.poll(() => route.request().failure()?.errorText).toMatch(/ABORTED/)
  }
  await expect(section(page, 'Game Script').getByRole('cell', { name: 'Leading', exact: true })).toHaveCount(0)
})

for (const [name, resource] of Object.entries(resources)) {
  for (const empty of [false, true]) {
    test(`failed background ${name} refresh keeps ${empty ? 'empty' : 'populated'} cached results and can retry`, async ({ page }) => {
      await page.clock.install()
      await mockSplits(page)
      let fail = false
      const json = !empty ? resource.json : name === 'profile' ? { ...playerProfile, games: [] }
        : name === 'ranks' ? { season: 2023, league: [] } : []
      await page.route(url => url.pathname === resource.path, route => route.fulfill(fail
        ? { status: 503, json: { detail: 'Unavailable.' } } : { json }))
      await page.goto(resource.url)
      await expect(page.getByRole('status')).toHaveCount(0)
      if (empty && name !== 'profile' && name !== 'ranks') await expect(section(page, 'Down')).toContainText('No split statistics')
      else if (name === 'profile') await expect(section(page, 'Season')).toContainText(empty ? 'No game records' : '2023')
      else await loaded(page)
      await page.clock.fastForward(301_000)
      await page.clock.resume()
      await page.getByRole('link', { name: 'Leaders', exact: true }).click()
      await expect(page.getByRole('button', { name: 'By Position', exact: true })).toBeVisible()
      fail = true
      await page.goBack()
      await expect(page.getByRole('alert')).toContainText('Showing the last successful result.')
      if (empty && name !== 'profile' && name !== 'ranks') await expect(section(page, 'Down')).toContainText('No split statistics')
      else if (name === 'profile') await expect(section(page, 'Season')).toContainText(empty ? 'No game records' : '2023')
      else await loaded(page)
      fail = false
      await page.getByRole('button', { name: 'Try again' }).click()
      await expect(page.getByRole('alert')).toHaveCount(0)
    })
  }
}
