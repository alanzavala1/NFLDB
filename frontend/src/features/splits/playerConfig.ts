import type { PlayerSplit } from '../../types'
import type { Dim, Metric, PlayerCategory, Situation } from './types'
import { sgn, pct, per, passerRating, intStr } from './metricFormatting'

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

// Comprehensive metric lists — these are the rows shown in the Compare view
// (and the options in the By-Split pivot's metric dropdown).
const PASSING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'att', label: 'ATT', group: 'Production', value: r => r.att, fmt: intStr },
  { key: 'cmp', label: 'CMP', group: 'Production', value: r => r.cmp, fmt: intStr },
  { key: 'yds', label: 'YDS', group: 'Production', value: r => r.yards, fmt: intStr, higherIsBetter: true },
  { key: 'td', label: 'TD', group: 'Production', value: r => r.td, fmt: intStr, higherIsBetter: true },
  { key: 'int', label: 'INT', group: 'Production', value: r => r.interceptions, fmt: intStr, higherIsBetter: false },
  { key: 'cmpp', label: 'CMP%', group: 'Efficiency', value: r => pct(r.cmp, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'ya', label: 'Y/A', group: 'Efficiency', value: r => per(r.yards, r.att), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'rate', label: 'RATE', group: 'Efficiency', value: r => passerRating(r.cmp ?? 0, r.att ?? 0, r.yards ?? 0, r.td ?? 0, r.interceptions ?? 0), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'adot', label: 'aDOT', group: 'Efficiency', value: r => per(r.air_yards, r.att), fmt: v => v.toFixed(1) },
  { key: 'yac', label: 'YAC/cmp', group: 'Efficiency', value: r => per(r.yac, r.cmp), fmt: v => v.toFixed(1) },
  { key: 'epa', label: 'EPA/att', group: 'Advanced', value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ', label: 'Success%', group: 'Advanced', value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'cpoe', label: 'CPOE', group: 'Advanced', value: r => r.cpoe, fmt: v => sgn(v, 1), higherIsBetter: true },
  { key: 'conv', label: 'Conv%', group: 'Situational', value: r => pct(r.first_downs, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'tdpct', label: 'TD%', group: 'Situational', value: r => pct(r.td, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
]

const RUSHING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'car', label: 'CAR', group: 'Production', value: r => r.att, fmt: intStr },
  { key: 'yds', label: 'YDS', group: 'Production', value: r => r.yards, fmt: intStr, higherIsBetter: true },
  { key: 'td', label: 'TD', group: 'Production', value: r => r.td, fmt: intStr, higherIsBetter: true },
  { key: 'ypc', label: 'Y/C', group: 'Efficiency', value: r => per(r.yards, r.att), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'epa', label: 'EPA/att', group: 'Advanced', value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ', label: 'Success%', group: 'Advanced', value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'conv', label: 'Conv%', group: 'Situational', value: r => pct(r.first_downs, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'tdpct', label: 'TD%', group: 'Situational', value: r => pct(r.td, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
]

const RECEIVING_METRICS: Metric<PlayerSplit>[] = [
  { key: 'tgt', label: 'TGT', group: 'Production', value: r => r.att, fmt: intStr },
  { key: 'rec', label: 'REC', group: 'Production', value: r => r.cmp, fmt: intStr, higherIsBetter: true },
  { key: 'yds', label: 'YDS', group: 'Production', value: r => r.yards, fmt: intStr, higherIsBetter: true },
  { key: 'td', label: 'TD', group: 'Production', value: r => r.td, fmt: intStr, higherIsBetter: true },
  { key: 'cth', label: 'Catch%', group: 'Efficiency', value: r => pct(r.cmp, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'ypr', label: 'Y/R', group: 'Efficiency', value: r => per(r.yards, r.cmp), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'ytgt', label: 'Y/Tgt', group: 'Efficiency', value: r => per(r.yards, r.att), fmt: v => v.toFixed(1), higherIsBetter: true },
  { key: 'adot', label: 'aDOT', group: 'Efficiency', value: r => per(r.air_yards, r.att), fmt: v => v.toFixed(1) },
  { key: 'yac', label: 'YAC', group: 'Efficiency', value: r => r.yac, fmt: intStr, higherIsBetter: true },
  { key: 'epa', label: 'EPA/tgt', group: 'Advanced', value: r => r.epa, fmt: v => sgn(v, 3), higherIsBetter: true },
  { key: 'succ', label: 'Success%', group: 'Advanced', value: r => r.success_pct, fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'conv', label: 'Conv%', group: 'Situational', value: r => pct(r.first_downs, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
  { key: 'tdpct', label: 'TD%', group: 'Situational', value: r => pct(r.td, r.att), fmt: v => v.toFixed(1) + '%', higherIsBetter: true },
]

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
