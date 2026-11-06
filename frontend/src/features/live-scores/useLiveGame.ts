import { useContext } from 'react'
import { LiveScoresContext } from './context'
import type { LiveGameOut } from '../../types'

export function useLiveGame(gameId: string | null | undefined): LiveGameOut | null {
  const games = useContext(LiveScoresContext)
  return gameId ? games[gameId] ?? null : null
}
