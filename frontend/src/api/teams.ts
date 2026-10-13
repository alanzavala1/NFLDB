import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchTeam(team: string, season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/teams/{team}', { params: { path: { team }, query: { season } }, signal })
  return requireData(data)
}

export async function fetchTeamRoster(team: string, season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/teams/{team}/roster', { params: { path: { team }, query: { season } }, signal })
  return requireData(data)
}

export async function fetchTeamDepthChart(team: string, season: number, week?: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/teams/{team}/depth-chart', { params: { path: { team }, query: { season, week } }, signal })
  return requireData(data)
}

export async function fetchTeamInjuries(team: string, season: number, week?: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/teams/{team}/injuries', { params: { path: { team }, query: { season, week } }, signal })
  return requireData(data)
}

export async function fetchTeamSplits(team: string, season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/teams/{team}/splits', { params: { path: { team }, query: { season } }, signal })
  return requireData(data)
}

function requireSelection(team: string | undefined, season: number | null) {
  if (!team || season === null) throw new Error('Select a team and season first.')
  return { team, season }
}

export function teamQueryOptions(team: string | undefined, season: number | null) {
  return queryOptions({
    queryKey: ['team', team, season] as const,
    queryFn: ({ signal }) => {
      const selected = requireSelection(team, season)
      return fetchTeam(selected.team, selected.season, signal)
    },
    enabled: !!team && season !== null,
  })
}

export function teamRosterQueryOptions(team: string | undefined, season: number | null) {
  return queryOptions({
    queryKey: ['team-roster', team, season] as const,
    queryFn: ({ signal }) => {
      const selected = requireSelection(team, season)
      return fetchTeamRoster(selected.team, selected.season, signal)
    },
    enabled: !!team && season !== null,
  })
}

export function teamDepthChartQueryOptions(team: string | undefined, season: number | null, week?: number) {
  return queryOptions({
    queryKey: ['team-depth-chart', team, season, week] as const,
    queryFn: ({ signal }) => {
      const selected = requireSelection(team, season)
      return fetchTeamDepthChart(selected.team, selected.season, week, signal)
    },
    enabled: !!team && season !== null,
  })
}

export function teamInjuriesQueryOptions(team: string | undefined, season: number | null, week?: number) {
  return queryOptions({
    queryKey: ['team-injuries', team, season, week] as const,
    queryFn: ({ signal }) => {
      const selected = requireSelection(team, season)
      return fetchTeamInjuries(selected.team, selected.season, week, signal)
    },
    enabled: !!team && season !== null,
  })
}

export function teamSplitsQueryOptions(team: string | undefined, season: number | null) {
  return queryOptions({
    queryKey: ['team-splits', team, season] as const,
    queryFn: ({ signal }) => {
      const selected = requireSelection(team, season)
      return fetchTeamSplits(selected.team, selected.season, signal)
    },
    enabled: !!team && season !== null,
  })
}
