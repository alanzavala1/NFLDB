import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchLeaders(season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/leaders', { params: { query: { season } }, signal })
  return requireData(data)
}

export function leadersQueryOptions(season: number | null) {
  return queryOptions({
    queryKey: ['leaders', season] as const,
    queryFn: ({ signal }) => {
      if (season === null) throw new Error('Select a season first.')
      return fetchLeaders(season, signal)
    },
    enabled: season !== null,
  })
}
