import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchPlayerSplits(playerId: string, signal?: AbortSignal) {
  const { data } = await client.GET('/api/players/{player_id}/splits', {
    params: { path: { player_id: playerId } }, signal,
  })
  return requireData(data)
}

export async function fetchDefensiveSplits(playerId: string, signal?: AbortSignal) {
  const { data } = await client.GET('/api/players/{player_id}/def-splits', {
    params: { path: { player_id: playerId } }, signal,
  })
  return requireData(data)
}

export async function fetchReceivingSplits(playerId: string, signal?: AbortSignal) {
  const { data } = await client.GET('/api/players/{player_id}/receiving-splits', {
    params: { path: { player_id: playerId } }, signal,
  })
  return requireData(data)
}

function requirePlayer(playerId: string | undefined) {
  if (!playerId) throw new Error('Select a player first.')
  return playerId
}

export function playerSplitsQueryOptions(playerId: string | undefined) {
  return queryOptions({
    queryKey: ['player-splits', playerId] as const,
    queryFn: ({ signal }) => fetchPlayerSplits(requirePlayer(playerId), signal),
    enabled: !!playerId,
  })
}

export function defensiveSplitsQueryOptions(playerId: string | undefined) {
  return queryOptions({
    queryKey: ['player-def-splits', playerId] as const,
    queryFn: ({ signal }) => fetchDefensiveSplits(requirePlayer(playerId), signal),
    enabled: !!playerId,
  })
}

export function receivingSplitsQueryOptions(playerId: string | undefined) {
  return queryOptions({
    queryKey: ['player-receiving-splits', playerId] as const,
    queryFn: ({ signal }) => fetchReceivingSplits(requirePlayer(playerId), signal),
    enabled: !!playerId,
  })
}
