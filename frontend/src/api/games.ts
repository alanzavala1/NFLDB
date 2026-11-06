import { queryOptions } from '@tanstack/react-query'
import { client, requireData } from './client'

export async function fetchGame(gameId: string, signal?: AbortSignal) {
  const { data } = await client.GET('/api/games/{game_id}', {
    params: { path: { game_id: gameId } }, signal,
  })
  return requireData(data)
}

export async function fetchGameLineup(gameId: string, signal?: AbortSignal) {
  const { data } = await client.GET('/api/games/{game_id}/lineup', {
    params: { path: { game_id: gameId } }, signal,
  })
  return requireData(data)
}

export async function fetchPlayerChart(gameId: string, playerId: string, signal?: AbortSignal) {
  const { data } = await client.GET('/api/games/{game_id}/players/{player_id}/chart', {
    params: { path: { game_id: gameId, player_id: playerId } }, signal,
  })
  return requireData(data)
}

function requireGame(gameId: string | undefined) {
  if (!gameId) throw new Error('Select a game first.')
  return gameId
}

export function gameQueryOptions(gameId: string | undefined) {
  return queryOptions({
    queryKey: ['game', gameId] as const,
    queryFn: ({ signal }) => fetchGame(requireGame(gameId), signal),
    enabled: !!gameId,
  })
}

export function gameLineupQueryOptions(gameId: string | undefined) {
  return queryOptions({
    queryKey: ['game-lineup', gameId] as const,
    queryFn: ({ signal }) => fetchGameLineup(requireGame(gameId), signal),
    enabled: !!gameId,
  })
}

export function playerChartQueryOptions(gameId: string | undefined, playerId: string | undefined) {
  return queryOptions({
    queryKey: ['player-chart', gameId, playerId] as const,
    queryFn: ({ signal }) => {
      if (!playerId) throw new Error('Select a player first.')
      return fetchPlayerChart(requireGame(gameId), playerId, signal)
    },
    enabled: !!gameId && !!playerId,
  })
}
