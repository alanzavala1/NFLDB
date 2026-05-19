const BASE = '/api'

// NFL season year = calendar year the season starts (Sep onward = this year, Jan–Aug = last year)
export const CURRENT_NFL_SEASON = ((): number => {
  const now = new Date()
  return now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1
})()

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

export interface WinProbPlay {
  game_seconds_remaining: number
  qtr: number
  home_wp: number
  touchdown: number
  interception: number
  fumble_lost: number
  posteam: string
  desc: string
}

export interface GameDetail extends Game {
  away: PlayerStats[]
  home: PlayerStats[]
  quarter_scores: QuarterScore[]
  win_prob: WinProbPlay[]
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
  game_type: string
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
  yac: number
  air_yards: number
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
  fg_att: number
  fg_made: number
  xp_att: number
  xp_made: number
  punts: number
  punt_yards: number
}

export interface SituationalStats {
  lng_pass?: number
  lng_rush?: number
  lng_rec?: number
  rz_pass_att?: number
  rz_cmp?: number
  rz_pass_tds?: number
  rz_targets?: number
  rz_rec_tds?: number
  rz_carries?: number
  rz_rush_tds?: number
  third_pass_att?: number
  third_pass_fd?: number
  third_targets?: number
  third_rec_fd?: number
  third_carries?: number
  third_rush_fd?: number
  fd_pass?: number
  fd_rec?: number
  fd_rush?: number
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

export interface PlayerAdvStats {
  fumbles_lost?: number
  target_share?: number
  air_yards_share?: number
  stuff_rate?: number
  stuffed?: number
  carries_total?: number
}

export interface PlayerWpa {
  pass_wpa?: number
  rec_wpa?: number
  rush_wpa?: number
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
  situational: Record<number, SituationalStats>
  wpa: Record<number, PlayerWpa>
  adv_stats: Record<number, PlayerAdvStats>
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
  pass_epa: number | null
  carries: number
  rush_yards: number
  rush_tds: number
  rush_epa: number | null
  targets: number
  receptions: number
  rec_yards: number
  rec_tds: number
  air_yards: number | null
  yac: number
  rec_epa: number | null
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
  playoff_leaders: TeamLeader[]
}

export interface LeagueLeader {
  player_id: string
  player_name: string
  position: string | null
  team: string | null
  headshot_url: string | null
  games_played: number
  attempts: number
  completions: number
  pass_yards: number
  pass_tds: number
  interceptions_thrown: number
  sacks_taken: number
  pass_epa: number | null
  carries: number
  rush_yards: number
  rush_tds: number
  rush_epa: number | null
  targets: number
  receptions: number
  rec_yards: number
  rec_tds: number
  yac: number
  air_yards: number | null
  rec_epa: number | null
  solo_tackles: number
  assist_tackles: number
  tackles_for_loss: number
  sacks: number
  qb_hits: number
  def_interceptions: number
  pass_breakups: number
  forced_fumbles: number | null
  fumble_recoveries: number | null
  fg_att: number
  fg_made: number
  xp_att: number
  xp_made: number
  punts: number
  punt_yards: number
}

export interface RosterPlayer {
  player_id: string
  player_name: string
  position: string | null
  jersey_number: number | null
  headshot_url: string | null
}

export interface StandingsTeam {
  team: string
  w: number
  l: number
  t: number
  pct: number
  pf: number
  pa: number
  gb: string
  home: string
  away: string
  div: string
  strk: string
}

export interface DivisionStandings {
  division: string
  teams: StandingsTeam[]
}

export interface SearchResult {
  type: 'player' | 'team'
  id: string
  name: string
  position: string | null
  team: string | null
  headshot_url: string | null
}

export interface PlayerComparable {
  player_id: string
  player_name: string
  position: string | null
  team: string | null
  headshot_url: string | null
  similarity: number
  games: number
  first_season: number
  last_season: number
  pass_yards: number
  pass_tds: number
  rush_yards: number
  rush_tds: number
  carries: number
  rec_yards: number
  rec_tds: number
  targets: number
  att: number
  cmp: number
  ints: number
}

export interface WpaLeader {
  player_id: string
  player_name: string
  position: string | null
  team: string | null
  headshot_url: string | null
  wpa: number
  games_played: number
  attempts?: number
  carries?: number
  receptions?: number
}

export interface WpaLeaders {
  passing: WpaLeader[]
  rushing: WpaLeader[]
  receiving: WpaLeader[]
}

export interface TeamAnalyticsTeam {
  team: string
  games: number
  wins: number
  losses: number
  ties: number
  pf_total: number
  pa_total: number
  // Scoring
  ppg: number | null
  papg: number | null
  pt_diff_per_game: number | null
  pts_per_drive: number | null
  pts_per_drive_allowed: number | null
  // Drives / red zone / turnovers
  total_drives: number | null
  total_drives_allowed: number | null
  rz_td_pct: number | null
  rz_td_pct_allowed: number | null
  off_turnovers_total: number
  def_takeaways_total: number
  turnover_diff_per_game: number | null
  // Offense
  off_plays_count: number | null
  off_epa_play: number | null
  off_pass_epa: number | null
  off_rush_epa: number | null
  off_success_pct: number | null
  off_explosive_pct: number | null
  proe: number | null
  third_down_pct: number | null
  // Defense
  def_epa_play: number | null
  def_pass_epa: number | null
  def_rush_epa: number | null
  def_success_pct: number | null
  def_explosive_pct: number | null
  def_sack_pct: number | null
  third_down_stop_pct: number | null
  // Ranks (1 = best for team direction)
  ppg_rank: number | null
  pts_per_drive_rank: number | null
  off_epa_play_rank: number | null
  off_pass_epa_rank: number | null
  off_rush_epa_rank: number | null
  off_success_rank: number | null
  off_explosive_rank: number | null
  third_down_rank: number | null
  rz_td_rank: number | null
  proe_rank: number | null
  papg_rank: number | null
  pts_per_drive_allowed_rank: number | null
  def_epa_play_rank: number | null
  def_pass_epa_rank: number | null
  def_rush_epa_rank: number | null
  def_success_rank: number | null
  def_explosive_rank: number | null
  third_down_stop_rank: number | null
  rz_td_allowed_rank: number | null
  def_sack_rank: number | null
  pt_diff_rank: number | null
  to_diff_rank: number | null
}

export interface TeamAnalyticsResponse {
  season: number
  league: TeamAnalyticsTeam[]
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
  search: (q: string) => get<SearchResult[]>(`/search?q=${encodeURIComponent(q)}`),
  standings: (season: number) => get<DivisionStandings[]>(`/standings?season=${season}`),
  leaders: (season: number) => get<LeagueLeader[]>(`/leaders?season=${season}`),
  wpaLeaders: (season: number) => get<WpaLeaders>(`/wpa-leaders?season=${season}`),
  teamRoster: (team: string, season: number) => get<RosterPlayer[]>(`/teams/${team}/roster?season=${season}`),
  comparables: (playerId: string) => get<PlayerComparable[]>(`/players/${playerId}/comparables`),
  teamAnalytics: (season: number) => get<TeamAnalyticsResponse>(`/team-analytics?season=${season}`),
}
