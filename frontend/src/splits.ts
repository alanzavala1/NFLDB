/**
 * Shared splits configuration for the Splits explorer.
 *
 * Defines, per entity kind (player category / team side), the dimensions you
 * can split by and the metrics you can compare on. A Metric carries both a
 * numeric accessor (for ranking + best-in-row shading) and a formatter (for
 * display). Also holds the value-label and career-aggregation helpers.
 */
import type { PlayerSplit, TeamSplit, PlayerGame, DefensiveSplit } from './api'

// ── Value labels ─────────────────────────────────────────────────────────────

const VALUE_LABELS: Record<string, string> = {
  '1': '1st Down', '2': '2nd Down', '3': '3rd Down', '4': '4th Down',
  short: 'Short', deep: 'Deep',
  left: 'Left', middle: 'Middle', right: 'Right',
  guard: 'Guard', tackle: 'Tackle', end: 'End',
  leading: 'Leading', tied: 'Tied', trailing: 'Trailing',
  shotgun: 'Shotgun', under_center: 'Under Center',
  red_zone: 'Red Zone', opp_territory: 'Opp Territory', own_territory: 'Own Territory',
  vs_pass: 'vs Pass', vs_run: 'vs Run',
  home: 'Home', away: 'Away',
  dome: 'Dome', outdoors: 'Outdoors', grass: 'Grass', turf: 'Turf',
  no_huddle: 'No-Huddle', huddle: 'Huddle', pressured: 'Under Pressure', clean: 'Clean Pocket',
  competitive: 'Competitive', garbage: 'Garbage Time',
  play_action: 'Play Action', no_pa: 'No Play Action',
  blitz: 'vs Blitz (5+)', standard_rush: 'Standard Rush',
  light_box: 'Light Box (≤6)', neutral_box: 'Neutral Box (7)', stacked_box: 'Stacked Box (8+)',
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
  group?: string                      // section header in the Compare view
}

