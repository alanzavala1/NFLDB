import type { Page } from '@playwright/test'
import type { GameDetail, GameLineup, GamePlayerStats, LineupPlayer, LineupTeam, PlayerChart } from '../../src/types'
import { game } from './scores'
import { mockProfile, playerGame } from './playerProfile'

export const gamePlayer: GamePlayerStats = {
  ...playerGame, player_id: 'test-player', player_name: 'Test quarterback', team: 'BUF',
}
export const gameDetail: GameDetail = {
  ...game, game_id: '2023_01_BUF_MIA', season: 2023, gameday: '2023-09-10',
  away_score: 17, home_score: 24, stadium: 'Test stadium',
  away: [gamePlayer], home: [], quarter_scores: [], win_prob: [], team_stats: [], scoring: [],
}
export const lineupPlayer: LineupPlayer = {
  player_id: 'home-player', pfr_player_id: null, player_name: 'Home quarterback',
  team: 'MIA', position: 'QB', position_group: 'QB', jersey_number: 1,
  headshot_url: null, rating: 7, raw_score: 3, plays_counted: 30,
  snaps: 60, snap_pct: 1, scored_td: false,
}
const homeTeam: LineupTeam = {
  team: 'MIA', side: 'home', avg_rating: 7, offense_avg: 7, defense_avg: 6,
  ol_grade: 6.5, offense_personnel: 'Test personnel', defense_personnel: 'Test defense',
  offense: [lineupPlayer], defense: [], rotation: [],
}
export const gameLineup: GameLineup = {
  game_id: gameDetail.game_id, season: 2023, week: 1, away_team: 'BUF', home_team: 'MIA',
  join_match_rate: 1, scoring: [], teams: [
    { ...homeTeam, team: 'BUF', side: 'away', offense: [{ ...lineupPlayer, team: 'BUF', player_id: 'test-player', player_name: 'Test quarterback' }] },
    homeTeam,
  ],
}
export const playerChart: PlayerChart = {
  game_id: gameDetail.game_id, player_id: lineupPlayer.player_id!,
  player_name: lineupPlayer.player_name, team: lineupPlayer.team, position: 'QB',
  role: 'passer', rating: 7, snap_pct: 1, stats: { attempts: 30, completions: 20, pass_yards: 250, pass_epa: 3 },
  events: [{ play_id: 1, qtr: 1, clock: '12:00', role: 'passer', lane: 'left',
    air_yards: 15, yards: 20, epa: 1, outcome: 'Complete', desc: 'Test completion' }],
}
export const gamePath = `/api/games/${gameDetail.game_id}`
export const lineupPath = `${gamePath}/lineup`
export const chartPath = `${gamePath}/players/home-player/chart`

export async function mockGame(page: Page, detail = gameDetail, lineup = gameLineup) {
  await mockProfile(page)
  await page.route('**/api/seasons', route => route.fulfill({ json: [{ season: 2023, status: 'loaded' }] }))
  await page.route(url => url.pathname.startsWith('/api/games/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/chart')) {
      const playerId = path.split('/').at(-2)!
      return route.fulfill({ json: { ...playerChart, player_id: playerId,
        stats: { ...playerChart.stats, pass_yards: playerId === 'test-player' ? 310 : 250 } } })
    }
    if (path.endsWith('/lineup')) return route.fulfill({ json: lineup })
    if (path === gamePath) return route.fulfill({ json: detail })
    return route.fulfill({ status: 404, json: { detail: 'Game not found.' } })
  })
  await page.route('**/api/schedule?*', route => route.fulfill({ json: [{ week: detail.week, games: [detail] }] }))
}
