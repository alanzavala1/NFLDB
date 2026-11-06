import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchTeamAnalytics(season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/team-analytics', { params: { query: { season } }, signal })
  return requireData(data)
}

// The response contains the entire league, so teams share one season cache.
export function teamAnalyticsQueryOptions(season: number | null) {
  return queryOptions({
    queryKey: ['team-analytics', season] as const,
    queryFn: ({ signal }) => {
      if (season === null) throw new Error('Select a season first.')
      return fetchTeamAnalytics(season, signal)
    },
    enabled: season !== null,
  })
}
