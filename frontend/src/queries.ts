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
import { useQuery, type UseQueryOptions } from '@tanstack/react-query'
import { api } from './api'
import type {
  DepthChartEntry, DivisionStandings, GameDetail, InjuryStatus,
  LeagueLeader, PlayerComparable, PlayerProfile, PlayerSplit, RosterPlayer,
  ScheduleWeek, SearchResult, SeasonStatus, TeamAnalyticsResponse,
  TeamProfile, TeamSplit, WpaLeaders,
} from './types'

// Past-season data is immutable, so override the global 5-minute staleTime
// and tell the cache it never goes stale.
const FOREVER = Number.POSITIVE_INFINITY

type Options<T> = Omit<UseQueryOptions<T>, 'queryKey' | 'queryFn'>


// ── Meta ─────────────────────────────────────────────────────────────────────

export function useSeasons(options?: Options<SeasonStatus[]>) {
  return useQuery({
    queryKey: ['seasons'] as const,
    queryFn: api.seasons,
    // Seasons status changes when an ingest finishes, so refresh on a short cadence.
    staleTime: 30 * 1000,
    ...options,
  })
}


// ── Schedule / games ─────────────────────────────────────────────────────────

export function useSchedule(season: number | null, options?: Options<ScheduleWeek[]>) {
  return useQuery({
    queryKey: ['schedule', season] as const,
    queryFn: () => api.schedule(season!),
    enabled: season != null,
    ...options,
  })
}

export function useGame(gameId: string | undefined, options?: Options<GameDetail>) {
  return useQuery({
    queryKey: ['game', gameId] as const,
    queryFn: () => api.game(gameId!),
    enabled: !!gameId,
    // A single game's data is immutable once finished — keep it forever.
    staleTime: FOREVER,
    ...options,
  })
}


// ── Player ───────────────────────────────────────────────────────────────────

export function usePlayer(playerId: string | undefined, options?: Options<PlayerProfile>) {
  return useQuery({
    queryKey: ['player', playerId] as const,
    queryFn: () => api.player(playerId!),
    enabled: !!playerId,
    ...options,
  })
}

export function usePlayerComparables(playerId: string | undefined, options?: Options<PlayerComparable[]>) {
  return useQuery({
    queryKey: ['player-comparables', playerId] as const,
    queryFn: () => api.comparables(playerId!),
    enabled: !!playerId,
    // Comparables rebuild during ingest but are otherwise stable.
    staleTime: FOREVER,
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

export function useTeam(abbrev: string | undefined, season: number | null, options?: Options<TeamProfile>) {
  return useQuery({
    queryKey: ['team', abbrev, season] as const,
    queryFn: () => api.team(abbrev!, season!),
    enabled: !!abbrev && season != null,
    ...options,
  })
}

export function useTeamRoster(abbrev: string | undefined, season: number | null, options?: Options<RosterPlayer[]>) {
  return useQuery({
    queryKey: ['team-roster', abbrev, season] as const,
    queryFn: () => api.teamRoster(abbrev!, season!),
    enabled: !!abbrev && season != null,
    ...options,
  })
}

export function useTeamDepthChart(
  abbrev: string | undefined,
  season: number | null,
  week?: number,
  options?: Options<DepthChartEntry[]>,
) {
  return useQuery({
    queryKey: ['team-depth-chart', abbrev, season, week] as const,
    queryFn: () => api.teamDepthChart(abbrev!, season!, week),
    enabled: !!abbrev && season != null,
    ...options,
  })
}

export function useTeamInjuries(
  abbrev: string | undefined,
  season: number | null,
  week?: number,
  options?: Options<InjuryStatus[]>,
) {
  return useQuery({
    queryKey: ['team-injuries', abbrev, season, week] as const,
    queryFn: () => api.teamInjuries(abbrev!, season!, week),
    enabled: !!abbrev && season != null,
    ...options,
  })
}

export function useTeamAnalytics(season: number | null, options?: Options<TeamAnalyticsResponse>) {
  return useQuery({
    queryKey: ['team-analytics', season] as const,
    queryFn: () => api.teamAnalytics(season!),
    enabled: season != null,
    ...options,
  })
}

export function useTeamSplits(abbrev: string | undefined, season: number | null, options?: Options<TeamSplit[]>) {
  return useQuery({
    queryKey: ['team-splits', abbrev, season] as const,
    queryFn: () => api.teamSplits(abbrev!, season!),
    enabled: !!abbrev && season != null,
    staleTime: FOREVER,
    ...options,
  })
}


// ── League ───────────────────────────────────────────────────────────────────

export function useStandings(season: number | null, options?: Options<DivisionStandings[]>) {
  return useQuery({
    queryKey: ['standings', season] as const,
    queryFn: () => api.standings(season!),
    enabled: season != null,
    ...options,
  })
}

export function useLeaders(season: number | null, options?: Options<LeagueLeader[]>) {
  return useQuery({
    queryKey: ['leaders', season] as const,
    queryFn: () => api.leaders(season!),
    enabled: season != null,
    ...options,
  })
}

export function useWpaLeaders(season: number | null, options?: Options<WpaLeaders>) {
  return useQuery({
    queryKey: ['wpa-leaders', season] as const,
    queryFn: () => api.wpaLeaders(season!),
    enabled: season != null,
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
