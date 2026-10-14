import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { LiveGameOut, Scoreboard } from '../../types'
import { liveScoreboardQueryOptions } from './queries'
import { EMPTY_GAMES, LiveScoresContext } from './context'

function indexGames(board: Scoreboard): Record<string, LiveGameOut> {
  return Object.fromEntries(board.games.flatMap(game => game.game_id ? [[game.game_id, game] as const] : []))
}

export function LiveScoresProvider({ children }: { children: ReactNode }) {
  const query = useQuery({ ...liveScoreboardQueryOptions(), select: indexGames })
  // Live data enhances the ordinary schedule. Errors preserve cached scores;
  // an initial failure leaves schedule cards usable until the paced recovery.
  return <LiveScoresContext.Provider value={query.data ?? EMPTY_GAMES}>{children}</LiveScoresContext.Provider>
}
