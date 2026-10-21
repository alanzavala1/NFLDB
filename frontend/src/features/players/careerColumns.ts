import type { NgsStats, SnapTotals, SituationalStats, PlayerWpa, PlayerAdvStats, KickingStats } from '../../types'
import { passerRating, pct, ratio, sfmt, dfmt, type Totals } from './stats'
import { hasReceivingActivity } from '../../utils/receiving'

export type ColKind = 'trad' | 'adv' | 'ngs' | 'snap' | 'sit'

export type Col = {
  key: string; label: string; kind: ColKind; group?: string; wpaOnly?: boolean; signed?: boolean; highlight?: boolean
  // `derived` marks trad columns whose value needs data beyond (totals, games)
  // — e.g. play-by-play kicking splits. TeamSplits skips these since it only
  // has per-team game totals, not the per-season derived dicts.
  derived?: boolean
  cell: (t: Totals, games: number, n?: NgsStats, sn?: SnapTotals, sit?: SituationalStats, w?: PlayerWpa, a?: PlayerAdvStats, k?: KickingStats) => string | number | null
}

export const QB_COLS: Col[] = [
  { key: 'g',    label: 'G',       kind: 'trad',                        cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',     kind: 'snap',                        cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',    kind: 'snap',                        cell: (_, __, _n, sn) => sn ? `${(sn.avg_offense_pct ?? 0).toFixed(0)}%` : null },
  // Passing
  { key: 'cmp',  label: 'CMP',     kind: 'trad', group: 'Passing',      cell: t => t.completions },
  { key: 'att',  label: 'ATT',     kind: 'trad', group: 'Passing',      cell: t => t.attempts },
  { key: 'cpct', label: 'CMP%',    kind: 'trad', group: 'Passing',      cell: t => pct(t.completions, t.attempts) },
  { key: 'yds',  label: 'YDS',     kind: 'trad', group: 'Passing', highlight: true, cell: t => t.pass_yards },
  { key: 'td',   label: 'TD',      kind: 'trad', group: 'Passing',      cell: t => t.pass_tds },
  { key: 'int',  label: 'INT',     kind: 'trad', group: 'Passing',      cell: t => t.interceptions_thrown },
  { key: 'ya',   label: 'Y/A',     kind: 'trad', group: 'Passing',      cell: t => ratio(t.pass_yards, t.attempts) },
  { key: 'sck',  label: 'SACK',    kind: 'trad', group: 'Passing',      cell: t => t.sacks_taken },
  { key: 'rate', label: 'RATE',    kind: 'trad', group: 'Passing',      cell: t => passerRating(t.completions, t.attempts, t.pass_yards, t.pass_tds, t.interceptions_thrown) },
  // Rushing
  { key: 'car',  label: 'CAR',     kind: 'trad', group: 'Rushing',      cell: t => t.carries > 0 ? t.carries : null },
  { key: 'ryds', label: 'YDS',     kind: 'trad', group: 'Rushing',      cell: t => t.carries > 0 ? t.rush_yards : null },
  { key: 'rtd',  label: 'TD',      kind: 'trad', group: 'Rushing',      cell: t => t.carries > 0 && t.rush_tds > 0 ? t.rush_tds : null },
  { key: 'rypc', label: 'Y/C',     kind: 'trad', group: 'Rushing',      cell: t => t.carries > 0 ? ratio(t.rush_yards, t.carries) : null },
  // Advanced / NGS / Situational / WPA
  { key: 'aya',  label: 'AY/A',    kind: 'adv',                         cell: t => t.attempts > 0 ? ((t.pass_yards + 20 * t.pass_tds - 45 * t.interceptions_thrown) / t.attempts).toFixed(1) : null },
  { key: 'epaa', label: 'EPA/Att', kind: 'adv',  signed: true,          cell: t => t.attempts > 0 ? sfmt(t.pass_epa / t.attempts, 3) : null },
  { key: 'qbfl', label: 'FUM',     kind: 'adv',                         cell: (_, __, _n, _sn, _sit, _w, a) => a?.fumbles_lost != null ? a.fumbles_lost : null },
  { key: 'pwpa', label: 'WPA',     kind: 'adv',  wpaOnly: true, signed: true, cell: (_, __, _n, _sn, _sit, w) => w?.pass_wpa != null ? sfmt(w.pass_wpa, 3) : null },
  { key: 'cpoe', label: 'CPOE',    kind: 'ngs',  signed: true,          cell: (_, __, n) => sfmt(n?.cpoe) },
  { key: 'ttt',  label: 'TTT',     kind: 'ngs',                         cell: (_, __, n) => n?.avg_time_to_throw != null ? `${n.avg_time_to_throw.toFixed(2)}s` : null },
  { key: 'adot', label: 'aDOT',    kind: 'ngs',                         cell: (_, __, n) => dfmt(n?.adot) },
  { key: 'agg',  label: 'AGG%',    kind: 'ngs',                         cell: (_, __, n) => n?.aggressiveness != null ? `${n.aggressiveness.toFixed(1)}%` : null },
  { key: 'xcmp', label: 'xCMP%',   kind: 'ngs',                         cell: (_, __, n) => n?.expected_cmp_pct != null ? `${n.expected_cmp_pct.toFixed(1)}%` : null },
  { key: 'rzd',  label: 'RZ TD',   kind: 'sit',                         cell: (_, __, _n, _sn, sit) => sit?.rz_pass_tds ?? null },
  { key: 'rzp',  label: 'RZ%',     kind: 'sit',                         cell: (_, __, _n, _sn, sit) => sit?.rz_pass_att ? pct(sit.rz_pass_tds ?? 0, sit.rz_pass_att) + '%' : null },
  { key: 'tdp',  label: '3D%',     kind: 'sit',                         cell: (_, __, _n, _sn, sit) => sit?.third_pass_att ? pct(sit.third_pass_fd ?? 0, sit.third_pass_att) + '%' : null },
  { key: 'lng',  label: 'LNG',     kind: 'sit',                         cell: (_, __, _n, _sn, sit) => sit?.lng_pass ?? null },
]

