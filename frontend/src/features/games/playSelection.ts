import type { WinProbPlay } from '../../types'

// ── Key plays (turnovers + big non-scoring WP swings) ─────────────────────────

export type KeyPlayKind = 'int' | 'fum' | 'big'

interface KeyPlayItem {
  qtr: number
  rem: number
  team: string | null
  desc: string | null
  kind: KeyPlayKind
  wpSwing: number  // points of WP added for the offense
}

// Scoring plays live in the Scoring Summary; this surfaces the OTHER pivotal
// moments — turnovers, and big non-scoring win-probability swings (4th-down
// stops, missed FGs, chunk plays).
const BIG_SWING = 10

// |WP%| change to count a non-scoring play as "key"
// Non-scrimmage plays (PATs, kicks, kneels) aren't "key plays" even if the
// win-prob diff around them looks large.
const NON_KEY = /extra point|field goal is good|kicks off|punts|two-point|kneels?\b|spiked/i

export function detectKeyPlays(plays: WinProbPlay[]): KeyPlayItem[] {
  const out: KeyPlayItem[] = []
  for (let i = 0; i < plays.length; i++) {
    const p = plays[i]
    const prevHomeWp = i > 0 ? plays[i - 1].home_wp : 0.5
    const homeSwing = (p.home_wp - prevHomeWp) * 100
    const base = { qtr: p.qtr, rem: p.game_seconds_remaining, team: p.posteam, desc: p.desc, wpSwing: homeSwing }
    if (p.interception === 1) {
      out.push({ ...base, kind: 'int' })
    } else if (p.fumble_lost === 1) {
      out.push({ ...base, kind: 'fum' })
    } else if (p.touchdown !== 1 && !NON_KEY.test(p.desc ?? '') && Math.abs(homeSwing) >= BIG_SWING) {
      out.push({ ...base, kind: 'big' })
    }
  }
  return out.sort((a, b) => b.rem - a.rem)
}
