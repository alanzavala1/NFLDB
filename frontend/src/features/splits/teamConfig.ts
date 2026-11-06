import type { TeamSplit } from '../../types'
import type { Dim, Metric, TeamSide, Situation } from './types'
import { sgn, intStr } from './metricFormatting'

// ── Team metrics ─────────────────────────────────────────────────────────────

const TEAM_METRICS: Metric<TeamSplit>[] = [
  { key: 'plays', label: 'Plays', group: 'Volume', value: r => r.plays, fmt: intStr },
  { key: 'epa', label: 'EPA/play', group: 'Efficiency', value: r => r.epa_play, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ', label: 'Success%', group: 'Efficiency', value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'ypp', label: 'Yds/play', group: 'Efficiency', value: r => r.yards_play, fmt: v => v.toFixed(2), higherIsBetter: true },
  { key: 'expl', label: 'Explosive%', group: 'Efficiency', value: r => r.explosive_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'passepa', label: 'Pass EPA', group: 'By type', value: r => r.pass_epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'rushepa', label: 'Rush EPA', group: 'By type', value: r => r.rush_epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'passrate', label: 'Pass%', group: 'By type', value: r => r.pass_rate, fmt: v => v.toFixed(1) + '%' },
]

const TEAM_DIMS: Dim[] = [
  { key: 'down', label: 'Down' },
  { key: 'game_script', label: 'Game Script' },
  { key: 'field_zone', label: 'Field Zone' },
  { key: 'quarter', label: 'Quarter' },
  { key: 'home_away', label: 'Home/Away' },
  { key: 'roof', label: 'Stadium' },
  { key: 'surface', label: 'Surface' },
  { key: 'no_huddle', label: 'Tempo' },
  { key: 'game_state', label: 'Game State' },
  { key: 'opponent', label: 'Opponent' },
  { key: 'opp_division', label: 'Division' },
]

export const TEAM_SPLIT_CONFIG: Record<TeamSide, { label: string; dims: Dim[]; metrics: Metric<TeamSplit>[] }> = {
  offense: { label: 'Offense', dims: TEAM_DIMS, metrics: TEAM_METRICS },
  defense: { label: 'Defense', dims: TEAM_DIMS, metrics: TEAM_METRICS },
}

export const TEAM_SITUATIONS: Situation[] = [
  { label: 'Red Zone', dim: 'field_zone', value: 'red_zone' },
  { label: '3rd Down', dim: 'down', value: '3' },
  { label: 'Competitive', dim: 'game_state', value: 'competitive' },
  { label: 'Dome', dim: 'roof', value: 'dome' },
  { label: 'Trailing', dim: 'game_script', value: 'trailing' },
  { label: 'Leading', dim: 'game_script', value: 'leading' },
]