export const RB_COLS: Col[] = [
  { key: 'g',    label: 'G',       kind: 'trad',                        cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',     kind: 'snap',                        cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',    kind: 'snap',                        cell: (_, __, _n, sn) => sn ? `${(sn.avg_offense_pct ?? 0).toFixed(0)}%` : null },
  // Rushing
  { key: 'car',  label: 'CAR',     kind: 'trad', group: 'Rushing',      cell: t => t.carries },
  { key: 'ryds', label: 'YDS',     kind: 'trad', group: 'Rushing', highlight: true, cell: t => t.rush_yards },
  { key: 'ypc',  label: 'Y/C',     kind: 'trad', group: 'Rushing',      cell: t => ratio(t.rush_yards, t.carries) },
  { key: 'rtd',  label: 'TD',      kind: 'trad', group: 'Rushing',      cell: t => t.rush_tds },
  { key: 'ryg',  label: 'Y/G',     kind: 'trad', group: 'Rushing',      cell: (t, g) => ratio(t.rush_yards, g) },
  // Receiving
  { key: 'tgt',  label: 'TGT',     kind: 'trad', group: 'Receiving',    cell: t => t.targets > 0 ? t.targets : null },
  { key: 'rec',  label: 'REC',     kind: 'trad', group: 'Receiving',    cell: t => hasReceivingActivity(t) ? t.receptions : null },
  { key: 'rcy',  label: 'YDS',     kind: 'trad', group: 'Receiving',    cell: t => hasReceivingActivity(t) ? t.rec_yards : null },
  { key: 'rctd', label: 'TD',      kind: 'trad', group: 'Receiving',    cell: t => hasReceivingActivity(t) ? t.rec_tds : null },
  { key: 'scr',  label: 'SCR YDS', kind: 'trad', group: 'Receiving',    cell: t => t.rush_yards + t.rec_yards > 0 ? t.rush_yards + t.rec_yards : null },
  // Passing (trick plays / pass-catchers who throw)
  { key: 'patt', label: 'ATT',     kind: 'trad', group: 'Passing',      cell: t => t.attempts > 0 ? t.attempts : null },
  { key: 'pyds', label: 'YDS',     kind: 'trad', group: 'Passing',      cell: t => t.attempts > 0 ? t.pass_yards : null },
  { key: 'ptd',  label: 'TD',      kind: 'trad', group: 'Passing',      cell: t => t.attempts > 0 ? t.pass_tds : null },
  // Advanced / NGS / Situational / WPA
  { key: 'epac',   label: 'EPA/Car', kind: 'adv', signed: true,         cell: t => t.carries > 0 ? sfmt(t.rush_epa / t.carries, 3) : null },
  { key: 'rbstuf', label: 'STF%',    kind: 'adv',                       cell: (_, __, _n, _sn, _sit, _w, a) => a?.stuff_rate != null ? `${a.stuff_rate.toFixed(1)}%` : null },
  { key: 'rbfl',   label: 'FUM',     kind: 'adv',                       cell: (_, __, _n, _sn, _sit, _w, a) => a?.fumbles_lost != null ? a.fumbles_lost : null },
  { key: 'rwpa',   label: 'WPA',     kind: 'adv', wpaOnly: true, signed: true, cell: (_, __, _n, _sn, _sit, w) => w ? sfmt((w.rush_wpa ?? 0) + (w.rec_wpa ?? 0), 3) : null },
  { key: 'ryoe',   label: 'RYOE',    kind: 'ngs', signed: true,         cell: (_, __, n) => sfmt(n?.rush_yoe) },
  { key: 'ryoa',   label: 'RYOE/A',  kind: 'ngs', signed: true,         cell: (_, __, n) => sfmt(n?.rush_yoe_per_att, 2) },
  { key: 'eff',    label: 'EFF%',    kind: 'ngs',                       cell: (_, __, n) => n?.rush_efficiency != null ? `${n.rush_efficiency.toFixed(1)}%` : null },
  { key: 'rzd',    label: 'RZ TD',   kind: 'sit',                       cell: (_, __, _n, _sn, sit) => sit?.rz_rush_tds ?? null },
  { key: 'rzp',    label: 'RZ%',     kind: 'sit',                       cell: (_, __, _n, _sn, sit) => sit?.rz_carries ? pct(sit.rz_rush_tds ?? 0, sit.rz_carries) + '%' : null },
  { key: 'tdp',    label: '3D%',     kind: 'sit',                       cell: (_, __, _n, _sn, sit) => sit?.third_carries ? pct(sit.third_rush_fd ?? 0, sit.third_carries) + '%' : null },
  { key: 'lng',    label: 'LNG',     kind: 'sit',                       cell: (_, __, _n, _sn, sit) => sit?.lng_rush ?? null },
]

