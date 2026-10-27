import type { PlayerGame, SituationalStats } from '../../types'
import { hasReceivingProduction } from '../../utils/receiving'

export function passerRating(cmp: number, att: number, yds: number, td: number, int_: number): string | null {
  if (att === 0) return null
  const clamp = (x: number) => Math.min(2.375, Math.max(0, x))
  const a = clamp((cmp / att - 0.3) / 0.2)
  const b = clamp((yds / att - 3) / 4)
  const c = clamp((td / att) / 0.05)
  const d = clamp(2.375 - (int_ / att) / 0.04)
  return (((a + b + c + d) / 6) * 100).toFixed(1)
}

export function pct(a: number, b: number | null, dec = 1): string | null { return b != null && b > 0 ? (a / b * 100).toFixed(dec) : null }

export function ratio(y: number | null, a: number | null, dec = 1): string | null { return y != null && a != null && a > 0 ? (y / a).toFixed(dec) : null }

export function sfmt(x: number | null | undefined, dec = 1): string | null { if (x == null) return null; return `${x >= 0 ? '+' : ''}${x.toFixed(dec)}` }

export function dfmt(x: number | null | undefined, dec = 1): string | null { if (x == null) return null; return x.toFixed(dec) }

export function sumGames(games: PlayerGame[]) {
  const s = {
    attempts: 0, completions: 0, pass_yards: 0, pass_tds: 0,
    interceptions_thrown: 0, sacks_taken: 0, pass_epa: 0,
    carries: 0, rush_yards: 0, rush_tds: 0, rush_epa: 0,
    targets: 0, receptions: 0, rec_yards: 0, rec_tds: 0, yac: 0, air_yards: 0, rec_epa: 0,
    solo_tackles: 0, assist_tackles: 0, tackles_for_loss: 0,
    sacks: 0, qb_hits: 0, def_interceptions: 0, pass_breakups: 0,
    forced_fumbles: 0, fumble_recoveries: 0,
    fg_att: 0, fg_made: 0, xp_att: 0, xp_made: 0,
    punts: 0, punt_yards: 0,
  }
  for (const g of games) {
    for (const k of Object.keys(s) as (keyof typeof s)[]) s[k] += g[k] ?? 0
  }
  return { ...s,
    targets: games.some(g => g.targets === null) ? null : s.targets,
    air_yards: games.some(g => g.air_yards === null) ? null : s.air_yards,
    yac: games.some(g => g.yac === null) ? null : s.yac,
  }
}

export type Totals = ReturnType<typeof sumGames>

const OL_POSITIONS = new Set(['C', 'G', 'T', 'OT', 'OG', 'OL', 'LS', 'OC'])

export function detectPos(t: Totals, position?: string | null): string {
  if (position === 'QB' || t.attempts > 10) return 'QB'
  // Missing targets must not turn a rostered receiver with rushing work into RB.
  if (position === 'WR' || position === 'TE') return 'WR'
  if (position === 'RB' || (t.carries > 20 && t.targets != null && t.targets < t.carries * 0.7)) return 'RB'
  if ((t.targets != null && t.targets > 20) || (!position && hasReceivingProduction(t))) return 'WR'
  if (position === 'K'  || t.fg_att > 0) return 'K'
  if (position === 'P'  || t.punts  > 0) return 'P'
  if (OL_POSITIONS.has(position ?? '')) return 'OL'
  return 'DEF'
}

export function aggregateSituational(situational: Record<number, SituationalStats>): SituationalStats {
  const agg: Record<string, number> = {}
  const sumKeys: (keyof SituationalStats)[] = [
    'rz_pass_att','rz_cmp','rz_pass_tds','rz_targets','rz_rec_tds','rz_carries','rz_rush_tds',
    'third_pass_att','third_pass_fd','third_targets','third_rec_fd','third_carries','third_rush_fd',
    'fd_pass','fd_rec','fd_rush',
  ]
  for (const s of Object.values(situational)) {
    agg.lng_pass = Math.max(agg.lng_pass ?? 0, s.lng_pass ?? 0)
    agg.lng_rush = Math.max(agg.lng_rush ?? 0, s.lng_rush ?? 0)
    agg.lng_rec  = Math.max(agg.lng_rec  ?? 0, s.lng_rec  ?? 0)
    for (const k of sumKeys) agg[k] = (agg[k] ?? 0) + (s[k] ?? 0)
  }
  const result = agg as SituationalStats
  for (const key of ['rz_targets', 'third_targets'] as const) {
    if (Object.values(situational).some(s => s[key] === null)) result[key] = null
  }
  return result
}
