import { client, requireData } from '../../api/client'

export async function fetchStandings(season: number, signal?: AbortSignal) {
  const { data } = await client.GET('/api/standings', { params: { query: { season } }, signal })
  return requireData(data)
}
