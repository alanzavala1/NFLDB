import type { TeamAnalyticsRow } from '../../types'
import type { MetricSpec } from './types'

function fmtSigned(d = 3) { return (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}` }

function fmtPct(d = 1)    { return (v: number) => `${v.toFixed(d)}%` }

function fmtNum(d = 1)    { return (v: number) => v.toFixed(d) }

export function buildOffenseMetrics(t: TeamAnalyticsRow): MetricSpec[] {
  return [
    { key: 'ppg',    label: 'Points/Game',         hint: 'Avg points scored per game',                       value: t.ppg,                rank: t.ppg_rank,                fmt: fmtNum(1) },
    { key: 'ppd',    label: 'Points/Drive',        hint: 'Total points / total offensive drives',           value: t.pts_per_drive,      rank: t.pts_per_drive_rank,      fmt: fmtNum(2) },
    { key: 'epa',    label: 'EPA/play',            hint: 'Avg Expected Points Added per scrimmage play',    value: t.off_epa_play,       rank: t.off_epa_play_rank,       fmt: fmtSigned(3) },
    { key: 'pepa',   label: 'Pass EPA/db',         hint: 'EPA per dropback (incl. sacks)',                  value: t.off_pass_epa,       rank: t.off_pass_epa_rank,       fmt: fmtSigned(3) },
    { key: 'repa',   label: 'Rush EPA/play',       hint: 'EPA per rush attempt',                            value: t.off_rush_epa,       rank: t.off_rush_epa_rank,       fmt: fmtSigned(3) },
    { key: 'succ',   label: 'Success %',           hint: '% of plays with positive EPA',                    value: t.off_success_pct,    rank: t.off_success_rank,        fmt: fmtPct(1) },
    { key: 'expl',   label: 'Explosive %',         hint: '% of plays ≥20 pass or ≥10 rush yards', value: t.off_explosive_pct,  rank: t.off_explosive_rank,      fmt: fmtPct(1) },
    { key: '3dp',    label: '3rd Down %',          hint: '3rd down conversion rate',                        value: t.third_down_pct,     rank: t.third_down_rank,         fmt: fmtPct(1) },
    { key: 'rztd',   label: 'Red Zone TD %',       hint: 'TDs scored / red zone drive trips',               value: t.rz_td_pct,          rank: t.rz_td_rank,              fmt: fmtPct(1) },
    { key: 'proe',   label: 'PROE',                hint: 'Pass Rate Over Expected (style indicator)',       value: t.proe,               rank: t.proe_rank,               fmt: fmtSigned(1) },
  ]
}

export function buildDefenseMetrics(t: TeamAnalyticsRow): MetricSpec[] {
  return [
    { key: 'papg',   label: 'Points/G allowed',    hint: 'Opponent points per game',                        value: t.papg,                       rank: t.papg_rank,                      fmt: fmtNum(1) },
    { key: 'ppda',   label: 'Points/Drive allowed',hint: 'Opponent points per drive',                       value: t.pts_per_drive_allowed,      rank: t.pts_per_drive_allowed_rank,     fmt: fmtNum(2) },
    { key: 'depa',   label: 'EPA/play allowed',    hint: 'Opponent EPA per scrimmage play',                 value: t.def_epa_play,               rank: t.def_epa_play_rank,              fmt: fmtSigned(3) },
    { key: 'dpepa',  label: 'Pass EPA/db allowed', hint: 'Opponent EPA per dropback',                       value: t.def_pass_epa,               rank: t.def_pass_epa_rank,              fmt: fmtSigned(3) },
    { key: 'drepa',  label: 'Rush EPA/play allowed', hint: 'Opponent EPA per rush',                         value: t.def_rush_epa,               rank: t.def_rush_epa_rank,              fmt: fmtSigned(3) },
    { key: 'dsucc',  label: 'Success % allowed',   hint: '% of opponent plays with positive EPA',           value: t.def_success_pct,            rank: t.def_success_rank,               fmt: fmtPct(1) },
    { key: 'dexpl',  label: 'Explosive % allowed', hint: 'Opponent explosive play rate',                    value: t.def_explosive_pct,          rank: t.def_explosive_rank,             fmt: fmtPct(1) },
    { key: '3ds',    label: '3rd Down Stop %',     hint: '% of opponent 3rd downs stopped',                 value: t.third_down_stop_pct,        rank: t.third_down_stop_rank,           fmt: fmtPct(1) },
    { key: 'rzta',   label: 'Red Zone TD % allowed', hint: 'TDs allowed / opponent RZ trips',               value: t.rz_td_pct_allowed,          rank: t.rz_td_allowed_rank,             fmt: fmtPct(1) },
    { key: 'sack',   label: 'Sack Rate',           hint: 'Sacks / opponent dropbacks',                      value: t.def_sack_pct,               rank: t.def_sack_rank,                  fmt: fmtPct(1) },
  ]
}

export function buildOverallMetrics(t: TeamAnalyticsRow): MetricSpec[] {
  return [
    { key: 'ptdiff', label: 'Point Diff / Game',   hint: '(PF − PA) / games',                               value: t.pt_diff_per_game,           rank: t.pt_diff_rank,                   fmt: fmtSigned(1) },
    { key: 'todiff', label: 'Turnover Diff / Game',hint: '(takeaways − giveaways) / games',                 value: t.turnover_diff_per_game,     rank: t.to_diff_rank,                   fmt: fmtSigned(2) },
  ]
}
