import type { GameDetail, GameLineup, LineupPlayer, TeamGameStats, WinProbPlay } from '../../src/types'
import { gameDetail, gameLineup, gamePlayer, lineupPlayer } from './gameDetail'

const teamStats: TeamGameStats = {
  team: 'BUF', plays: 60, first_downs: 22, third_att: 10, third_conv: 6,
  fourth_att: 2, fourth_conv: 1, penalties: 4, penalty_yards: 30,
  turnovers: 1, epa_play: 0.25, success_pct: 55,
}
const play: WinProbPlay = {
  game_seconds_remaining: 3300, qtr: 1, home_wp: 0.55,
  touchdown: 0, interception: 0, fumble_lost: 0, posteam: 'MIA', desc: 'Opening completion',
}
export const layoutGame: GameDetail = {
  ...gameDetail, roof: 'outdoors', surface: 'grass', temp: 75, wind: 5, spread_line: -3, total_line: 42,
  away: [gamePlayer, { ...gamePlayer, player_id: 'away-back', player_name: 'Away runner', position: 'RB',
    attempts: 0, completions: 0, pass_yards: 0, pass_tds: 0, interceptions_thrown: 0, sacks_taken: 0,
    carries: 12, rush_yards: 100, rush_tds: 1, targets: 5, receptions: 4, rec_yards: 50, rec_tds: 1 }],
  home: [{ ...gamePlayer, player_id: 'home-player', player_name: 'Home quarterback', team: 'MIA', pass_yards: 300 },
    { ...gamePlayer, player_id: 'home-defender', player_name: 'Home defender', team: 'MIA', position: 'LB',
      attempts: 0, completions: 0, pass_yards: 0, carries: 0, solo_tackles: 4, assist_tackles: 3, sacks: 1.5 }],
  quarter_scores: [{ qtr: 1, away: 7, home: 7 }, { qtr: 2, away: 3, home: 7 }, { qtr: 3, away: 0, home: 3 }, { qtr: 4, away: 7, home: 7 }],
  team_stats: [teamStats, { ...teamStats, team: 'MIA', plays: 65, epa_play: -0.15, turnovers: 2 }],
  scoring: [{ qtr: 1, clock: '12:00', team: 'BUF', kind: 'TD', desc: '(12:00) (Shotgun) Away touchdown', away_score: 7, home_score: 0 }],
  win_prob: [play, { ...play, game_seconds_remaining: 3000, home_wp: 0.3, posteam: 'BUF', touchdown: 1, desc: 'Away touchdown' },
    { ...play, game_seconds_remaining: 1600, qtr: 2, home_wp: 0.7, posteam: 'BUF', interception: 1, desc: 'Home interception' },
    { ...play, game_seconds_remaining: 800, qtr: 4, home_wp: 0.9, posteam: 'MIA', desc: 'Decisive completion' },
    { ...play, game_seconds_remaining: 0, qtr: 4, home_wp: 1, desc: 'Game ends' }],
}
export const runner: LineupPlayer = {
  ...lineupPlayer, player_id: 'home-runner', player_name: 'Home runner', position: 'RB', position_group: 'RB', scored_td: true,
}
export const defender: LineupPlayer = {
  ...lineupPlayer, player_id: 'home-defender', player_name: 'Home defender', position: 'LB', position_group: 'LB',
}
export const layoutLineup: GameLineup = {
  ...gameLineup, away_coach: 'Away coach', home_coach: 'Home coach',
  scoring: [{ team: 'BUF', player_id: 'away-back', player_name: 'Away runner', kind: 'TD', qtr: 1, clock: '12:00', distance: 10, desc: 'Away touchdown' }],
  teams: gameLineup.teams.map(team => ({ ...team,
    offense: team.side === 'home' ? [...team.offense, runner] : team.offense,
    defense: team.side === 'home' ? [defender] : [{ ...defender, player_id: 'away-defender', player_name: 'Away defender', team: 'BUF', rating: null, plays_counted: 0 }],
    rotation: team.side === 'home' ? [runner, defender] : [],
  })),
}
