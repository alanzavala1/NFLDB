import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchSeasons(signal?: AbortSignal) {
  const { data } = await client.GET('/api/seasons', { signal })
  return requireData(data)
}

export function seasonsQueryOptions() {
  return queryOptions({
    queryKey: ['seasons'] as const,
    queryFn: ({ signal }) => fetchSeasons(signal),
    staleTime: 30_000,
  })
}
