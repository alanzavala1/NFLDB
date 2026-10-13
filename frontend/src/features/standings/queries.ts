import { queryOptions } from '@tanstack/react-query'
import { fetchStandings } from './api'

export function standingsQueryOptions(season: number | null) {
  return queryOptions({
    queryKey: ['standings', season] as const,
    queryFn: ({ signal }) => {
      if (season === null) throw new Error('Select a season first.')
      return fetchStandings(season, signal)
    },
    enabled: season !== null,
  })
}
