/**
 * Shared splits configuration for the Splits explorer.
 *
 * Defines, per entity kind (player category / team side), the dimensions you
 * can split by and the metrics you can compare on. A Metric carries both a
 * numeric accessor (for ranking + best-in-row shading) and a formatter (for
 * display). Also holds the value-label and career-aggregation helpers.
 */
import type { PlayerSplit, TeamSplit } from './api'

// ── Value labels ─────────────────────────────────────────────────────────────

const VALUE_LABELS: Record<string, string> = {
  '1': '1st Down', '2': '2nd Down', '3': '3rd Down', '4': '4th Down',
  short: 'Short', deep: 'Deep',
  left: 'Left', middle: 'Middle', right: 'Right',
  guard: 'Guard', tackle: 'Tackle', end: 'End',
  leading: 'Leading', tied: 'Tied', trailing: 'Trailing',
  shotgun: 'Shotgun', under_center: 'Under Center',
  red_zone: 'Red Zone', opp_territory: 'Opp Territory', own_territory: 'Own Territory',
}
export function splitValueLabel(dim: string, value: string): string {
  if (dim === 'quarter') return value === 'OT' ? 'OT' : `Q${value}`
  return VALUE_LABELS[value] ?? value
}

// ── Metric spec ──────────────────────────────────────────────────────────────

export type Metric<R> = {
  key: string
  label: string
  value: (r: R) => number | null      // numeric — for ranking / best-in-row
  fmt: (v: number) => string          // display string
  higherIsBetter?: boolean            // undefined ⇒ neutral (no winner shading)
}

