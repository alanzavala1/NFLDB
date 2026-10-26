import type { Page } from '@playwright/test'
import type { PlayerSplit, DefensiveSplit } from '../../src/types'
import { mockProfile, playerProfile } from './playerProfile'
import { analyticsRow, teamSplit, teamProfile } from './teamProfile'

export const offensiveSplit: PlayerSplit = {
  season: 2023, category: 'passing', split_dim: 'down', split_value: '1', sort_order: 1,
  att: 20, cmp: 15, yards: 200, td: 2, interceptions: 0, air_yards: 150,
  yac: 50, first_downs: 10, epa: 4, success_pct: 60, cpoe: 3,
}
export const offensiveSplits: PlayerSplit[] = [offensiveSplit,
  { ...offensiveSplit, split_value: '3', sort_order: 3, att: 10, cmp: 5, yards: 50, td: 0, interceptions: 1, epa: -1 },
  { ...offensiveSplit, season: 2022, yards: 300 },
  { ...offensiveSplit, split_dim: 'game_script', split_value: 'leading' },
  { ...offensiveSplit, category: 'rushing', att: 3, cmp: 0, yards: 15, td: 0, interceptions: 0 },
]
export const defensiveSplit: DefensiveSplit = {
  season: 2023, split_dim: 'down', split_value: '1', sort_order: 1,
  tackles: 7, solo: 4, assists: 3, tfl: 2, sacks: 1.5, qb_hits: 3,
  interceptions: 1, pass_breakups: 2, forced_fumbles: 1,
}
export const defensiveSplits: DefensiveSplit[] = [defensiveSplit,
  { ...defensiveSplit, split_dim: 'vs_play', split_value: 'vs_pass' },
]
export const teamSplits = [teamSplit, { ...teamSplit, split_dim: 'down', split_value: '1', sort_order: 1 }]
export const splitAnalytics = { season: 2023, league: [{ ...analyticsRow, team: 'MIA' }] }

export async function mockSplits(page: Page) {
  await mockProfile(page)
  await page.route('**/api/seasons', route => route.fulfill({ json: [
    { season: 2026, status: 'loading' }, { season: 2025, status: 'available' },
    { season: 2024, status: 'loaded' }, { season: 2023, status: 'loaded' }, { season: 2022, status: 'loaded' },
  ] }))
  await page.route(url => /^\/api\/players\/[^/]+$/.test(url.pathname), route => {
    const id = new URL(route.request().url()).pathname.split('/').at(-1)!
    return route.fulfill({ json: { ...playerProfile, player_id: id,
      player_name: id === 'other-player' ? 'Second quarterback' : 'Test quarterback' } })
  })
  await page.route(url => /^\/api\/players\/[^/]+\/(splits|def-splits)$/.test(url.pathname), route => {
    const path = new URL(route.request().url()).pathname
    return route.fulfill({ json: path.endsWith('/def-splits') ? defensiveSplits
      : offensiveSplits.map(row => path.includes('/other-player/') ? { ...row, yards: (row.yards ?? 0) * 2 } : row) })
  })
  await page.route('**/api/players/*/receiving-splits', route => route.fulfill({ json: {
    player_id: new URL(route.request().url()).pathname.split('/').at(-2),
    scope: 'Qualified regular-season receiving; observed production on supplied games', seasons: [],
  } }))
  await page.route(url => url.pathname.startsWith('/api/teams/'), route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/splits')) return route.fulfill({ json: teamSplits })
    if (/^\/api\/teams\/[^/]+$/.test(url.pathname)) return route.fulfill({ json: { ...teamProfile, season: Number(url.searchParams.get('season')) } })
    return route.fulfill({ json: [] })
  })
  await page.route('**/api/team-analytics?*', route => route.fulfill({ json: { ...splitAnalytics,
    season: Number(new URL(route.request().url()).searchParams.get('season')) } }))
  await page.route('**/api/search?*', route => route.fulfill({ json: [{ type: 'player', id: 'other-player', name: 'Second quarterback', position: 'QB', team: 'BUF', headshot_url: null }] }))
}
