import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchWpaLeaders(season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/wpa-leaders', { params: { query: { season } }, signal })
  return requireData(data)
}

export function wpaLeadersQueryOptions(season: number | null) {
  return queryOptions({
    queryKey: ['wpa-leaders', season] as const,
    queryFn: ({ signal }) => {
      if (season === null) throw new Error('Select a season first.')
      return fetchWpaLeaders(season, signal)
    },
    enabled: season !== null,
  })
}