const sgn = (v: number, d = 3) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`
const pct = (a: number | null | undefined, b: number | null | undefined) =>
  b && b > 0 ? ((a ?? 0) / b) * 100 : null
const per = (a: number | null | undefined, b: number | null | undefined) =>
  b && b > 0 ? (a ?? 0) / b : null

type Dim = { key: string; label: string }

const COMMON_PLAYER_DIMS: Dim[] = [
  { key: 'down', label: 'Down' },
  { key: 'game_script', label: 'Game Script' },
  { key: 'quarter', label: 'Quarter' },
  { key: 'shotgun', label: 'Formation' },
  { key: 'opponent', label: 'Opponent' },
  { key: 'opp_division', label: 'Division' },
]

// ── Player metrics ───────────────────────────────────────────────────────────

const PASSING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'epa',  label: 'EPA/att', value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'ya',   label: 'Y/A',     value: r => per(r.yards, r.att), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'cmp',  label: 'CMP%',    value: r => pct(r.cmp, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'succ', label: 'Success%',value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'cpoe', label: 'CPOE',    value: r => r.cpoe, fmt: v => sgn(v, 1), higherIsBetter: true },
  { key: 'td',   label: 'TD',      value: r => r.td, fmt: v => String(v), higherIsBetter: true },
  { key: 'yds',  label: 'Yards',   value: r => r.yards, fmt: v => String(v), higherIsBetter: true },
  { key: 'att',  label: 'Attempts',value: r => r.att, fmt: v => String(v) },
]

const RUSHING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'epa',  label: 'EPA/att', value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'ypc',  label: 'Y/C',     value: r => per(r.yards, r.att), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'succ', label: 'Success%',value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'td',   label: 'TD',      value: r => r.td, fmt: v => String(v), higherIsBetter: true },
  { key: 'yds',  label: 'Yards',   value: r => r.yards, fmt: v => String(v), higherIsBetter: true },
  { key: 'car',  label: 'Carries', value: r => r.att, fmt: v => String(v) },
]

const RECEIVING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'epa',  label: 'EPA/tgt', value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'ypr',  label: 'Y/R',     value: r => per(r.yards, r.cmp), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'cth',  label: 'Catch%',  value: r => pct(r.cmp, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'succ', label: 'Success%',value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'yac',  label: 'YAC',     value: r => r.yac, fmt: v => String(v), higherIsBetter: true },
  { key: 'td',   label: 'TD',      value: r => r.td, fmt: v => String(v), higherIsBetter: true },
  { key: 'yds',  label: 'Yards',   value: r => r.yards, fmt: v => String(v), higherIsBetter: true },
  { key: 'tgt',  label: 'Targets', value: r => r.att, fmt: v => String(v) },
]

export type PlayerCategory = 'passing' | 'rushing' | 'receiving'

export const PLAYER_SPLIT_CONFIG: Record<PlayerCategory, { label: string; dims: Dim[]; metrics: Metric<PlayerSplit>[] }> = {
  passing: {
    label: 'Passing',
    dims: [{ key: 'pass_depth', label: 'Pass Depth' }, { key: 'pass_location', label: 'Direction' }, ...COMMON_PLAYER_DIMS],
    metrics: PASSING_METRICS,
  },
  rushing: {
    label: 'Rushing',
    dims: [{ key: 'run_gap', label: 'Gap' }, { key: 'run_direction', label: 'Direction' }, ...COMMON_PLAYER_DIMS],
    metrics: RUSHING_METRICS,
  },
  receiving: {
    label: 'Receiving',
    dims: [{ key: 'target_depth', label: 'Target Depth' }, { key: 'target_direction', label: 'Direction' }, ...COMMON_PLAYER_DIMS],
    metrics: RECEIVING_METRICS,
  },
}

// ── Team metrics ─────────────────────────────────────────────────────────────

const TEAM_METRICS: Metric<TeamSplit>[] = [
  { key: 'epa',      label: 'EPA/play',   value: r => r.epa_play, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ',     label: 'Success%',   value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'ypp',      label: 'Yds/play',   value: r => r.yards_play, fmt: v => v.toFixed(2), higherIsBetter: true },
  { key: 'expl',     label: 'Explosive%', value: r => r.explosive_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'passepa',  label: 'Pass EPA',   value: r => r.pass_epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'rushepa',  label: 'Rush EPA',   value: r => r.rush_epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'passrate', label: 'Pass%',      value: r => r.pass_rate, fmt: v => v.toFixed(1) + '%' },
]

const TEAM_DIMS: Dim[] = [
  { key: 'down', label: 'Down' },
  { key: 'game_script', label: 'Game Script' },
  { key: 'field_zone', label: 'Field Zone' },
  { key: 'quarter', label: 'Quarter' },
]

export type TeamSide = 'offense' | 'defense'

export const TEAM_SPLIT_CONFIG: Record<TeamSide, { label: string; dims: Dim[]; metrics: Metric<TeamSplit>[] }> = {
  offense: { label: 'Offense', dims: TEAM_DIMS, metrics: TEAM_METRICS },
  defense: { label: 'Defense', dims: TEAM_DIMS, metrics: TEAM_METRICS },
}

// ── Career aggregation (player) ──────────────────────────────────────────────
// Counting stats sum; rate stats are attempt-weighted so a career row
// reconciles with the player's overall line for the split.

export function aggregatePlayerSplitRows(rows: PlayerSplit[]): PlayerSplit | null {
  if (rows.length === 0) return null
  const sum = (f: (r: PlayerSplit) => number | null | undefined) => rows.reduce((a, r) => a + (f(r) ?? 0), 0)
  const att = sum(r => r.att)
  const wavg = (f: (r: PlayerSplit) => number | null | undefined) =>
    att > 0 ? rows.reduce((a, r) => a + (f(r) ?? 0) * (r.att ?? 0), 0) / att : null
  return {
    season: rows[0].season, category: rows[0].category, split_dim: rows[0].split_dim,
    split_value: rows[0].split_value, sort_order: rows[0].sort_order,
    att, cmp: sum(r => r.cmp), yards: sum(r => r.yards), td: sum(r => r.td),
    interceptions: sum(r => r.interceptions), air_yards: sum(r => r.air_yards), yac: sum(r => r.yac),
    epa: wavg(r => r.epa), success_pct: wavg(r => r.success_pct), cpoe: wavg(r => r.cpoe),
  }
}

/** Group a dimension's rows by split_value across seasons, aggregating each. */
export function aggregateCareerByValue(rows: PlayerSplit[]): PlayerSplit[] {
  const byValue = new Map<string, PlayerSplit[]>()
  for (const r of rows) {
    const g = byValue.get(r.split_value)
    if (g) g.push(r); else byValue.set(r.split_value, [r])
  }
  const out: PlayerSplit[] = []
  for (const group of byValue.values()) {
    const agg = aggregatePlayerSplitRows(group)
    if (agg) out.push(agg)
  }
  return out
}

export const CAREER_SEASON = 0  // sentinel: aggregate across all seasons