export const WR_COLS: Col[] = [
  { key: 'g',    label: 'G',         kind: 'trad',                      cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',       kind: 'snap',                      cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',      kind: 'snap',                      cell: (_, __, _n, sn) => sn ? `${(sn.avg_offense_pct ?? 0).toFixed(0)}%` : null },
  // Receiving
  { key: 'tgt',  label: 'TGT',       kind: 'trad', group: 'Receiving',  cell: t => t.targets },
  { key: 'rec',  label: 'REC',       kind: 'trad', group: 'Receiving',  cell: t => t.receptions },
  { key: 'yds',  label: 'YDS',       kind: 'trad', group: 'Receiving', highlight: true, cell: t => t.rec_yards },
  { key: 'ypr',  label: 'Y/R',       kind: 'trad', group: 'Receiving',  cell: t => ratio(t.rec_yards, t.receptions) },
  { key: 'td',   label: 'TD',        kind: 'trad', group: 'Receiving',  cell: t => t.rec_tds },
  { key: 'cpct', label: 'CTH%',      kind: 'trad', group: 'Receiving',  cell: t => pct(t.receptions, t.targets) },
  { key: 'ytgt', label: 'Y/TGT',     kind: 'trad', group: 'Receiving',  cell: t => ratio(t.rec_yards, t.targets) },
  { key: 'yg',   label: 'Y/G',       kind: 'trad', group: 'Receiving',  cell: (t, g) => ratio(t.rec_yards, g) },
  // Rushing
  { key: 'car',  label: 'CAR',       kind: 'trad', group: 'Rushing',    cell: t => t.carries > 0 ? t.carries : null },
  { key: 'ryd',  label: 'YDS',       kind: 'trad', group: 'Rushing',    cell: t => t.carries > 0 ? t.rush_yards : null },
  // Passing
  { key: 'patt', label: 'ATT',       kind: 'trad', group: 'Passing',    cell: t => t.attempts > 0 ? t.attempts : null },
  { key: 'pyds', label: 'YDS',       kind: 'trad', group: 'Passing',    cell: t => t.attempts > 0 ? t.pass_yards : null },
  { key: 'ptd',  label: 'TD',        kind: 'trad', group: 'Passing',    cell: t => t.attempts > 0 ? t.pass_tds : null },
  // Advanced / NGS / Situational / WPA
  { key: 'epat',   label: 'EPA/Tgt', kind: 'adv',  signed: true,        cell: t => t.targets > 0 ? sfmt(t.rec_epa / t.targets, 3) : null },
  { key: 'ayt',    label: 'AY/TGT',  kind: 'adv',                       cell: t => t.targets > 0 ? ratio(t.air_yards, t.targets) : null },
  { key: 'yacr',   label: 'YAC/R',   kind: 'adv',                       cell: t => t.receptions > 0 ? ratio(t.yac, t.receptions) : null },
  { key: 'racr',   label: 'RACR',    kind: 'adv',                       cell: t => t.air_yards > 0 ? (t.rec_yards / t.air_yards).toFixed(2) : null },
  { key: 'tgtsh',  label: 'TGT%',    kind: 'adv',                       cell: (_, __, _n, _sn, _sit, _w, a) => a?.target_share != null ? `${a.target_share.toFixed(1)}%` : null },
  { key: 'aysh',   label: 'AY%',     kind: 'adv',                       cell: (_, __, _n, _sn, _sit, _w, a) => a?.air_yards_share != null ? `${a.air_yards_share.toFixed(1)}%` : null },
  { key: 'wrfl',   label: 'FUM',     kind: 'adv',                       cell: (_, __, _n, _sn, _sit, _w, a) => a?.fumbles_lost != null ? a.fumbles_lost : null },
  { key: 'recwpa', label: 'WPA',     kind: 'adv',  wpaOnly: true, signed: true, cell: (_, __, _n, _sn, _sit, w) => w?.rec_wpa != null ? sfmt(w.rec_wpa, 3) : null },
  { key: 'sep',    label: 'SEP',     kind: 'ngs',                       cell: (_, __, n) => dfmt(n?.avg_separation) },
  { key: 'cush',   label: 'CUSH',    kind: 'ngs',                       cell: (_, __, n) => dfmt(n?.avg_cushion) },
  { key: 'tgd',    label: 'TGT DEP', kind: 'ngs',                       cell: (_, __, n) => dfmt(n?.avg_target_depth) },
  { key: 'yacx',   label: 'YAC+',    kind: 'ngs',  signed: true,        cell: (_, __, n) => sfmt(n?.avg_yac_above_exp) },
  { key: 'ngsaysh',label: 'AY SH%',  kind: 'ngs',                       cell: (_, __, n) => n?.air_yards_share != null ? `${n.air_yards_share.toFixed(1)}%` : null },
  { key: 'rzd',    label: 'RZ TD',   kind: 'sit',                       cell: (_, __, _n, _sn, sit) => sit?.rz_rec_tds ?? null },
  { key: 'rzp',    label: 'RZ%',     kind: 'sit',                       cell: (_, __, _n, _sn, sit) => sit?.rz_targets ? pct(sit.rz_rec_tds ?? 0, sit.rz_targets) + '%' : null },
  { key: 'tdp',    label: '3D%',     kind: 'sit',                       cell: (_, __, _n, _sn, sit) => sit?.third_targets ? pct(sit.third_rec_fd ?? 0, sit.third_targets) + '%' : null },
  { key: 'lng',    label: 'LNG',     kind: 'sit',                       cell: (_, __, _n, _sn, sit) => sit?.lng_rec ?? null },
]

