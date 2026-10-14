import type { Page } from '@playwright/test'
import type { LiveGameOut, Scoreboard } from '../../src/types'
import { mockApi } from './scores'
import { gameDetail, gameLineup } from './gameDetail'

export const liveGame: LiveGameOut = {
  game_id: 'second-game', away_team: 'SF', home_team: 'KC', gameday: '2026-09-13',
  state: 'in', away_score: 14, home_score: 17, period: 3, clock: '5:42',
  possession: 'KC', detail: '3rd Quarter', away_periods: [7, 7, 0], home_periods: [7, 7, 3],
  down_distance: '2nd & 5', red_zone: false, last_play: 'Live fixture play',
  away_timeouts: 3, home_timeouts: 2, leaders: [],
}

export function liveBoard(index = 0, period: number | null = 10, changes: Partial<LiveGameOut> = {}): Scoreboard {
  return { games: [{ ...liveGame, ...changes }], source: 'live', poll_after: period,
    fetched_at: new Date(Date.parse('2026-10-14T18:00:00Z') + index * 1000).toISOString() }
}

export async function mockLivePages(page: Page) {
  await mockApi(page)
  await page.route(url => url.pathname === '/api/games/second-game', route => route.fulfill({ json: {
    ...gameDetail, game_id: 'second-game', season: 2026, gameday: liveGame.gameday,
    away_team: 'SF', home_team: 'KC', away_score: null, home_score: null, away: [], home: [],
  } }))
  await page.route(url => url.pathname === '/api/games/second-game/lineup', route => route.fulfill({ json: {
    ...gameLineup, game_id: 'second-game', season: 2026, away_team: 'SF', home_team: 'KC', teams: [], scoring: [],
  } }))
}
