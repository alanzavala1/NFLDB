/**
 * Friendly aliases for backend Pydantic models.
 *
 * Source of truth: api/schemas/*.py -> generated into ./api.d.ts via
 * `npm run gen-types`. Do not hand-edit api.d.ts.
 */
import type { components } from './api'

type Schemas = components['schemas']

// Meta
export type HealthResponse      = Schemas['HealthResponse']
export type SeasonStatus        = Schemas['SeasonStatus']
export type LoadSeasonResponse  = Schemas['LoadSeasonResponse']

// Schedule / games
export type Game             = Schemas['Game']
export type ScheduleWeek     = Schemas['ScheduleWeek']
export type GamePlayerStats  = Schemas['GamePlayerStats']
export type GameDetail       = Schemas['GameDetail']
export type QuarterScore     = Schemas['QuarterScore']
export type WinProbPlay      = Schemas['WinProbPlay']

// Search
export type SearchResult     = Schemas['SearchResult']

// Teams
export type RosterPlayer     = Schemas['RosterPlayer']
export type TeamGame         = Schemas['TeamGame']
export type TeamLeader       = Schemas['TeamLeader']
export type TeamProfile      = Schemas['TeamProfile']

// Standings
export type StandingsRow         = Schemas['StandingsRow']
export type DivisionStandings    = Schemas['DivisionStandings']

// Leaders
export type LeagueLeader     = Schemas['LeagueLeader']
export type WpaLeader        = Schemas['WpaLeader']
export type WpaLeaders       = Schemas['WpaLeaders']
export type PlayerComparable = Schemas['PlayerComparable']

// Player profile
export type PlayerProfile    = Schemas['PlayerProfile']
export type PlayerGame       = Schemas['PlayerGame']
export type NgsStats         = Schemas['NgsStats']
export type SnapTotals       = Schemas['SnapTotals']
export type SituationalStats = Schemas['SituationalStats']
export type PlayerWpa        = Schemas['PlayerWpa']
export type PlayerAdvStats   = Schemas['PlayerAdvStats']

// Team analytics
export type TeamAnalyticsRow      = Schemas['TeamAnalyticsRow']
export type TeamAnalyticsResponse = Schemas['TeamAnalyticsResponse']