export const DEF_COLS: Col[] = [
  { key: 'g',    label: 'G',    kind: 'trad', cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',  kind: 'snap', cell: (_, __, _n, sn) => sn ? ((sn.defense_snaps ?? 0) > 0 ? sn.defense_snaps : sn.st_snaps) : null },
  { key: 'spct', label: 'SNP%', kind: 'snap', cell: (_, __, _n, sn) => sn ? ((sn.defense_snaps ?? 0) > 0 ? `${(sn.avg_defense_pct ?? 0).toFixed(0)}%` : `${(sn.avg_st_pct ?? 0).toFixed(0)}%`) : null },
  { key: 'tot',  label: 'TOT',  kind: 'trad', highlight: true, cell: t => t.solo_tackles + t.assist_tackles },
  { key: 'solo', label: 'SOLO', kind: 'trad', cell: t => t.solo_tackles },
  { key: 'ast',  label: 'AST',  kind: 'trad', cell: t => t.assist_tackles },
  { key: 'tfl',  label: 'TFL',  kind: 'trad', cell: t => t.tackles_for_loss > 0 ? t.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', kind: 'trad', cell: t => t.sacks > 0 ? t.sacks : null },
  { key: 'int',  label: 'INT',  kind: 'trad', cell: t => t.def_interceptions > 0 ? t.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  kind: 'trad', cell: t => t.pass_breakups > 0 ? t.pass_breakups : null },
  { key: 'qbh',  label: 'QBH',  kind: 'trad', cell: t => t.qb_hits > 0 ? t.qb_hits : null },
  { key: 'ff',   label: 'FF',   kind: 'trad', cell: t => t.forced_fumbles > 0 ? t.forced_fumbles : null },
  { key: 'fr',   label: 'FR',   kind: 'trad', cell: t => t.fumble_recoveries > 0 ? t.fumble_recoveries : null },
  { key: 'dtd',  label: 'TD',   kind: 'trad', derived: true, cell: (_, __, _n, _sn, _sit, _w, a) => a?.def_tds ? a.def_tds : null },
]

const fgBucket = (m?: number | null, a?: number | null): string | null =>
  a && a > 0 ? `${m ?? 0}/${a}` : null

export const K_COLS: Col[] = [
  { key: 'g',     label: 'G',     kind: 'trad',                   cell: (_, g) => g },
  { key: 'snp',   label: 'SNP',   kind: 'snap',                   cell: (_, __, _n, sn) => sn?.st_snaps ?? null },
  { key: 'spct',  label: 'SNP%',  kind: 'snap',                   cell: (_, __, _n, sn) => sn ? `${(sn.avg_st_pct ?? 0).toFixed(0)}%` : null },
  // Field goals — totals
  { key: 'fgm',   label: 'FG',    kind: 'trad', group: 'Field Goals', highlight: true, cell: t => t.fg_att > 0 ? `${t.fg_made}/${t.fg_att}` : null },
  { key: 'fgpct', label: 'FG%',   kind: 'trad', group: 'Field Goals', cell: t => t.fg_att > 0 ? pct(t.fg_made, t.fg_att) : null },
  { key: 'lng',   label: 'LNG',   kind: 'trad', group: 'Field Goals', derived: true, cell: (_, __, _n, _sn, _sit, _w, _a, k) => k?.fg_long ?? null },
  // Field goals — by distance bucket (the signature kicker split)
  { key: 'fg39',  label: '<40',   kind: 'trad', group: 'By Distance', derived: true, cell: (_, __, _n, _sn, _sit, _w, _a, k) => fgBucket(k?.fg_0_39_made, k?.fg_0_39_att) },
  { key: 'fg49',  label: '40-49', kind: 'trad', group: 'By Distance', derived: true, cell: (_, __, _n, _sn, _sit, _w, _a, k) => fgBucket(k?.fg_40_49_made, k?.fg_40_49_att) },
  { key: 'fg50',  label: '50+',   kind: 'trad', group: 'By Distance', derived: true, cell: (_, __, _n, _sn, _sit, _w, _a, k) => fgBucket(k?.fg_50_made, k?.fg_50_att) },
  // Extra points & scoring
  { key: 'xpm',   label: 'XP',    kind: 'trad', cell: t => t.xp_att > 0 ? `${t.xp_made}/${t.xp_att}` : null },
  { key: 'pts',   label: 'PTS',   kind: 'trad', cell: t => (t.fg_made * 3 + t.xp_made) > 0 ? t.fg_made * 3 + t.xp_made : null },
]

export const P_COLS: Col[] = [
  { key: 'g',    label: 'G',     kind: 'trad',                   cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',   kind: 'snap',                   cell: (_, __, _n, sn) => sn?.st_snaps ?? null },
  { key: 'spct', label: 'SNP%',  kind: 'snap',                   cell: (_, __, _n, sn) => sn ? `${(sn.avg_st_pct ?? 0).toFixed(0)}%` : null },
  { key: 'pnt',  label: 'PUNTS', kind: 'trad', highlight: true,  cell: t => t.punts > 0 ? t.punts : null },
  { key: 'pavg', label: 'AVG',   kind: 'trad',                   cell: t => t.punts > 0 ? ratio(t.punt_yards, t.punts) : null },
  // Net average and placement (derived) — what actually separates punters
  { key: 'pnet', label: 'NET',   kind: 'trad', group: 'Net & Placement', derived: true, cell: (t, _g, _n, _sn, _sit, _w, _a, k) => t.punts > 0 && k?.punt_net_yards != null ? ratio(k.punt_net_yards, t.punts) : null },
  { key: 'plng', label: 'LNG',   kind: 'trad', group: 'Net & Placement', derived: true, cell: (_, __, _n, _sn, _sit, _w, _a, k) => k?.punt_long ?? null },
  { key: 'pin20',label: 'IN20',  kind: 'trad', group: 'Net & Placement', derived: true, cell: (_, __, _n, _sn, _sit, _w, _a, k) => k?.punt_inside_20 ?? null },
  { key: 'ptb',  label: 'TB',    kind: 'trad', group: 'Net & Placement', derived: true, cell: (_, __, _n, _sn, _sit, _w, _a, k) => k?.punt_touchbacks ?? null },
]

export const OL_COLS: Col[] = [
  { key: 'g',    label: 'G',     kind: 'trad', cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',   kind: 'snap', cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',  kind: 'snap', cell: (_, __, _n, sn) => sn ? `${(sn.avg_offense_pct ?? 0).toFixed(0)}%` : null },
  // Penalties — the only individual accountability stat the vendor data carries
  // for linemen. Grouped so the table reads as a real position view, not a stub.
  { key: 'pen',  label: 'PEN',   kind: 'trad', group: 'Penalties', derived: true, cell: (_, __, _n, sn, _sit, _w, a) => a?.penalties ?? (sn ? 0 : null) },
  { key: 'peny', label: 'YDS',   kind: 'trad', group: 'Penalties', derived: true, cell: (_, __, _n, sn, _sit, _w, a) => a?.penalty_yards ?? (sn ? 0 : null) },
  { key: 'fs',   label: 'FS',    kind: 'trad', group: 'Penalties', derived: true, cell: (_, __, _n, sn, _sit, _w, a) => a?.false_starts ?? (sn ? 0 : null) },
  { key: 'hold', label: 'HOLD',  kind: 'trad', group: 'Penalties', derived: true, cell: (_, __, _n, sn, _sit, _w, a) => a?.holding ?? (sn ? 0 : null) },
]
