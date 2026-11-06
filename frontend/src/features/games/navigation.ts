import type { GameOrigin } from '../../types/navigation'

export function playerLink(playerId: string, ctx: GameOrigin | null) {
  if (!ctx) return { to: `/players/${playerId}`, state: undefined }
  return { to: `/players/${playerId}`, state: { fromGame: ctx } }
}
