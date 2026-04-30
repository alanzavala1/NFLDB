const BASE = '/api'

export interface SeasonEntry {
  season: number
  status: 'loaded' | 'loading' | 'queued' | 'available' | 'error'
}

export interface Game {
  game_id: string
  season: number
  game_type: string
  week: number
  gameday: string
  gametime: string
  away_team: string
  home_team: string
  away_score: number | null
  home_score: number | null
  away_qb_name: string | null
  home_qb_name: string | null
  away_record: string | null
  home_record: string | null
  spread_line: number | null
  total_line: number | null
  roof: string | null
  surface: string | null
  temp: number | null
  wind: number | null
  stadium: string | null
  overtime: number | null
  div_game: number | null
}

export interface PlayerStats {
  player_id: string
  player_name: string
  team: string
  season: number
  week: number
  position: string | null
  jersey_number: number | null
  headshot_url: string | null
  attempts: number
  completions: number
  pass_yards: number
  pass_tds: number
  interceptions_thrown: number
  sacks_taken: number
  pass_epa: number
  targets: number
  receptions: number
  rec_yards: number
  rec_tds: number
  air_yards: number
  yac: number
  rec_epa: number
  carries: number
  rush_yards: number
  rush_tds: number
  rush_epa: number
  solo_tackles: number
  assist_tackles: number
  tackles_for_loss: number
  sacks: number
  qb_hits: number
  def_interceptions: number
  pass_breakups: number
  forced_fumbles: number
  fumble_recoveries: number
  fg_att: number
  fg_made: number
  xp_att: number
  xp_made: number
  punts: number
  punt_yards: number
  punt_returns: number
  punt_return_yards: number
  punt_return_tds: number
}

export interface QuarterScore {
  qtr: number
  away: number
  home: number
}

export interface GameDetail extends Game {
  away: PlayerStats[]
  home: PlayerStats[]
  quarter_scores: QuarterScore[]
}

export interface PlayerGame {
  game_id: string
  season: number
  week: number
  team: string
  opponent: string
  location: 'home' | 'away'
  gameday: string
  away_score: number | null
  home_score: number | null
  result: 'W' | 'L' | 'T' | null
  attempts: number
  completions: number
  pass_yards: number
  pass_tds: number
  interceptions_thrown: number
  targets: number
  receptions: number
  rec_yards: number
  rec_tds: number
  carries: number
  rush_yards: number
  rush_tds: number
  solo_tackles: number
  assist_tackles: number
  sacks: number
  def_interceptions: number
  pass_breakups: number
}

export interface NgsStats {
  // Passing
  avg_time_to_throw?: number
  adot?: number
  avg_completed_air_yards?: number
  cpoe?: number
  aggressiveness?: number
  expected_cmp_pct?: number
  ngs_passer_rating?: number
  // Rushing
  rush_yoe?: number
  rush_yoe_per_att?: number
  rush_efficiency?: number
  avg_time_to_los?: number
  pct_vs_8_defenders?: number
  // Receiving
  avg_separation?: number
  avg_cushion?: number
  avg_target_depth?: number
  avg_yac?: number
  avg_yac_above_exp?: number
  catch_pct?: number
  air_yards_share?: number
}

export interface SnapTotals {
  season: number
  offense_snaps: number
  defense_snaps: number
  st_snaps: number
  avg_offense_pct: number
  avg_defense_pct: number
  avg_st_pct: number
}

export interface PlayerProfile {
  player_id: string
  player_name: string
  position: string | null
  team: string | null
  jersey_number: number | null
  headshot_url: string | null
  height: string | null
  weight: number | null
  age: number | null
  college: string | null
  years_exp: number | null
  entry_year: number | null
  games_played: number
  season_totals: Record<string, number>
  games: PlayerGame[]
  ngs: Record<number, NgsStats>
  snap_totals: Record<number, SnapTotals>
}

export interface TeamGame {
    game_id: string
    season: number
    week: number
    gameday: string
    away_team: string
    home_team: string
    away_score: number | null
    home_score: number | null
    away_record: string | null
    home_record: string | null
    stadium: string | null
  }

  export interface TeamLeader {
  player_id: string
  player_name: string
  position: string | null
  headshot_url: string | null
  jersey_number: number | null
  games_played: number
  attempts: number
  completions: number
  pass_yards: number
  pass_tds: number
  interceptions_thrown: number
  sacks_taken: number
  carries: number
  rush_yards: number
  rush_tds: number
  targets: number
  receptions: number
  rec_yards: number
  rec_tds: number
  yac: number
  solo_tackles: number
  assist_tackles: number
  sacks: number
  tackles_for_loss: number
  qb_hits: number
  def_interceptions: number
  pass_breakups: number
  forced_fumbles: number
  fumble_recoveries: number
}

export interface TeamProfile {
  team: string
  season: number
  games: TeamGame[]
  leaders: TeamLeader[]
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export interface WeekGroup {
  week: number
  games: Game[]
}

export const api = {
  seasons: () => get<SeasonEntry[]>('/seasons'),
  loadSeason: (year: number) =>
    fetch(`${BASE}/seasons/${year}/load?force=false`, { method: 'POST' }).then(r => r.json()),
  schedule: (season: number) => get<WeekGroup[]>(`/schedule?season=${season}`),
  game: (gameId: string) => get<GameDetail>(`/games/${gameId}`),
  player: (playerId: string) => get<PlayerProfile>(`/players/${playerId}`),
  team: (abbrev: string, season: number) => get<TeamProfile>(`/teams/${abbrev}?season=${season}`),
}
