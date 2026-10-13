import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchPlayer(playerId: string, signal?: AbortSignal) {
  const { data } = await client.GET('/api/players/{player_id}', {
    params: { path: { player_id: playerId } }, signal,
  })
  return requireData(data)
}

export async function fetchPlayerComparables(playerId: string, signal?: AbortSignal) {
  const { data } = await client.GET('/api/players/{player_id}/comparables', {
    params: { path: { player_id: playerId } }, signal,
  })
  return requireData(data)
}

export function playerQueryOptions(playerId: string | undefined) {
  return queryOptions({
    queryKey: ['player', playerId] as const,
    queryFn: ({ signal }) => {
      if (!playerId) throw new Error('Select a player first.')
      return fetchPlayer(playerId, signal)
    },
    enabled: !!playerId,
  })
}

export function playerComparablesQueryOptions(playerId: string | undefined) {
  return queryOptions({
    queryKey: ['player-comparables', playerId] as const,
    queryFn: ({ signal }) => {
      if (!playerId) throw new Error('Select a player first.')
      return fetchPlayerComparables(playerId, signal)
    },
    enabled: !!playerId,
  })
}
