/**
 * Keep the live board moving forwards.
 *
 * Serving processes and upstream edge nodes can hold snapshots of different
 * ages. Schedule fallback can also lag a game already in progress. The client
 * keeps previously reported values rather than inventing a score or clock.
 *
 * The client is the only place that sees the sequence, so the ordering is
 * enforced here, in two layers:
 *
 *   1. A whole response fetched before the one already on screen is dropped.
 *      `fetched_at` is stamped when the instance built the snapshot — a stale
 *      or failed-over reply carries the original, not the time it was served —
 *      so it names the cross-instance case exactly.
 *
 *   2. Per game, a state behind the one already shown is held back even when
 *      the response as a whole is newer. ESPN answers from several edge nodes
 *      with a 10s TTL each, and an instance that loses the upstream falls back
 *      to our schedule, which is freshly stamped but knows nothing about a game
 *      in progress.
 *
 * Nothing here invents a value. Both layers only ever decide to keep showing
 * something the server already sent.
 */
import type { LiveGameOut, Scoreboard } from '../../types'

/** "12:34" → 754 seconds. Null when absent or unparseable — which callers must
 *  treat as "unknown", never as zero. */
export function clockToSeconds(clock: string | null | undefined): number | null {
  if (!clock) return null
  const m = /^(\d{1,2}):(\d{2})(?:\.\d+)?$/.exec(clock.trim())
  if (!m) return null
  return Number(m[1]) * 60 + Number(m[2])
}

// pre → in → post is the only direction a game travels.
const STATE_ORDER: Record<string, number> = { pre: 0, in: 1, post: 2 }

const score = (v: number | null | undefined) => v ?? 0

/**
 * Is `next` behind `prev` for the same game?
 *
 * Only ever answers true on evidence. A missing period or an unparseable clock
 * is not evidence of anything, and the response is let through — showing a
 * slightly old number is a much smaller lie than freezing the board because one
 * field was null.
 */
export function isBehind(prev: LiveGameOut, next: LiveGameOut): boolean {
  const was = STATE_ORDER[prev.state] ?? 0
  const now = STATE_ORDER[next.state] ?? 0
  if (now < was) return true      // a game that has finished does not restart
  if (now > was) return false     // and moving on is not a regression

  // Keep the last reported score on a decrease, including corrections until
  // later data catches up. Replacing a known score with null is also held.
  if (score(next.away_score) < score(prev.away_score)) return true
  if (score(next.home_score) < score(prev.home_score)) return true

  if (prev.period != null && next.period != null) {
    if (next.period < prev.period) return true
    if (next.period > prev.period) return false   // the clock resets legitimately
    // Within one period the clock counts down, so a larger value is a rewind.
    const before = clockToSeconds(prev.clock)
    const after = clockToSeconds(next.clock)
    if (before != null && after != null && after > before) return true
  }
  return false
}

/**
 * Fold a response into the board, keeping any game the response would move
 * backwards. The response's set of games stays authoritative — only the
 * contents of a game are guarded, so a board that legitimately empties out
 * still empties out.
 */
export function mergeGames(
  prev: Record<string, LiveGameOut>,
  incoming: LiveGameOut[],
): Record<string, LiveGameOut> {
  const out: Record<string, LiveGameOut> = {}
  for (const g of incoming) {
    if (!g.game_id) continue
    const before = prev[g.game_id]
    out[g.game_id] = before && isBehind(before, g) ? before : g
  }
  return out
}

/**
 * Was this response built before the one we are already showing?
 *
 * Equal timestamps are not stale — that is the same snapshot served twice,
 * which is the cache working. An unparseable or missing stamp is let through,
 * because layer 2 still guards the values themselves.
 */
export function isStaleResponse(fetchedAt: string | null | undefined, shownAt: string | null): boolean {
  if (!fetchedAt || !shownAt) return false
  const next = Date.parse(fetchedAt)
  const shown = Date.parse(shownAt)
  if (Number.isNaN(next) || Number.isNaN(shown)) return false
  return next < shown
}

/** Keep ordering in the shared cache, but always honor the latest reply's pacing. */
export function reconcileScoreboard(previous: Scoreboard | undefined, incoming: Scoreboard): Scoreboard {
  if (previous && isStaleResponse(incoming.fetched_at, previous.fetched_at)) {
    return { ...previous, poll_after: incoming.poll_after }
  }
  const games = Object.fromEntries((previous?.games ?? []).flatMap(game => game.game_id ? [[game.game_id, game] as const] : []))
  return { ...incoming, games: Object.values(mergeGames(games, incoming.games)) }
}
