import type { DefensiveSplit } from '../../types'
import type { Dim, Metric, Situation } from './types'
import { intStr } from './metricFormatting'

// ── Defensive player metrics ─────────────────────────────────────────────────
// Event counts (more is always better). No coverage data exists in nflfastR,
// so these are tackles / pass-rush / takeaway production, not coverage.

const DEFENSE_METRICS: Metric<DefensiveSplit>[] = [
  { key: 'tackles', label: 'Tackles', group: 'Tackling', value: r => r.tackles, fmt: v => v.toFixed(0), higherIsBetter: true },
  { key: 'solo', label: 'Solo', group: 'Tackling', value: r => r.solo, fmt: intStr, higherIsBetter: true },
  { key: 'tfl', label: 'TFL', group: 'Tackling', value: r => r.tfl, fmt: intStr, higherIsBetter: true },
  { key: 'sacks', label: 'Sacks', group: 'Pass Rush', value: r => r.sacks, fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'qb_hits', label: 'QB Hits', group: 'Pass Rush', value: r => r.qb_hits, fmt: intStr, higherIsBetter: true },
  { key: 'int', label: 'INT', group: 'Coverage', value: r => r.interceptions, fmt: intStr, higherIsBetter: true },
  { key: 'pbu', label: 'PBU', group: 'Coverage', value: r => r.pass_breakups, fmt: intStr, higherIsBetter: true },
  { key: 'ff', label: 'FF', group: 'Takeaways', value: r => r.forced_fumbles, fmt: intStr, higherIsBetter: true },
]

const DEFENSE_DIMS: Dim[] = [
  { key: 'vs_play', label: 'vs Pass/Run' },
  { key: 'down', label: 'Down' },
  { key: 'game_script', label: 'Game Script' },
  { key: 'quarter', label: 'Quarter' },
  { key: 'field_zone', label: 'Field Zone' },
  { key: 'home_away', label: 'Home/Away' },
  { key: 'roof', label: 'Stadium' },
  { key: 'surface', label: 'Surface' },
  { key: 'no_huddle', label: 'Tempo' },
  { key: 'game_state', label: 'Game State' },
  { key: 'opponent', label: 'Opponent' },
  { key: 'opp_division', label: 'Division' },
]

export const DEFENSE_SPLIT_CONFIG: { label: string; dims: Dim[]; metrics: Metric<DefensiveSplit>[] } = {
  label: 'Defense', dims: DEFENSE_DIMS, metrics: DEFENSE_METRICS,
}

export const DEFENSE_SITUATIONS: Situation[] = [
  { label: 'vs Pass', dim: 'vs_play', value: 'vs_pass' },
  { label: 'vs Run', dim: 'vs_play', value: 'vs_run' },
  { label: '3rd Down', dim: 'down', value: '3' },
  { label: 'Red Zone', dim: 'field_zone', value: 'red_zone' },
  { label: 'Trailing', dim: 'game_script', value: 'trailing' },
]
