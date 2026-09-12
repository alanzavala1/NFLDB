/**
 * Live scores, paced by the server.
 *
 * The client never decides how often to poll. Every response carries
 * `poll_after` — the server already knows whether a game is being played,
 * whether one has run into overtime, and whether it is a Wednesday in June —
 * so the hook simply does what it is told, and stops entirely when told null.
 *
 * One fetch feeds every card on the page: the provider holds the board, and
 * `useLiveGame(game_id)` picks a single game out of it.
 *
 * What the hook does decide is whether a response is worth rendering at all.
 * The server's cache is per-instance and there is no session affinity, so
 * successive polls can arrive out of order; see `liveOrdering` for why that is
 * the client's problem and how far the guard goes.
 */
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { api } from '../api'
import { isStaleResponse, mergeGames } from './liveOrdering'
import type { LiveGameOut, Scoreboard } from '../types'

type Board = {
  byGameId: Record<string, LiveGameOut>
  source: Scoreboard['source'] | null
  fetchedAt: string | null
}

const EMPTY: Board = { byGameId: {}, source: null, fetchedAt: null }

const LiveScoresContext = createContext<Board>(EMPTY)

export function LiveScoresProvider({ children }: { children: ReactNode }) {
  const [board, setBoard] = useState<Board>(EMPTY)
  const timer = useRef<number | undefined>(undefined)
  // The newest `fetched_at` we have rendered. Kept in a ref, not state, so the
  // comparison can't race a pending render.
  const shownAt = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function tick() {
      try {
        const data = await api.liveScoreboard()
        if (cancelled) return

        // An older snapshot than the one on screen is not an update. Drop it
        // whole rather than merging it game by game — the pacing it carries is
        // still good, so the next poll goes out on schedule either way.
        if (!isStaleResponse(data.fetched_at, shownAt.current)) {
          shownAt.current = data.fetched_at ?? shownAt.current
          setBoard(prev => ({
            byGameId: mergeGames(prev.byGameId, data.games),
            source: data.source,
            fetchedAt: data.fetched_at,
          }))
        }

        // null means there is nothing to watch — stop, don't fall back to a
        // default interval. An idle tab should cost nothing.
        if (data.poll_after != null) {
          timer.current = window.setTimeout(tick, data.poll_after * 1000)
        }
      } catch {
        // The scoreboard is an enhancement over cards that already render from
        // the schedule. If it fails, leave what we have and try again later
        // rather than surfacing an error for something nobody asked for.
        if (!cancelled) timer.current = window.setTimeout(tick, 60_000)
      }
    }

    tick()
    return () => {
      cancelled = true
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [])

  return <LiveScoresContext.Provider value={board}>{children}</LiveScoresContext.Provider>
}

/** The live state for one game, or null if it isn't on today's board. */
export function useLiveGame(gameId: string | null | undefined): LiveGameOut | null {
  const board = useContext(LiveScoresContext)
  if (!gameId) return null
  return board.byGameId[gameId] ?? null
}

/** Whether any game on the board is being played right now. */
export function useAnyGameLive(): boolean {
  const board = useContext(LiveScoresContext)
  return Object.values(board.byGameId).some(g => g.state === 'in')
}
