import type { PlayerGame, PlayerProfile } from '../../src/types'

export const playerGame: PlayerGame = {
  game_id: '2023_01_BUF_MIA', season: 2023, week: 1, team: 'BUF', opponent: 'MIA',
  location: 'home', gameday: '2023-09-10', away_score: 17, home_score: 24,
  result: 'W', game_type: 'REG', position: 'QB', jersey_number: 17, headshot_url: null,
  attempts: 30, completions: 20, pass_yards: 250, pass_tds: 2,
  interceptions_thrown: 1, sacks_taken: 1, pass_epa: 3,
  targets: 0, receptions: 0, rec_yards: 0, rec_tds: 0, air_yards: 0, yac: 0, rec_epa: 0,
  carries: 3, rush_yards: 15, rush_tds: 0, rush_epa: 1,
  solo_tackles: 0, assist_tackles: 0, tackles_for_loss: 0, sacks: 0, qb_hits: 0,
  def_interceptions: 0, pass_breakups: 0, forced_fumbles: 0, fumble_recoveries: 0,
  fg_att: 0, fg_made: 0, xp_att: 0, xp_made: 0, punts: 0, punt_yards: 0,
  punt_returns: 0, punt_return_yards: 0, punt_return_tds: 0,
}

export const playerProfile: PlayerProfile = {
  player_id: 'test-player', player_name: 'Test quarterback', position: 'QB', team: 'BUF',
  jersey_number: 17, headshot_url: null, height: 76, weight: 230, age: 27,
  college: 'Test college', years_exp: 6, entry_year: 2018, rookie_year: 2018,
  draft_club: null, draft_number: null, games_played: 2, season_totals: {},
  games: [playerGame, {
    ...playerGame, game_id: '2023_19_BUF_MIA', week: 19, gameday: '2024-01-14',
    game_type: 'WC', pass_yards: 300,
  }],
  ngs: {}, snap_totals: {}, situational: {}, kicking: {}, wpa: {}, adv_stats: {},
  draft: null, combine: null, current_injury: null, depth: null, awards: [],
}
