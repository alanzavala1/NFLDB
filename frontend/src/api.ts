/**
 * HTTP client + type re-exports.
 *
 * Every type below is derived from the Pydantic models in api/schemas/*.py
 * via the OpenAPI codegen pipeline:
 *
 *   api/schemas/*.py  →  emit_openapi.py  →  frontend/openapi.json
 *                                                  ↓ npm run gen-types
 *                                          src/types/api.d.ts
 *                                                  ↓
 *                                          src/types/index.ts (aliases)
 *
 * Backward-compatible aliases (SeasonEntry, WeekGroup, PlayerStats,
 * StandingsTeam, TeamAnalyticsTeam) are re-exported under the historical
 * names that the pages were already importing.
 */
import type {
  CombineData, DepthChartEntry, DivisionStandings, DraftInfo, Game,
  GameDetail, GamePlayerStats, InjuryStatus, KickingStats, LeagueLeader, NgsStats,
  PlayerAdvStats, PlayerAward, PlayerComparable, PlayerGame, PlayerProfile, PlayerWpa,
  RosterPlayer, ScheduleWeek, SearchResult, SeasonStatus, SituationalStats,
  SnapTotals, StandingsRow, TeamAnalyticsResponse, TeamAnalyticsRow,
  TeamGame, TeamLeader, TeamProfile, WinProbPlay, WpaLeader, WpaLeaders,
} from './types'

const BASE = '/api'

// NFL season year = calendar year the season starts (Sep onward = this year, Jan–Aug = last year)
export const CURRENT_NFL_SEASON = ((): number => {
  const now = new Date()
  return now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1
})()

// ── Generated types, re-exported under both their current names and the
//     historical aliases so pages don't have to be touched on every rename ───
export type {
  CombineData, DepthChartEntry, DivisionStandings, DraftInfo, Game,
  GameDetail, InjuryStatus, KickingStats, LeagueLeader, NgsStats, PlayerAdvStats,
  PlayerAward, PlayerComparable, PlayerGame, PlayerProfile, PlayerWpa,
  RosterPlayer, SearchResult, SituationalStats, SnapTotals, TeamGame,
  TeamLeader, TeamProfile, WinProbPlay, WpaLeader, WpaLeaders,
}

export type SeasonEntry        = SeasonStatus
export type WeekGroup          = ScheduleWeek
export type PlayerStats        = GamePlayerStats
export type StandingsTeam      = StandingsRow
export type TeamAnalyticsTeam  = TeamAnalyticsRow

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  seasons:       ()                            => get<SeasonStatus[]>('/seasons'),
  loadSeason:    (year: number)                => fetch(`${BASE}/seasons/${year}/load?force=false`, { method: 'POST' }).then(r => r.json()),
  schedule:      (season: number)              => get<ScheduleWeek[]>(`/schedule?season=${season}`),
  game:          (gameId: string)              => get<GameDetail>(`/games/${gameId}`),
  player:        (playerId: string)            => get<PlayerProfile>(`/players/${playerId}`),
  team:          (abbrev: string, season: number) => get<TeamProfile>(`/teams/${abbrev}?season=${season}`),
  teamRoster:    (team: string, season: number) => get<RosterPlayer[]>(`/teams/${team}/roster?season=${season}`),
  teamDepthChart: (team: string, season: number, week?: number) =>
    get<DepthChartEntry[]>(`/teams/${team}/depth-chart?season=${season}${week != null ? `&week=${week}` : ''}`),
  teamInjuries:  (team: string, season: number, week?: number) =>
    get<InjuryStatus[]>(`/teams/${team}/injuries?season=${season}${week != null ? `&week=${week}` : ''}`),
  teamAnalytics: (season: number)              => get<TeamAnalyticsResponse>(`/team-analytics?season=${season}`),
  standings:     (season: number)              => get<DivisionStandings[]>(`/standings?season=${season}`),
  leaders:       (season: number)              => get<LeagueLeader[]>(`/leaders?season=${season}`),
  wpaLeaders:    (season: number)              => get<WpaLeaders>(`/wpa-leaders?season=${season}`),
  comparables:   (playerId: string)            => get<PlayerComparable[]>(`/players/${playerId}/comparables`),
  search:        (q: string)                   => get<SearchResult[]>(`/search?q=${encodeURIComponent(q)}`),
}
