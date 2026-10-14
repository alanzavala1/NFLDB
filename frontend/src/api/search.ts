import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchSearch(text: string, signal?: AbortSignal) {
  const q = text.trim()
  if (!q) throw new Error('Enter a player or team to search.')
  const { data } = await client.GET('/api/search', { params: { query: { q } }, signal })
  return requireData(data)
}

export function searchQueryOptions(text: string) {
  const term = text.trim()
  return queryOptions({
    queryKey: ['search', term] as const,
    queryFn: ({ signal }) => fetchSearch(term, signal),
    enabled: term.length > 0,
    staleTime: 60_000,
  })
}
