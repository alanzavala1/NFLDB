import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchSchedule(season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/schedule', { params: { query: { season } }, signal })
  return requireData(data)
}

export function scheduleQueryOptions(season: number | null) {
  return queryOptions({
    queryKey: ['schedule', season] as const,
    queryFn: ({ signal }) => {
      if (season === null) throw new Error('Select a season first.')
      return fetchSchedule(season, signal)
    },
    enabled: season !== null,
  })
}
