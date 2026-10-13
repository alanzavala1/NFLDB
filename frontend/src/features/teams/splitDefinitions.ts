import type { TeamSplitCol } from './types'
import type { TeamSplit } from '../../types'

export const TEAM_SPLIT_DIMS: { key: string; label: string }[] = [
  { key: 'down',        label: 'Down' },
  { key: 'game_script', label: 'Game Script' },
  { key: 'field_zone',  label: 'Field Zone' },
  { key: 'quarter',     label: 'Quarter' },
  { key: 'game_state',  label: 'Game State' },
  { key: 'home_away',   label: 'Home/Away' },
  { key: 'roof',        label: 'Stadium' },
  { key: 'surface',     label: 'Surface' },
  { key: 'no_huddle',   label: 'Tempo' },
  { key: 'opp_division', label: 'Division' },
  { key: 'opponent',    label: 'Opponent' },
]

const TEAM_SPLIT_VALUE_LABELS: Record<string, string> = {
  '1': '1st Down', '2': '2nd Down', '3': '3rd Down', '4': '4th Down',
  leading: 'Leading', tied: 'Tied', trailing: 'Trailing',
  red_zone: 'Red Zone', opp_territory: 'Opp Territory', own_territory: 'Own Territory',
  competitive: 'Competitive', garbage: 'Garbage Time',
  home: 'Home', away: 'Away', dome: 'Dome', outdoors: 'Outdoors',
  grass: 'Grass', turf: 'Turf', huddle: 'Huddle', no_huddle: 'No-Huddle',
}

export function teamSplitValueLabel(dim: string, value: string): string {
  if (dim === 'quarter') return value === 'OT' ? 'OT' : `Q${value}`
  return TEAM_SPLIT_VALUE_LABELS[value] ?? value
}

export const fmtSign3 = (v: number | null | undefined) => v == null ? null : `${v >= 0 ? '+' : ''}${v.toFixed(3)}`

const fmtPct1  = (v: number | null | undefined) => v == null ? null : `${v.toFixed(1)}%`

const fmtNum2  = (v: number | null | undefined) => v == null ? null : v.toFixed(2)

export const TEAM_SPLIT_COLS: TeamSplitCol[] = [
  { label: 'PLAYS',    get: r => r.plays != null ? String(r.plays) : null },
  { label: 'EPA/play', get: r => fmtSign3(r.epa_play), signed: true, heat: 'epa' },
  { label: 'SUCC%',    get: r => fmtPct1(r.success_pct), heat: 'pct' },
  { label: 'YDS/play', get: r => fmtNum2(r.yards_play), highlight: true },
  { label: 'EXPL%',    get: r => fmtPct1(r.explosive_pct) },
  { label: 'PASS%',    get: r => fmtPct1(r.pass_rate) },
  { label: 'PASS EPA', get: r => fmtSign3(r.pass_epa), signed: true },
  { label: 'RUSH EPA', get: r => fmtSign3(r.rush_epa), signed: true },
]

export function aggregateTeamSplit(rows: TeamSplit[]): TeamSplit | null {
  if (rows.length === 0) return null
  const plays = rows.reduce((a, r) => a + (r.plays ?? 0), 0)
  const wavg = (f: (r: TeamSplit) => number | null | undefined) =>
    plays > 0 ? rows.reduce((a, r) => a + (f(r) ?? 0) * (r.plays ?? 0), 0) / plays : null
  return {
    side: rows[0].side, split_dim: rows[0].split_dim, split_value: '__total__', sort_order: 999,
    plays,
    epa_play: wavg(r => r.epa_play), success_pct: wavg(r => r.success_pct),
    pass_rate: wavg(r => r.pass_rate), yards_play: wavg(r => r.yards_play),
    explosive_pct: wavg(r => r.explosive_pct),
    pass_epa: wavg(r => r.pass_epa), rush_epa: wavg(r => r.rush_epa),
  }
}
