import { expect, type Page } from '@playwright/test'
import { test } from './fixtures/scores'
import { gameDetail, gameLineup, lineupPlayer, mockGame, playerChart } from './fixtures/gameDetail'
import type { GameLineup, LineupPlayer } from '../src/types'

const formations = {
  standard: {
    offense: ['WR', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT', 'QB', 'RB', 'FB'],
    defense: ['DE', 'DT', 'DT', 'DE', 'OLB', 'MLB', 'CB', 'CB', 'FS', 'SS', 'NB'],
  },
  jumbo: {
    offense: ['LT', 'LG', 'C', 'RG', 'RT', 'OL', 'WR', 'TE', 'QB', 'RB', 'FB'],
    defense: ['DE', 'DT', 'LB', 'LB', 'LB', 'LB', 'LB', 'LB', 'CB', 'CB', 'S'],
  },
  spread: {
    offense: ['WR', 'WR', 'WR', 'WR', 'WR', 'LT', 'C', 'RT', 'TE', 'QB', 'RB'],
    defense: ['DE', 'DT', 'DE', 'LB', 'LB', 'CB', 'CB', 'NB', 'DB', 'FS', 'SS'],
  },
}

function fullLineup(formation: keyof typeof formations): GameLineup {
  const makePlayers = (team: string, positions: string[], unit: string): LineupPlayer[] => positions.map((position, i) => ({
    ...lineupPlayer, team, position, player_id: `${team}-${unit}-${i}`, position_group: null,
    player_name: `Player ${unit} ${i} Longlastname`, jersey_number: 10 + i,
    rating: 8.9, scored_td: true,
  }))
  return { ...gameLineup, teams: gameLineup.teams.map(team => ({
    ...team, offense: makePlayers(team.team, formations[formation].offense, 'offense'),
    defense: makePlayers(team.team, formations[formation].defense, 'defense'),
  })) }
}

async function fieldProblems(page: Page) {
  return page.locator('.fieldbox').evaluate(field => {
    const bounds = field.getBoundingClientRect()
    const nodes = Array.from(field.querySelectorAll<HTMLButtonElement>('.player'))
    const problems: string[] = []
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i].getBoundingClientRect()
      if (a.width < 44 || a.height < 44) problems.push(`small target ${i}`)
      if (a.left < bounds.left - 1 || a.right > bounds.right + 1 || a.top < bounds.top || a.bottom > bounds.bottom) problems.push(`outside field ${i}`)
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j].getBoundingClientRect()
        if (a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top) problems.push(`overlap ${i}/${j}`)
      }
    }
    return problems
  })
}

async function blockedPlayers(page: Page) {
  return page.locator('.fieldbox .player').evaluateAll(nodes => nodes.flatMap((node, i) => {
    node.scrollIntoView({ block: 'center', behavior: 'instant' })
    const box = node.getBoundingClientRect()
    const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2)
    return hit && node.contains(hit) ? [] : [`blocked player ${i}`]
  }))
}

for (const width of [320, 390, 760, 1280]) {
  for (const formation of Object.keys(formations) as (keyof typeof formations)[]) {
    test(`${formation} lineup keeps 22 player targets separate at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await mockGame(page, gameDetail, fullLineup(formation))
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await page.goto(`/games/${gameDetail.game_id}`)
      await page.getByRole('button', { name: 'Lineup', exact: true }).click()
      await expect(page.locator('.fieldbox .player')).toHaveCount(22)
      const directory = process.env.LINEUP_SPACING_CAPTURE
      if (directory) await page.screenshot({ path: `${directory}/${formation}-${width}.png`, fullPage: true, animations: 'disabled' })
      expect(await fieldProblems(page)).toEqual([])
      expect(await blockedPlayers(page)).toEqual([])
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await page.getByRole('button', { name: 'Bills ball' }).click()
      expect(await fieldProblems(page)).toEqual([])
      expect(await blockedPlayers(page)).toEqual([])
    })
  }
}

test('ratings explanation stays outside the field and long-name charts fit a narrow phone', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 })
  await mockGame(page, gameDetail, fullLineup('standard'))
  await page.goto(`/games/${gameDetail.game_id}`)
  await page.getByRole('button', { name: 'Lineup', exact: true }).click()
  const help = page.getByRole('button', { name: 'About game ratings', exact: true })
  await help.click()
  const explanation = page.getByRole('region', { name: 'Game ratings explanation' })
  await expect(explanation).toBeVisible()
  const panel = (await explanation.boundingBox())!
  const field = (await page.locator('.fieldbox').boundingBox())!
  expect(panel.y + panel.height).toBeLessThanOrEqual(field.y)
  expect(panel.x).toBeGreaterThanOrEqual(0)
  expect(panel.x + panel.width).toBeLessThanOrEqual(320)
  const captureDirectory = process.env.LINEUP_SPACING_CAPTURE
  if (captureDirectory) await page.screenshot({ path: `${captureDirectory}/help-phone.png`, fullPage: true, animations: 'disabled' })
  await help.click()
  await expect(explanation).toHaveCount(0)
  // Both pass and run map panels retain room alongside a full player name.
  for (const role of ['passer', 'rusher']) {
    await page.route(url => url.pathname.endsWith('/chart'), route => route.fulfill({ json: {
      ...playerChart, role, events: role === 'rusher'
        ? [{ ...playerChart.events[0], role, lane: 'left tackle', yards: 12 }]
        : playerChart.events,
    } }))
    await page.locator(`.fieldbox .player[aria-label$=", ${role === 'passer' ? 'QB' : 'RB'}"]`).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.locator('.tmap')).toBeVisible()
    expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
    const close = dialog.getByRole('button', { name: 'Close player chart' })
    const box = (await close.boundingBox())!
    expect(box.width).toBeGreaterThanOrEqual(44)
    expect(box.height).toBeGreaterThanOrEqual(44)
    expect(box.x + box.width).toBeLessThanOrEqual(320)
    const directory = process.env.LINEUP_SPACING_CAPTURE
    if (directory) await page.screenshot({ path: `${directory}/${role}-phone.png`, animations: 'disabled' })
    await dialog.locator('.modal-foot').scrollIntoViewIfNeeded()
    await expect(close).toBeInViewport()
    await close.click()
    await expect(dialog).toHaveCount(0)
  }
})

test('player labels stay reachable by keyboard and unidentified positions do not stack', async ({ page }) => {
  const lineup = fullLineup('standard')
  lineup.teams[1].offense = lineup.teams[1].offense.map(player => ({ ...player, position: null }))
  await page.setViewportSize({ width: 320, height: 740 })
  await mockGame(page, gameDetail, lineup)
  await page.goto(`/games/${gameDetail.game_id}`)
  await page.getByRole('button', { name: 'Lineup', exact: true }).click()
  expect(await fieldProblems(page)).toEqual([])
  expect(await blockedPlayers(page)).toEqual([])
  const player = page.locator('.fieldbox .player').first()
  await player.focus()
  await expect(player).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