const sgn = (v: number, d = 3) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`
const pct = (a: number | null | undefined, b: number | null | undefined) =>
  b && b > 0 ? ((a ?? 0) / b) * 100 : null
const per = (a: number | null | undefined, b: number | null | undefined) =>
  b && b > 0 ? (a ?? 0) / b : null

function passerRating(cmp: number, att: number, yds: number, td: number, int: number): number | null {
  if (att <= 0) return null
  const clamp = (x: number) => Math.max(0, Math.min(2.375, x))
  const a = clamp(((cmp / att) - 0.3) * 5)
  const b = clamp(((yds / att) - 3) * 0.25)
  const c = clamp((td / att) * 20)
  const d = clamp(2.375 - (int / att) * 25)
  return ((a + b + c + d) / 6) * 100
}

type Dim = { key: string; label: string }

const COMMON_PLAYER_DIMS: Dim[] = [
  { key: 'down', label: 'Down' },
  { key: 'game_script', label: 'Game Script' },
  { key: 'quarter', label: 'Quarter' },
  { key: 'shotgun', label: 'Formation' },
  { key: 'field_zone', label: 'Field Zone' },
  { key: 'home_away', label: 'Home/Away' },
  { key: 'roof', label: 'Stadium' },
  { key: 'surface', label: 'Surface' },
  { key: 'no_huddle', label: 'Tempo' },
  { key: 'game_state', label: 'Game State' },
  { key: 'opponent', label: 'Opponent' },
  { key: 'opp_division', label: 'Division' },
]

// ── Player metrics ───────────────────────────────────────────────────────────

const intStr = (v: number) => String(v)
// Comprehensive metric lists — these are the rows shown in the Compare view
// (and the options in the By-Split pivot's metric dropdown).
const PASSING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'att',  label: 'ATT',     group: 'Production', value: r => r.att, fmt: intStr },
  { key: 'cmp',  label: 'CMP',     group: 'Production', value: r => r.cmp, fmt: intStr },
  { key: 'yds',  label: 'YDS',     group: 'Production', value: r => r.yards, fmt: intStr, higherIsBetter: true },
  { key: 'td',   label: 'TD',      group: 'Production', value: r => r.td, fmt: intStr, higherIsBetter: true },
  { key: 'int',  label: 'INT',     group: 'Production', value: r => r.interceptions, fmt: intStr, higherIsBetter: false },
  { key: 'cmpp', label: 'CMP%',    group: 'Efficiency', value: r => pct(r.cmp, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'ya',   label: 'Y/A',     group: 'Efficiency', value: r => per(r.yards, r.att), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'rate', label: 'RATE',    group: 'Efficiency', value: r => passerRating(r.cmp ?? 0, r.att ?? 0, r.yards ?? 0, r.td ?? 0, r.interceptions ?? 0), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'adot', label: 'aDOT',    group: 'Efficiency', value: r => per(r.air_yards, r.att), fmt: v => v.toFixed(1) },
  { key: 'yac',  label: 'YAC/cmp', group: 'Efficiency', value: r => per(r.yac, r.cmp), fmt: v => v.toFixed(1) },
  { key: 'epa',  label: 'EPA/att', group: 'Advanced',   value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ', label: 'Success%',group: 'Advanced',   value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'cpoe', label: 'CPOE',    group: 'Advanced',   value: r => r.cpoe, fmt: v => sgn(v, 1), higherIsBetter: true },
  { key: 'conv', label: 'Conv%',   group: 'Situational',value: r => pct(r.first_downs, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'tdpct',label: 'TD%',     group: 'Situational',value: r => pct(r.td, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
]

const RUSHING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'car',  label: 'CAR',     group: 'Production', value: r => r.att, fmt: intStr },
  { key: 'yds',  label: 'YDS',     group: 'Production', value: r => r.yards, fmt: intStr, higherIsBetter: true },
  { key: 'td',   label: 'TD',      group: 'Production', value: r => r.td, fmt: intStr, higherIsBetter: true },
  { key: 'ypc',  label: 'Y/C',     group: 'Efficiency', value: r => per(r.yards, r.att), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'epa',  label: 'EPA/att', group: 'Advanced',   value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ', label: 'Success%',group: 'Advanced',   value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'conv', label: 'Conv%',   group: 'Situational',value: r => pct(r.first_downs, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'tdpct',label: 'TD%',     group: 'Situational',value: r => pct(r.td, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
]

const RECEIVING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'tgt',  label: 'TGT',     group: 'Production', value: r => r.att, fmt: intStr },
  { key: 'rec',  label: 'REC',     group: 'Production', value: r => r.cmp, fmt: intStr, higherIsBetter: true },
  { key: 'yds',  label: 'YDS',     group: 'Production', value: r => r.yards, fmt: intStr, higherIsBetter: true },
  { key: 'td',   label: 'TD',      group: 'Production', value: r => r.td, fmt: intStr, higherIsBetter: true },
  { key: 'cth',  label: 'Catch%',  group: 'Efficiency', value: r => pct(r.cmp, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'ypr',  label: 'Y/R',     group: 'Efficiency', value: r => per(r.yards, r.cmp), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'ytgt', label: 'Y/Tgt',   group: 'Efficiency', value: r => per(r.yards, r.att), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'adot', label: 'aDOT',    group: 'Efficiency', value: r => per(r.air_yards, r.att), fmt: v => v.toFixed(1) },
  { key: 'yac',  label: 'YAC',     group: 'Efficiency', value: r => r.yac, fmt: intStr, higherIsBetter: true },
  { key: 'epa',  label: 'EPA/tgt', group: 'Advanced',   value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ', label: 'Success%',group: 'Advanced',   value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'conv', label: 'Conv%',   group: 'Situational',value: r => pct(r.first_downs, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'tdpct',label: 'TD%',     group: 'Situational',value: r => pct(r.td, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
]

export type PlayerCategory = 'passing' | 'rushing' | 'receiving'

export const PLAYER_SPLIT_CONFIG: Record<PlayerCategory, { label: string; dims: Dim[]; metrics: Metric<PlayerSplit>[] }> = {
  passing: {
    label: 'Passing',
    dims: [{ key: 'pass_depth', label: 'Pass Depth' }, { key: 'pass_location', label: 'Direction' }, { key: 'pressure', label: 'Pressure' }, { key: 'play_action', label: 'Play Action' }, { key: 'blitz', label: 'Blitz' }, ...COMMON_PLAYER_DIMS],
    metrics: PASSING_METRICS,
  },
  rushing: {
    label: 'Rushing',
    dims: [{ key: 'run_gap', label: 'Gap' }, { key: 'run_direction', label: 'Direction' }, { key: 'box_count', label: 'Box Count' }, ...COMMON_PLAYER_DIMS],
    metrics: RUSHING_METRICS,
  },
  receiving: {
    label: 'Receiving',
    dims: [{ key: 'target_depth', label: 'Target Depth' }, { key: 'target_direction', label: 'Direction' }, { key: 'pressure', label: 'Pressure' }, { key: 'play_action', label: 'Play Action' }, { key: 'blitz', label: 'Blitz' }, ...COMMON_PLAYER_DIMS],
    metrics: RECEIVING_METRICS,
  },
}

// ── Defensive player metrics ─────────────────────────────────────────────────
// Event counts (more is always better). No coverage data exists in nflfastR,
// so these are tackles / pass-rush / takeaway production, not coverage.

const DEFENSE_METRICS: Metric<DefensiveSplit>[] = [
  { key: 'tackles', label: 'Tackles', group: 'Tackling',  value: r => r.tackles, fmt: v => v.toFixed(0), higherIsBetter: true },
  { key: 'solo',    label: 'Solo',    group: 'Tackling',  value: r => r.solo, fmt: intStr, higherIsBetter: true },
  { key: 'tfl',     label: 'TFL',     group: 'Tackling',  value: r => r.tfl, fmt: intStr, higherIsBetter: true },
  { key: 'sacks',   label: 'Sacks',   group: 'Pass Rush', value: r => r.sacks, fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'qb_hits', label: 'QB Hits', group: 'Pass Rush', value: r => r.qb_hits, fmt: intStr, higherIsBetter: true },
  { key: 'int',     label: 'INT',     group: 'Coverage',  value: r => r.interceptions, fmt: intStr, higherIsBetter: true },
  { key: 'pbu',     label: 'PBU',     group: 'Coverage',  value: r => r.pass_breakups, fmt: intStr, higherIsBetter: true },
  { key: 'ff',      label: 'FF',      group: 'Takeaways', value: r => r.forced_fumbles, fmt: intStr, higherIsBetter: true },
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

/** Sum a defender's event rows (counting stats only). */
export function aggregateDefenseSplitRows(rows: DefensiveSplit[]): DefensiveSplit | null {
  if (rows.length === 0) return null
  const sum = (f: (r: DefensiveSplit) => number | null | undefined) => rows.reduce((a, r) => a + (f(r) ?? 0), 0)
  return {
    season: rows[0].season, split_dim: rows[0].split_dim, split_value: rows[0].split_value, sort_order: rows[0].sort_order,
    tackles: sum(r => r.tackles), solo: sum(r => r.solo), assists: sum(r => r.assists), tfl: sum(r => r.tfl),
    sacks: sum(r => r.sacks), qb_hits: sum(r => r.qb_hits), interceptions: sum(r => r.interceptions),
    pass_breakups: sum(r => r.pass_breakups), forced_fumbles: sum(r => r.forced_fumbles),
  }
}

/** Group a dimension's defensive rows by split_value across seasons. */
export function aggregateDefenseCareerByValue(rows: DefensiveSplit[]): DefensiveSplit[] {
  const byValue = new Map<string, DefensiveSplit[]>()
  for (const r of rows) { const g = byValue.get(r.split_value); if (g) g.push(r); else byValue.set(r.split_value, [r]) }
  const out: DefensiveSplit[] = []
  for (const g of byValue.values()) { const agg = aggregateDefenseSplitRows(g); if (agg) out.push(agg) }
  return out
}

// ── Team metrics ─────────────────────────────────────────────────────────────

const TEAM_METRICS: Metric<TeamSplit>[] = [
  { key: 'plays',    label: 'Plays',      group: 'Volume',     value: r => r.plays, fmt: intStr },
  { key: 'epa',      label: 'EPA/play',   group: 'Efficiency', value: r => r.epa_play, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ',     label: 'Success%',   group: 'Efficiency', value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'ypp',      label: 'Yds/play',   group: 'Efficiency', value: r => r.yards_play, fmt: v => v.toFixed(2), higherIsBetter: true },
  { key: 'expl',     label: 'Explosive%', group: 'Efficiency', value: r => r.explosive_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'passepa',  label: 'Pass EPA',   group: 'By type',    value: r => r.pass_epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'rushepa',  label: 'Rush EPA',   group: 'By type',    value: r => r.rush_epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'passrate', label: 'Pass%',      group: 'By type',    value: r => r.pass_rate, fmt: v => v.toFixed(1) + '%' },
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
    first_downs: sum(r => r.first_downs),
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

export function aggregateTeamSplitRows(rows: TeamSplit[]): TeamSplit | null {
  if (rows.length === 0) return null
  const plays = rows.reduce((a, r) => a + (r.plays ?? 0), 0)
  const w = (f: (r: TeamSplit) => number | null | undefined) =>
    plays > 0 ? rows.reduce((a, r) => a + (f(r) ?? 0) * (r.plays ?? 0), 0) / plays : null
  return {
    side: rows[0].side, split_dim: rows[0].split_dim, split_value: rows[0].split_value, sort_order: rows[0].sort_order,
    plays, epa_play: w(r => r.epa_play), success_pct: w(r => r.success_pct), pass_rate: w(r => r.pass_rate),
    yards_play: w(r => r.yards_play), explosive_pct: w(r => r.explosive_pct),
    pass_epa: w(r => r.pass_epa), rush_epa: w(r => r.rush_epa),
  }
}

// ── Quick situational presets (the prominent filter chips) ───────────────────

export type Situation = { label: string; dim: string; value: string }

export const PLAYER_SITUATIONS: Record<PlayerCategory, Situation[]> = {
  passing: [
    { label: 'Deep', dim: 'pass_depth', value: 'deep' },
    { label: 'Short', dim: 'pass_depth', value: 'short' },
    { label: '3rd Down', dim: 'down', value: '3' },
    { label: '1st Down', dim: 'down', value: '1' },
    { label: 'Red Zone', dim: 'field_zone', value: 'red_zone' },
    { label: 'Under Pressure', dim: 'pressure', value: 'pressured' },
    { label: 'Play Action', dim: 'play_action', value: 'play_action' },
    { label: 'vs Blitz', dim: 'blitz', value: 'blitz' },
    { label: 'Competitive', dim: 'game_state', value: 'competitive' },
    { label: 'Dome', dim: 'roof', value: 'dome' },
    { label: 'Trailing', dim: 'game_script', value: 'trailing' },
    { label: 'Leading', dim: 'game_script', value: 'leading' },
    { label: 'Shotgun', dim: 'shotgun', value: 'shotgun' },
  ],
  rushing: [
    { label: '3rd Down', dim: 'down', value: '3' },
    { label: '1st Down', dim: 'down', value: '1' },
    { label: 'Red Zone', dim: 'field_zone', value: 'red_zone' },
    { label: 'Stacked Box', dim: 'box_count', value: 'stacked_box' },
    { label: 'Light Box', dim: 'box_count', value: 'light_box' },
    { label: 'Competitive', dim: 'game_state', value: 'competitive' },
    { label: 'Off Guard', dim: 'run_gap', value: 'guard' },
    { label: 'Off End', dim: 'run_gap', value: 'end' },
    { label: 'Trailing', dim: 'game_script', value: 'trailing' },
    { label: 'Shotgun', dim: 'shotgun', value: 'shotgun' },
  ],
  receiving: [
    { label: 'Deep', dim: 'target_depth', value: 'deep' },
    { label: 'Short', dim: 'target_depth', value: 'short' },
    { label: '3rd Down', dim: 'down', value: '3' },
    { label: 'Red Zone', dim: 'field_zone', value: 'red_zone' },
    { label: 'Under Pressure', dim: 'pressure', value: 'pressured' },
    { label: 'Play Action', dim: 'play_action', value: 'play_action' },
    { label: 'vs Blitz', dim: 'blitz', value: 'blitz' },
    { label: 'Competitive', dim: 'game_state', value: 'competitive' },
    { label: 'Trailing', dim: 'game_script', value: 'trailing' },
    { label: 'Shotgun', dim: 'shotgun', value: 'shotgun' },
  ],
}

export const TEAM_SITUATIONS: Situation[] = [
  { label: 'Red Zone', dim: 'field_zone', value: 'red_zone' },
  { label: '3rd Down', dim: 'down', value: '3' },
  { label: 'Competitive', dim: 'game_state', value: 'competitive' },
  { label: 'Dome', dim: 'roof', value: 'dome' },
  { label: 'Trailing', dim: 'game_script', value: 'trailing' },
  { label: 'Leading', dim: 'game_script', value: 'leading' },
]

// Map a single game-log row to the PlayerSplit shape so per-game rows reuse the
// same columns. Rate fields the game log doesn't carry (success%, cpoe) are
// null; epa is converted to a per-attempt average to match the split metric.
export function gameToSplitRow(g: PlayerGame, cat: PlayerCategory): PlayerSplit {
  const base = {
    season: g.season, category: cat, split_dim: 'game', split_value: g.game_id, sort_order: g.week,
    att: null as number | null, cmp: null as number | null, yards: null as number | null, td: null as number | null,
    interceptions: null as number | null, air_yards: null as number | null, yac: null as number | null,
    first_downs: null as number | null,
    epa: null as number | null, success_pct: null as number | null, cpoe: null as number | null,
  }
  if (cat === 'passing') return { ...base, att: g.attempts, cmp: g.completions, yards: g.pass_yards, td: g.pass_tds, interceptions: g.interceptions_thrown, air_yards: g.air_yards, yac: g.yac, epa: g.attempts ? g.pass_epa / g.attempts : null }
  if (cat === 'rushing') return { ...base, att: g.carries, yards: g.rush_yards, td: g.rush_tds, epa: g.carries ? g.rush_epa / g.carries : null }
  return { ...base, att: g.targets, cmp: g.receptions, yards: g.rec_yards, td: g.rec_tds, air_yards: g.air_yards, yac: g.yac, epa: g.targets ? g.rec_epa / g.targets : null }
}

export const CAREER_SEASON = 0  // sentinel: aggregate across all seasons

// Dimension that fully partitions every play (no NULL bucket) — summing all
// its values yields the "Overall" (unfiltered) row. `down` is set on every
// scrimmage pass/run play, so it covers all of them.
export const OVERALL_DIM = 'down'
