/**
 * TanStack Query hooks for every API call.
 *
 * Why wrap api.ts at all?
 *   - Stable query keys so the cache works across pages
 *   - Centralized caching/staleness policy
 *   - Free loading + error states (`useQuery` returns isPending/isError)
 *   - Auto-dedup when two components on the same page ask for the same data
 *
 * Pattern: every hook is a thin wrapper around `useQuery({ queryKey, queryFn })`.
 * The query keys are arrays starting with a stable string namespace so we
 * can later invalidate groups (e.g. `qc.invalidateQueries({ queryKey: ['players'] })`).
 */
import { useQuery, type QueryKey, type UseQueryOptions } from '@tanstack/react-query'
import { api } from './api'
import { seasonsQueryOptions } from './api/seasons'
import { scheduleQueryOptions } from './api/schedule'
import { gameQueryOptions } from './api/games'
import { leadersQueryOptions } from './api/leaders'
import { wpaLeadersQueryOptions } from './api/wpaLeaders'
import { playerQueryOptions, playerComparablesQueryOptions } from './api/players'
import { teamQueryOptions, teamRosterQueryOptions, teamDepthChartQueryOptions, teamInjuriesQueryOptions, teamSplitsQueryOptions } from './api/teams'
import { teamAnalyticsQueryOptions } from './api/teamAnalytics'
import { standingsQueryOptions } from './features/standings/queries'
import type {
  DepthChartEntry, DivisionStandings, GameDetail, InjuryStatus,
  LeagueLeader, PlayerComparable, PlayerProfile, PlayerSplit, RosterPlayer,
  ScheduleWeek, SearchResult, SeasonStatus, TeamAnalyticsResponse,
  TeamProfile, TeamSplit, WpaLeaders,
} from './types'

// Remaining legacy Player Splits policy; revisit when that resource migrates.
const FOREVER = Number.POSITIVE_INFINITY

type Options<T, Key extends QueryKey = QueryKey> = Omit<UseQueryOptions<T, Error, T, Key>, 'queryKey' | 'queryFn'>


// ── Meta ─────────────────────────────────────────────────────────────────────

export function useSeasons(options?: Options<SeasonStatus[], readonly ['seasons']>) {
  return useQuery({
    ...seasonsQueryOptions(),
    ...options,
  })
}


// ── Schedule / games ─────────────────────────────────────────────────────────

export function useSchedule(season: number | null, options?: Options<ScheduleWeek[], readonly ['schedule', number | null]>) {
  return useQuery({
    ...scheduleQueryOptions(season),
    ...options,
  })
}

export function useGame(gameId: string | undefined, options?: Options<GameDetail, readonly ['game', string | undefined]>) {
  return useQuery({
    ...gameQueryOptions(gameId),
    ...options,
  })
}


// ── Player ───────────────────────────────────────────────────────────────────

export function usePlayer(playerId: string | undefined, options?: Options<PlayerProfile, readonly ['player', string | undefined]>) {
  return useQuery({
    ...playerQueryOptions(playerId),
    ...options,
  })
}

export function usePlayerComparables(playerId: string | undefined, options?: Options<PlayerComparable[], readonly ['player-comparables', string | undefined]>) {
  return useQuery({
    ...playerComparablesQueryOptions(playerId),
    ...options,
  })
}

export function usePlayerSplits(playerId: string | undefined, options?: Options<PlayerSplit[]>) {
  return useQuery({
    queryKey: ['player-splits', playerId] as const,
    queryFn: () => api.splits(playerId!),
    enabled: !!playerId,
    // Splits are materialized during ingest; stable between loads.
    staleTime: FOREVER,
    ...options,
  })
}


// ── Team ─────────────────────────────────────────────────────────────────────

export function useTeam(abbrev: string | undefined, season: number | null, options?: Options<TeamProfile, readonly ['team', string | undefined, number | null]>) {
  return useQuery({
    ...teamQueryOptions(abbrev, season),
    ...options,
  })
}

export function useTeamRoster(abbrev: string | undefined, season: number | null, options?: Options<RosterPlayer[], readonly ['team-roster', string | undefined, number | null]>) {
  return useQuery({
    ...teamRosterQueryOptions(abbrev, season),
    ...options,
  })
}

export function useTeamDepthChart(
  abbrev: string | undefined,
  season: number | null,
  week?: number,
  options?: Options<DepthChartEntry[], readonly ['team-depth-chart', string | undefined, number | null, number | undefined]>,
) {
  return useQuery({
    ...teamDepthChartQueryOptions(abbrev, season, week),
    ...options,
  })
}

export function useTeamInjuries(
  abbrev: string | undefined,
  season: number | null,
  week?: number,
  options?: Options<InjuryStatus[], readonly ['team-injuries', string | undefined, number | null, number | undefined]>,
) {
  return useQuery({
    ...teamInjuriesQueryOptions(abbrev, season, week),
    ...options,
  })
}

export function useTeamAnalytics(season: number | null, options?: Options<TeamAnalyticsResponse, readonly ['team-analytics', number | null]>) {
  return useQuery({
    ...teamAnalyticsQueryOptions(season),
    ...options,
  })
}

export function useTeamSplits(abbrev: string | undefined, season: number | null, options?: Options<TeamSplit[], readonly ['team-splits', string | undefined, number | null]>) {
  return useQuery({
    ...teamSplitsQueryOptions(abbrev, season),
    ...options,
  })
}


// ── League ───────────────────────────────────────────────────────────────────

export function useStandings(season: number | null, options?: Options<DivisionStandings[], readonly ['standings', number | null]>) {
  return useQuery({
    ...standingsQueryOptions(season),
    ...options,
  })
}

export function useLeaders(season: number | null, options?: Options<LeagueLeader[], readonly ['leaders', number | null]>) {
  return useQuery({
    ...leadersQueryOptions(season),
    ...options,
  })
}

export function useWpaLeaders(season: number | null, options?: Options<WpaLeaders, readonly ['wpa-leaders', number | null]>) {
  return useQuery({
    ...wpaLeadersQueryOptions(season),
    ...options,
  })
}


// ── Search ───────────────────────────────────────────────────────────────────

export function useSearch(q: string, options?: Options<SearchResult[]>) {
  return useQuery({
    queryKey: ['search', q] as const,
    queryFn: () => api.search(q),
    enabled: q.length >= 2,
    // Search results can be cached briefly to handle rapid typing without thrashing.
    staleTime: 60 * 1000,
    ...options,
  })
}
