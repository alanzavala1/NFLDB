import type { PlayerSplit, TeamSplit, DefensiveSplit, PlayerGame } from '../../types'
import type { PlayerCategory } from './types'

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

// ── Career aggregation (player) ──────────────────────────────────────────────
// Counting stats sum; rate stats are attempt-weighted so a career row
// reconciles with the player's overall line for the split.

export function aggregatePlayerSplitRows(rows: PlayerSplit[]): PlayerSplit | null {
  if (rows.length === 0) return null
  const sum = (f: (r: PlayerSplit) => number | null | undefined) => rows.reduce((a, r) => a + (f(r) ?? 0), 0)
  const att = sum(r => r.att)
  const missingTargets = rows[0].category === 'receiving' && rows.some(r => r.att === null)
  const wavg = (f: (r: PlayerSplit) => number | null | undefined) =>
    att > 0 ? rows.reduce((a, r) => a + (f(r) ?? 0) * (r.att ?? 0), 0) / att : null
  return {
    season: rows[0].season, category: rows[0].category, split_dim: rows[0].split_dim,
    split_value: rows[0].split_value, sort_order: rows[0].sort_order,
    att: missingTargets ? null : att, cmp: sum(r => r.cmp), yards: sum(r => r.yards), td: sum(r => r.td),
    interceptions: sum(r => r.interceptions), air_yards: sum(r => r.air_yards), yac: sum(r => r.yac),
    first_downs: sum(r => r.first_downs),
    epa: missingTargets ? null : wavg(r => r.epa),
    success_pct: missingTargets ? null : wavg(r => r.success_pct), cpoe: wavg(r => r.cpoe),
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

// Map a singleEntity game-log row to the PlayerSplit shape so per-game rows reuse the
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
