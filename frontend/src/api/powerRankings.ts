import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchPowerRankings(season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/power-rankings', { params: { query: { season } }, signal })
  return requireData(data)
}

export function powerRankingsQueryOptions(season: number | null) {
  return queryOptions({
    queryKey: ['power-rankings', season] as const,
    queryFn: ({ signal }) => {
      if (season === null) throw new Error('Select a season first.')
      return fetchPowerRankings(season, signal)
    },
    enabled: season !== null,
  })
}
