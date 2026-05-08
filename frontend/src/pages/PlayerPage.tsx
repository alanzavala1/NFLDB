import { useEffect, useRef, useState } from 'react'
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { PlayerProfile, PlayerGame, NgsStats, SnapTotals, SituationalStats, PlayerWpa } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl } from '../utils/teams'

// — helpers —
function passerRating(cmp: number, att: number, yds: number, td: number, int_: number): string | null {
  if (att === 0) return null
  const clamp = (x: number) => Math.min(2.375, Math.max(0, x))
  const a = clamp((cmp / att - 0.3) / 0.2)
  const b = clamp((yds / att - 3) / 4)
  const c = clamp((td / att) / 0.05)
  const d = clamp(2.375 - (int_ / att) / 0.04)
  return (((a + b + c + d) / 6) * 100).toFixed(1)
}
function pct(a: number, b: number, dec = 1): string | null { return b > 0 ? (a / b * 100).toFixed(dec) : null }
function ratio(y: number, a: number, dec = 1): string | null { return a > 0 ? (y / a).toFixed(dec) : null }
function sfmt(x: number | undefined, dec = 1): string | null { if (x == null) return null; return `${x >= 0 ? '+' : ''}${x.toFixed(dec)}` }
function dfmt(x: number | undefined, dec = 1): string | null { if (x == null) return null; return x.toFixed(dec) }

// — aggregation —
function sumGames(games: PlayerGame[]) {
  const s = {
    attempts: 0, completions: 0, pass_yards: 0, pass_tds: 0,
    interceptions_thrown: 0, sacks_taken: 0, pass_epa: 0,
    carries: 0, rush_yards: 0, rush_tds: 0, rush_epa: 0,
    targets: 0, receptions: 0, rec_yards: 0, rec_tds: 0, yac: 0, air_yards: 0, rec_epa: 0,
    solo_tackles: 0, assist_tackles: 0, tackles_for_loss: 0,
    sacks: 0, qb_hits: 0, def_interceptions: 0, pass_breakups: 0,
  }
  for (const g of games) {
    for (const k of Object.keys(s) as (keyof typeof s)[]) {
      s[k] += g[k] ?? 0
    }
  }
  return s
}
type Totals = ReturnType<typeof sumGames>

type ColKind = 'trad' | 'adv' | 'ngs' | 'snap' | 'sit' | 'wpa'
type Col = {
  key: string; label: string; kind: ColKind; signed?: boolean; highlight?: boolean
  cell: (t: Totals, games: number, n?: NgsStats, sn?: SnapTotals, sit?: SituationalStats, w?: PlayerWpa) => string | number | null
}

// — column definitions —
const QB_COLS: Col[] = [
  { key: 'g',      label: 'G',      kind: 'trad', cell: (_, g) => g },
  { key: 'snp',    label: 'SNP',    kind: 'snap', cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct',   label: 'SNP%',   kind: 'snap', cell: (_, __, _n, sn) => sn ? `${sn.avg_offense_pct.toFixed(0)}%` : null },
  { key: 'cmp',    label: 'CMP',    kind: 'trad', cell: t => t.completions },
  { key: 'att',    label: 'ATT',    kind: 'trad', cell: t => t.attempts },
  { key: 'cpct',   label: 'CMP%',   kind: 'trad', cell: t => pct(t.completions, t.attempts) },
  { key: 'yds',    label: 'YDS',    kind: 'trad', highlight: true, cell: t => t.pass_yards },
  { key: 'td',     label: 'TD',     kind: 'trad', cell: t => t.pass_tds },
  { key: 'int',    label: 'INT',    kind: 'trad', cell: t => t.interceptions_thrown },
  { key: 'ya',     label: 'Y/A',    kind: 'trad', cell: t => ratio(t.pass_yards, t.attempts) },
  { key: 'sck',    label: 'SACK',   kind: 'trad', cell: t => t.sacks_taken },
  { key: 'rate',   label: 'RATE',   kind: 'trad', cell: t => passerRating(t.completions, t.attempts, t.pass_yards, t.pass_tds, t.interceptions_thrown) },
  { key: 'car',    label: 'CAR',    kind: 'trad', cell: t => t.carries > 0 ? t.carries : null },
  { key: 'ryds',   label: 'RYDS',   kind: 'trad', cell: t => t.carries > 0 ? t.rush_yards : null },
  { key: 'rtd',    label: 'RTD',    kind: 'trad', cell: t => t.carries > 0 && t.rush_tds > 0 ? t.rush_tds : null },
  { key: 'rypc',   label: 'Y/C',    kind: 'trad', cell: t => t.carries > 0 ? ratio(t.rush_yards, t.carries) : null },
  { key: 'aya',    label: 'AY/A',   kind: 'adv',  cell: t => t.attempts > 0 ? ((t.pass_yards + 20 * t.pass_tds - 45 * t.interceptions_thrown) / t.attempts).toFixed(1) : null },
  { key: 'epaa',   label: 'EPA/Att',kind: 'adv', signed: true, cell: t => t.attempts > 0 ? sfmt(t.pass_epa / t.attempts, 3) : null },
  { key: 'cpoe',   label: 'CPOE',   kind: 'ngs', signed: true, cell: (_, __, n) => sfmt(n?.cpoe) },
  { key: 'ttt',    label: 'TTT',    kind: 'ngs', cell: (_, __, n) => n?.avg_time_to_throw != null ? `${n.avg_time_to_throw.toFixed(2)}s` : null },
  { key: 'adot',   label: 'aDOT',   kind: 'ngs', cell: (_, __, n) => dfmt(n?.adot) },
  { key: 'agg',    label: 'AGG%',   kind: 'ngs', cell: (_, __, n) => n?.aggressiveness != null ? `${n.aggressiveness.toFixed(1)}%` : null },
  { key: 'xcmp',   label: 'xCMP%',  kind: 'ngs', cell: (_, __, n) => n?.expected_cmp_pct != null ? `${n.expected_cmp_pct.toFixed(1)}%` : null },
  { key: 'rzd',    label: 'RZ TD',  kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.rz_pass_tds ?? null },
  { key: 'rzp',    label: 'RZ%',    kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.rz_pass_att ? pct(sit.rz_pass_tds ?? 0, sit.rz_pass_att) + '%' : null },
  { key: 'tdp',    label: '3D%',    kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.third_pass_att ? pct(sit.third_pass_fd ?? 0, sit.third_pass_att) + '%' : null },
  { key: 'lng',    label: 'LNG',    kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.lng_pass ?? null },
  { key: 'pwpa',   label: 'WPA',    kind: 'wpa', signed: true, cell: (_, __, _n, _sn, _sit, w) => w?.pass_wpa != null ? sfmt(w.pass_wpa, 3) : null },
]

const RB_COLS: Col[] = [
  { key: 'g',    label: 'G',       kind: 'trad', cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',     kind: 'snap', cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',    kind: 'snap', cell: (_, __, _n, sn) => sn ? `${sn.avg_offense_pct.toFixed(0)}%` : null },
  { key: 'car',  label: 'CAR',     kind: 'trad', cell: t => t.carries },
  { key: 'ryds', label: 'YDS',     kind: 'trad', highlight: true, cell: t => t.rush_yards },
  { key: 'ypc',  label: 'Y/C',     kind: 'trad', cell: t => ratio(t.rush_yards, t.carries) },
  { key: 'rtd',  label: 'TD',      kind: 'trad', cell: t => t.rush_tds },
  { key: 'ryg',  label: 'Y/G',     kind: 'trad', cell: (t, g) => ratio(t.rush_yards, g) },
  { key: 'tgt',  label: 'TGT',     kind: 'trad', cell: t => t.targets > 0 ? t.targets : null },
  { key: 'rec',  label: 'REC',     kind: 'trad', cell: t => t.targets > 0 ? t.receptions : null },
  { key: 'rcy',  label: 'REC YDS', kind: 'trad', cell: t => t.targets > 0 ? t.rec_yards : null },
  { key: 'scr',  label: 'SCR YDS', kind: 'trad', cell: t => t.rush_yards + t.rec_yards > 0 ? t.rush_yards + t.rec_yards : null },
  { key: 'patt', label: 'P.ATT',  kind: 'trad', cell: t => t.attempts > 0 ? t.attempts : null },
  { key: 'pyds', label: 'P.YDS',  kind: 'trad', cell: t => t.attempts > 0 ? t.pass_yards : null },
  { key: 'ptd',  label: 'P.TD',   kind: 'trad', cell: t => t.attempts > 0 ? t.pass_tds : null },
  { key: 'epac', label: 'EPA/Car', kind: 'adv', signed: true, cell: t => t.carries > 0 ? sfmt(t.rush_epa / t.carries, 3) : null },
  { key: 'ryoe', label: 'RYOE',    kind: 'ngs', signed: true, cell: (_, __, n) => sfmt(n?.rush_yoe) },
  { key: 'ryoa', label: 'RYOE/A',  kind: 'ngs', signed: true, cell: (_, __, n) => sfmt(n?.rush_yoe_per_att, 2) },
  { key: 'eff',  label: 'EFF%',    kind: 'ngs', cell: (_, __, n) => n?.rush_efficiency != null ? `${n.rush_efficiency.toFixed(1)}%` : null },
  { key: 'rzd',  label: 'RZ TD',   kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.rz_rush_tds ?? null },
  { key: 'rzp',  label: 'RZ%',     kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.rz_carries ? pct(sit.rz_rush_tds ?? 0, sit.rz_carries) + '%' : null },
  { key: 'tdp',  label: '3D%',     kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.third_carries ? pct(sit.third_rush_fd ?? 0, sit.third_carries) + '%' : null },
  { key: 'lng',  label: 'LNG',     kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.lng_rush ?? null },
  { key: 'rwpa', label: 'WPA',     kind: 'wpa', signed: true, cell: (_, __, _n, _sn, _sit, w) => w ? sfmt((w.rush_wpa ?? 0) + (w.rec_wpa ?? 0), 3) : null },
]

const WR_COLS: Col[] = [
  { key: 'g',    label: 'G',         kind: 'trad', cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',       kind: 'snap', cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',      kind: 'snap', cell: (_, __, _n, sn) => sn ? `${sn.avg_offense_pct.toFixed(0)}%` : null },
  { key: 'tgt',  label: 'TGT',       kind: 'trad', cell: t => t.targets },
  { key: 'rec',  label: 'REC',       kind: 'trad', cell: t => t.receptions },
  { key: 'yds',  label: 'YDS',       kind: 'trad', highlight: true, cell: t => t.rec_yards },
  { key: 'ypr',  label: 'Y/R',       kind: 'trad', cell: t => ratio(t.rec_yards, t.receptions) },
  { key: 'td',   label: 'TD',        kind: 'trad', cell: t => t.rec_tds },
  { key: 'cpct', label: 'CTH%',      kind: 'trad', cell: t => pct(t.receptions, t.targets) },
  { key: 'ytgt', label: 'Y/TGT',     kind: 'trad', cell: t => ratio(t.rec_yards, t.targets) },
  { key: 'yg',   label: 'Y/G',       kind: 'trad', cell: (t, g) => ratio(t.rec_yards, g) },
  { key: 'car',  label: 'CAR',       kind: 'trad', cell: t => t.carries > 0 ? t.carries : null },
  { key: 'ryd',  label: 'RUSH YDS',  kind: 'trad', cell: t => t.carries > 0 ? t.rush_yards : null },
  { key: 'patt', label: 'P.ATT',     kind: 'trad', cell: t => t.attempts > 0 ? t.attempts : null },
  { key: 'pyds', label: 'P.YDS',     kind: 'trad', cell: t => t.attempts > 0 ? t.pass_yards : null },
  { key: 'ptd',  label: 'P.TD',      kind: 'trad', cell: t => t.attempts > 0 ? t.pass_tds : null },
  { key: 'epat', label: 'EPA/Tgt',   kind: 'adv', signed: true, cell: t => t.targets > 0 ? sfmt(t.rec_epa / t.targets, 3) : null },
  { key: 'ayt',  label: 'AY/TGT',    kind: 'adv', cell: t => t.targets > 0 ? ratio(t.air_yards, t.targets) : null },
  { key: 'yacr', label: 'YAC/R',     kind: 'adv', cell: t => t.receptions > 0 ? ratio(t.yac, t.receptions) : null },
  { key: 'sep',  label: 'SEP',       kind: 'ngs', cell: (_, __, n) => dfmt(n?.avg_separation) },
  { key: 'cush', label: 'CUSH',      kind: 'ngs', cell: (_, __, n) => dfmt(n?.avg_cushion) },
  { key: 'tgd',  label: 'TGT DEPTH', kind: 'ngs', cell: (_, __, n) => dfmt(n?.avg_target_depth) },
  { key: 'yacx', label: 'YAC+',      kind: 'ngs', signed: true, cell: (_, __, n) => sfmt(n?.avg_yac_above_exp) },
  { key: 'aysh', label: 'AY SH%',    kind: 'ngs', cell: (_, __, n) => n?.air_yards_share != null ? `${n.air_yards_share.toFixed(1)}%` : null },
  { key: 'rzd',  label: 'RZ TD',     kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.rz_rec_tds ?? null },
  { key: 'rzp',  label: 'RZ%',       kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.rz_targets ? pct(sit.rz_rec_tds ?? 0, sit.rz_targets) + '%' : null },
  { key: 'tdp',  label: '3D%',       kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.third_targets ? pct(sit.third_rec_fd ?? 0, sit.third_targets) + '%' : null },
  { key: 'lng',  label: 'LNG',       kind: 'sit',  cell: (_, __, _n, _sn, sit) => sit?.lng_rec ?? null },
  { key: 'recwpa', label: 'WPA',     kind: 'wpa', signed: true, cell: (_, __, _n, _sn, _sit, w) => w?.rec_wpa != null ? sfmt(w.rec_wpa, 3) : null },
]

const DEF_COLS: Col[] = [
  { key: 'g',    label: 'G',    kind: 'trad', cell: (_, g) => g },
  { key: 'snp',  label: 'SNP',  kind: 'snap', cell: (_, __, _n, sn) => sn ? (sn.defense_snaps > 0 ? sn.defense_snaps : sn.st_snaps) : null },
  { key: 'spct', label: 'SNP%', kind: 'snap', cell: (_, __, _n, sn) => sn ? (sn.defense_snaps > 0 ? `${sn.avg_defense_pct.toFixed(0)}%` : `${sn.avg_st_pct.toFixed(0)}%`) : null },
  { key: 'tot',  label: 'TOT',  kind: 'trad', highlight: true, cell: t => t.solo_tackles + t.assist_tackles },
  { key: 'solo', label: 'SOLO', kind: 'trad', cell: t => t.solo_tackles },
  { key: 'ast',  label: 'AST',  kind: 'trad', cell: t => t.assist_tackles },
  { key: 'tfl',  label: 'TFL',  kind: 'trad', cell: t => t.tackles_for_loss > 0 ? t.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', kind: 'trad', cell: t => t.sacks > 0 ? t.sacks : null },
  { key: 'int',  label: 'INT',  kind: 'trad', cell: t => t.def_interceptions > 0 ? t.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  kind: 'trad', cell: t => t.pass_breakups > 0 ? t.pass_breakups : null },
  { key: 'qbh',  label: 'QBH',  kind: 'trad', cell: t => t.qb_hits > 0 ? t.qb_hits : null },
]

function detectPos(t: Totals, position?: string | null): string {
  if (position === 'QB' || t.attempts > 10) return 'QB'
  if (position === 'RB' || (t.carries > 20 && t.targets < t.carries * 0.7)) return 'RB'
  if (position === 'WR' || position === 'TE' || t.targets > 20) return 'WR'
  return 'DEF'
}

// — highlights bar —
function HighlightsBar({ pos, totals, games, ngs }: {
  pos: string; totals: Totals; games: number; ngs: Record<number, NgsStats>
}) {
  const ngsEntries = Object.entries(ngs).sort(([a], [b]) => Number(b) - Number(a))
  const cpoeVals = ngsEntries.map(([, n]) => n.cpoe).filter((v): v is number => v != null)
  const avgCpoe = cpoeVals.length > 0 ? cpoeVals.reduce((a, b) => a + b, 0) / cpoeVals.length : null

  type Stat = { label: string; value: string | null; note?: string; green?: boolean; red?: boolean }
  let stats: Stat[] = []

  if (pos === 'QB') {
    const rate = passerRating(totals.completions, totals.attempts, totals.pass_yards, totals.pass_tds, totals.interceptions_thrown)
    const aya = totals.attempts > 0 ? (totals.pass_yards + 20 * totals.pass_tds - 45 * totals.interceptions_thrown) / totals.attempts : null
    const epaa = totals.attempts > 0 ? totals.pass_epa / totals.attempts : null
    stats = [
      { label: 'Passer Rating', value: rate },
      { label: 'AY/A', value: aya != null ? aya.toFixed(1) : null, note: 'Adj. Net Yds/Att' },
      { label: 'EPA / Att', value: epaa != null ? `${epaa >= 0 ? '+' : ''}${epaa.toFixed(3)}` : null, note: 'Exp. Points Added', green: epaa != null && epaa >= 0, red: epaa != null && epaa < 0 },
      { label: 'CPOE', value: avgCpoe != null ? `${avgCpoe >= 0 ? '+' : ''}${avgCpoe.toFixed(1)}%` : null, note: 'Cmp% Over Expected', green: avgCpoe != null && avgCpoe >= 0, red: avgCpoe != null && avgCpoe < 0 },
    ]
  } else if (pos === 'RB') {
    const epac = totals.carries > 0 ? totals.rush_epa / totals.carries : null
    const scryg = games > 0 ? (totals.rush_yards + totals.rec_yards) / games : null
    stats = [
      { label: 'Rush Yards', value: totals.rush_yards.toLocaleString() },
      { label: 'Y / Carry', value: totals.carries > 0 ? (totals.rush_yards / totals.carries).toFixed(1) : null },
      { label: 'EPA / Carry', value: epac != null ? `${epac >= 0 ? '+' : ''}${epac.toFixed(3)}` : null, note: 'Exp. Points Added', green: epac != null && epac >= 0, red: epac != null && epac < 0 },
      { label: 'SCR YDS / G', value: scryg != null ? scryg.toFixed(1) : null, note: 'Scrimmage per game' },
    ]
  } else if (pos === 'WR') {
    const epat = totals.targets > 0 ? totals.rec_epa / totals.targets : null
    stats = [
      { label: 'Rec Yards', value: totals.rec_yards.toLocaleString() },
      { label: 'Catch %', value: totals.targets > 0 ? pct(totals.receptions, totals.targets) + '%' : null },
      { label: 'EPA / Target', value: epat != null ? `${epat >= 0 ? '+' : ''}${epat.toFixed(3)}` : null, note: 'Exp. Points Added', green: epat != null && epat >= 0, red: epat != null && epat < 0 },
      { label: 'Y / Target', value: totals.targets > 0 ? (totals.rec_yards / totals.targets).toFixed(1) : null },
    ]
  } else {
    const tot = totals.solo_tackles + totals.assist_tackles
    stats = [
      { label: 'Tackles', value: tot > 0 ? tot.toLocaleString() : null },
      { label: 'Sacks', value: totals.sacks > 0 ? totals.sacks.toString() : null },
      { label: 'INT', value: totals.def_interceptions > 0 ? totals.def_interceptions.toString() : null },
      { label: 'PBU', value: totals.pass_breakups > 0 ? totals.pass_breakups.toString() : null },
    ]
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
      {stats.map(s => (
        <div key={s.label} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className={`text-2xl font-black tabular-nums leading-none mb-1.5
            ${s.value == null ? 'text-gray-700' : s.green ? 'text-emerald-400' : s.red ? 'text-red-400' : 'text-white'}`}>
            {s.value ?? '—'}
          </div>
          <div className="text-xs font-bold text-gray-500 uppercase tracking-wider">{s.label}</div>
          {s.note && <div className="text-xs text-gray-700 mt-0.5">{s.note}</div>}
        </div>
      ))}
    </div>
  )
}

// — situational stats cards —
function aggregateSituational(situational: Record<number, SituationalStats>): SituationalStats {
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
  return agg as SituationalStats
}

// — career stats table —
function CareerTable({ seasons, bySeason, ngs, snapTotals, situational, wpa, position, onlyKinds, showGroupHeaders = true }: {
  seasons: number[]
  bySeason: Record<number, PlayerGame[]>
  ngs: Record<number, NgsStats>
  snapTotals: Record<number, SnapTotals>
  situational: Record<number, SituationalStats>
  wpa?: Record<number, PlayerWpa>
  position?: string | null
  onlyKinds?: ColKind[]
  showGroupHeaders?: boolean
}) {
  const allTotals = sumGames(seasons.flatMap(s => bySeason[s]))
  const pos = detectPos(allTotals, position)
  const allCols = pos === 'QB' ? QB_COLS : pos === 'RB' ? RB_COLS : pos === 'WR' ? WR_COLS : DEF_COLS

  const hasNgs  = Object.keys(ngs).length > 0
  const hasSnaps = Object.keys(snapTotals).length > 0
  const hasSit  = Object.keys(situational).length > 0 && pos !== 'DEF'
  const hasWpa  = wpa != null && Object.keys(wpa).length > 0
  const cols = allCols.filter(c =>
    !(onlyKinds && !onlyKinds.includes(c.kind)) &&
    !(c.kind === 'ngs'  && !hasNgs) &&
    !(c.kind === 'snap' && !hasSnaps) &&
    !(c.kind === 'sit'  && !hasSit) &&
    !(c.kind === 'wpa'  && !hasWpa)
  )

  const tradCount = cols.filter(c => c.kind === 'trad').length
  const advCount  = cols.filter(c => c.kind === 'adv').length
  const ngsCount  = cols.filter(c => c.kind === 'ngs').length
  const snapCount = cols.filter(c => c.kind === 'snap').length
  const sitCount  = cols.filter(c => c.kind === 'sit').length
  const wpaCount  = cols.filter(c => c.kind === 'wpa').length

  const careerWpaTotals: PlayerWpa | undefined = hasWpa ? {
    pass_wpa: seasons.reduce((acc, s) => acc + (wpa![s]?.pass_wpa ?? 0), 0),
    rush_wpa: seasons.reduce((acc, s) => acc + (wpa![s]?.rush_wpa ?? 0), 0),
    rec_wpa:  seasons.reduce((acc, s) => acc + (wpa![s]?.rec_wpa  ?? 0), 0),
  } : undefined

  const careerSit = hasSit ? aggregateSituational(situational) : undefined

  const careerT = sumGames(seasons.flatMap(s => bySeason[s]))
  const careerGames = seasons.reduce((acc, s) => acc + bySeason[s].length, 0)

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-left'

  if (cols.length === 0) return null

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {showGroupHeaders && (
              <tr className="border-b border-gray-800/50">
                <th colSpan={2} />
                {tradCount > 0 && <th colSpan={tradCount} className="py-1 text-center text-[10px] font-semibold text-gray-600 uppercase tracking-widest border-l border-gray-800/40">Stats</th>}
                {advCount  > 0 && <th colSpan={advCount}  className="py-1 text-center text-[10px] font-semibold text-amber-500/60 uppercase tracking-widest bg-amber-950/20 border-l border-gray-800/40">Advanced</th>}
                {ngsCount  > 0 && <th colSpan={ngsCount}  className="py-1 text-center text-[10px] font-semibold text-indigo-400 uppercase tracking-widest bg-indigo-950/25 border-l border-gray-800/40">Next Gen</th>}
                {snapCount > 0 && <th colSpan={snapCount} className="py-1 text-center text-[10px] font-semibold text-gray-700 uppercase tracking-widest border-l border-gray-800/40">Snaps</th>}
                {sitCount  > 0 && <th colSpan={sitCount}  className="py-1 text-center text-[10px] font-semibold text-teal-500/60 uppercase tracking-widest bg-teal-950/20 border-l border-gray-800/40">Situational</th>}
                {wpaCount  > 0 && <th colSpan={wpaCount}  className="py-1 text-center text-[10px] font-semibold text-violet-400/60 uppercase tracking-widest bg-violet-950/20 border-l border-gray-800/40">WPA</th>}
              </tr>
            )}
            <tr className="border-b border-gray-800">
              <th className={`${thBase} text-gray-500 pl-4`}>Season</th>
              <th className={`${thBase} text-gray-500`}>Team</th>
              {cols.map((c, i) => {
                const sep = i > 0 && cols[i - 1].kind !== c.kind
                return (
                  <th key={c.key} className={`${thBase} ${sep ? 'border-l border-gray-800/40' : ''}
                    ${c.kind === 'adv'  ? 'text-amber-300/50 bg-amber-950/10' :
                      c.kind === 'ngs'  ? 'text-indigo-300/50 bg-indigo-950/10' :
                      c.kind === 'snap' ? 'text-gray-700' :
                      c.kind === 'sit'  ? 'text-teal-400/50 bg-teal-950/10' :
                      c.kind === 'wpa'  ? 'text-violet-400/50 bg-violet-950/10' : 'text-gray-500'}`}>
                    {c.label}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {seasons.map(s => {
              const games = bySeason[s]
              const t = sumGames(games)
              const n = ngs[s] as NgsStats | undefined
              const sn = snapTotals[s] as SnapTotals | undefined
              const sit = situational[s] as SituationalStats | undefined
              const w = wpa?.[s] as PlayerWpa | undefined
              const teams = [...new Set(games.map(g => g.team))]
              return (
                <tr key={s} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                  <td className="py-2.5 pl-4 pr-3 font-bold text-white whitespace-nowrap">{s}</td>
                  <td className="py-2.5 px-3">
                    <div className="flex items-center gap-1.5">
                      <div className="flex -space-x-1">
                        {teams.map(tm => (
                          <img key={tm} src={teamLogoUrl(tm)} alt={tm} className="w-5 h-5 object-contain ring-1 ring-gray-900 rounded-full bg-gray-900" />
                        ))}
                      </div>
                      <span className="text-gray-400 text-xs">{teams.join('/')}</span>
                    </div>
                  </td>
                  {cols.map((c, i) => {
                    const sep = i > 0 && cols[i - 1].kind !== c.kind
                    const raw = c.cell(t, games.length, n, sn, sit, w)
                    const isNull = raw === null || raw === undefined
                    const strVal = isNull ? null : String(raw)
                    const isPos = c.signed && !isNull && strVal!.startsWith('+')
                    const isNeg = c.signed && !isNull && strVal!.startsWith('-')
                    return (
                      <td key={c.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums
                        ${sep ? 'border-l border-gray-800/30' : ''}
                        ${c.kind === 'adv'  ? 'bg-amber-950/10'  : ''}
                        ${c.kind === 'ngs'  ? 'bg-indigo-950/10' : ''}
                        ${c.kind === 'sit'  ? 'bg-teal-950/10'   : ''}
                        ${c.kind === 'wpa'  ? 'bg-violet-950/10' : ''}
                        ${isNull   ? 'text-gray-700' :
                          isPos    ? 'text-emerald-400 font-semibold' :
                          isNeg    ? 'text-red-400 font-semibold' :
                          c.highlight ? 'text-white font-bold' :
                          c.kind === 'ngs'  ? 'text-gray-200' :
                          c.kind === 'adv'  ? 'text-amber-200/80' :
                          c.kind === 'sit'  ? 'text-teal-200/80' :
                          c.kind === 'wpa'  ? 'text-violet-200/80' :
                          'text-gray-300'}`}>
                        {isNull ? '—' : strVal}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
            {seasons.length > 1 && (
              <tr className="border-t-2 border-gray-700 bg-gray-800/40">
                <td className="py-2.5 pl-4 pr-3 text-xs font-bold text-gray-400 uppercase tracking-wider whitespace-nowrap">Career</td>
                <td className="py-2.5 px-3 text-gray-600 text-xs">{careerGames}G</td>
                {cols.map((c, i) => {
                  const sep = i > 0 && cols[i - 1].kind !== c.kind
                  const raw = (c.kind === 'trad' || c.kind === 'adv' || c.kind === 'sit' || c.kind === 'wpa')
                    ? c.cell(careerT, careerGames, undefined, undefined, careerSit, careerWpaTotals)
                    : null
                  const isNull = raw === null || raw === undefined
                  const strVal = isNull ? null : String(raw)
                  const isPos = c.signed && !isNull && strVal!.startsWith('+')
                  const isNeg = c.signed && !isNull && strVal!.startsWith('-')
                  return (
                    <td key={c.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums font-semibold
                      ${sep ? 'border-l border-gray-800/30' : ''}
                      ${c.kind === 'adv' ? 'bg-amber-950/10' : ''}
                      ${c.kind === 'ngs' ? 'bg-indigo-950/10 text-gray-700' : ''}
                      ${c.kind === 'sit' ? 'bg-teal-950/10' : ''}
                      ${c.kind === 'wpa' ? 'bg-violet-950/10' : ''}
                      ${isNull ? 'text-gray-700' : isPos ? 'text-emerald-400' : isNeg ? 'text-red-400' : c.highlight ? 'text-white' : c.kind === 'adv' ? 'text-amber-200/80' : c.kind === 'sit' ? 'text-teal-200/80' : c.kind === 'wpa' ? 'text-violet-200/80' : 'text-gray-300'}`}>
                      {isNull ? '—' : String(raw)}
                    </td>
                  )
                })}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// — team splits —
function TeamSplits({ seasons, bySeason, position }: {
  seasons: number[]
  bySeason: Record<number, PlayerGame[]>
  position?: string | null
}) {
  const byTeam: Record<string, PlayerGame[]> = {}
  for (const s of seasons) {
    for (const g of bySeason[s]) {
      ;(byTeam[g.team] ??= []).push(g)
    }
  }
  const teamList = Object.entries(byTeam)
  if (teamList.length <= 1) return null

  const allTotals = sumGames(seasons.flatMap(s => bySeason[s]))
  const pos = detectPos(allTotals, position)
  const colSet = pos === 'QB' ? QB_COLS : pos === 'RB' ? RB_COLS : pos === 'WR' ? WR_COLS : DEF_COLS
  const cols = colSet.filter(c => c.kind === 'trad' && c.key !== 'g')

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-4">
      <div className="px-4 py-2.5 border-b border-gray-800">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">Career by Team</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="py-2 pl-4 pr-3 text-xs font-medium text-gray-500 text-left whitespace-nowrap">Team</th>
              <th className="py-2 px-3 text-xs font-medium text-gray-500 text-left whitespace-nowrap">Seasons</th>
              {cols.map(c => (
                <th key={c.key} className="py-2 px-3 text-xs font-medium text-gray-500 text-left whitespace-nowrap">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {teamList.map(([team, games]) => {
              const t = sumGames(games)
              const teamSeasons = [...new Set(games.map(g => g.season))].sort()
              const label = teamSeasons.length === 1
                ? `${teamSeasons[0]} · ${games.length}G`
                : `${teamSeasons[0]}–${teamSeasons[teamSeasons.length - 1]} · ${games.length}G`
              return (
                <tr key={team} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                  <td className="py-2.5 pl-4 pr-3">
                    <Link to={`/teams/${team}`} className="flex items-center gap-2 group w-fit">
                      <img src={teamLogoUrl(team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                      <span className="text-sm font-bold text-gray-300 group-hover:text-white transition-colors">{team}</span>
                    </Link>
                  </td>
                  <td className="py-2.5 px-3 text-xs text-gray-500 whitespace-nowrap">{label}</td>
                  {cols.map(c => {
                    const raw = c.cell(t, games.length)
                    const isNull = raw === null || raw === undefined
                    return (
                      <td key={c.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums text-sm ${isNull ? 'text-gray-700' : c.highlight ? 'text-white font-bold' : 'text-gray-300'}`}>
                        {isNull ? '—' : String(raw)}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// — game log —
function resultBadge(result: PlayerGame['result']) {
  if (!result) return <span className="text-gray-600 text-xs font-bold">—</span>
  const cls = { W: 'text-green-400', L: 'text-red-400', T: 'text-gray-400' }
  return <span className={`text-xs font-bold ${cls[result]}`}>{result}</span>
}

type GameCol = { label: string; cell: (g: PlayerGame) => string | number | null; highlight?: boolean }

function getGameCols(pos: string): GameCol[] {
  if (pos === 'QB') return [
    { label: 'C/ATT', cell: g => g.attempts > 0 ? `${g.completions}/${g.attempts}` : null },
    { label: 'YDS',   cell: g => g.attempts > 0 ? g.pass_yards : null, highlight: true },
    { label: 'TD',    cell: g => g.attempts > 0 ? g.pass_tds : null },
    { label: 'INT',   cell: g => g.attempts > 0 ? g.interceptions_thrown : null },
    { label: 'RATE',  cell: g => g.attempts > 0 ? passerRating(g.completions, g.attempts, g.pass_yards, g.pass_tds, g.interceptions_thrown) : null },
    { label: 'EPA',   cell: g => g.attempts > 0 ? sfmt(g.pass_epa, 1) : null },
  ]
  if (pos === 'RB') return [
    { label: 'CAR',     cell: g => g.carries > 0 ? g.carries : null },
    { label: 'YDS',     cell: g => g.rush_yards, highlight: true },
    { label: 'Y/C',     cell: g => g.carries > 0 ? ratio(g.rush_yards, g.carries) : null },
    { label: 'TD',      cell: g => g.rush_tds > 0 ? g.rush_tds : null },
    { label: 'TGT',     cell: g => g.targets > 0 ? g.targets : null },
    { label: 'REC',     cell: g => g.targets > 0 ? g.receptions : null },
    { label: 'REC YDS', cell: g => g.receptions > 0 ? g.rec_yards : null },
    { label: 'EPA',     cell: g => sfmt(g.rush_epa, 1) },
  ]
  if (pos === 'WR' || pos === 'TE') return [
    { label: 'TGT', cell: g => g.targets },
    { label: 'REC', cell: g => g.receptions },
    { label: 'YDS', cell: g => g.rec_yards, highlight: true },
    { label: 'Y/R', cell: g => g.receptions > 0 ? ratio(g.rec_yards, g.receptions) : null },
    { label: 'TD',  cell: g => g.rec_tds > 0 ? g.rec_tds : null },
    { label: 'EPA', cell: g => sfmt(g.rec_epa, 1) },
  ]
  return [
    { label: 'TOT',  cell: g => g.solo_tackles + g.assist_tackles, highlight: true },
    { label: 'SOLO', cell: g => g.solo_tackles },
    { label: 'AST',  cell: g => g.assist_tackles },
    { label: 'SACK', cell: g => g.sacks > 0 ? g.sacks : null },
    { label: 'INT',  cell: g => g.def_interceptions > 0 ? g.def_interceptions : null },
    { label: 'PBU',  cell: g => g.pass_breakups > 0 ? g.pass_breakups : null },
  ]
}

function GameLog({ season, games, pos, playerId, playerName, fromGame, defaultOpen = false }: {
  season: number; games: PlayerGame[]; pos: string
  playerId: string; playerName: string; fromGame?: any; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const seasonTeams = [...new Set(games.map(g => g.team))]
  const wins = games.filter(g => g.result === 'W').length
  const losses = games.filter(g => g.result === 'L').length
  const ties = games.filter(g => g.result === 'T').length
  const record = ties > 0 ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`
  const gameCols = getGameCols(pos)

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-3 hover:bg-gray-800/50 transition-colors text-left"
      >
        <div className="flex -space-x-1.5">
          {seasonTeams.map(t => (
            <img key={t} src={teamLogoUrl(t)} alt={t} className="w-6 h-6 object-contain ring-1 ring-gray-900 rounded-full bg-gray-900" />
          ))}
        </div>
        <span className="font-semibold text-white">{season}</span>
        <span className="text-gray-500 text-xs">{seasonTeams.join('/')} · {record} · {games.length}G</span>
        <span className="ml-auto text-gray-600 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="overflow-x-auto border-t border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="py-2 px-4 text-xs font-medium text-gray-600 text-left">Wk</th>
                <th className="py-2 px-4 text-xs font-medium text-gray-600 text-left">Opponent</th>
                <th className="py-2 px-4 text-xs font-medium text-gray-600 text-left">Result</th>
                {gameCols.map(c => (
                  <th key={c.label} className="py-2 px-4 text-xs font-medium text-gray-600 text-left">{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {games.map(g => {
                const score = g.away_score !== null ? `${g.away_score}–${g.home_score}` : null
                return (
                  <tr key={g.game_id} className="border-t border-gray-800/60 hover:bg-gray-800/40">
                    <td className="py-2 px-4 text-xs tabular-nums whitespace-nowrap">
                      {g.game_type === 'REG'
                        ? <span className="text-gray-500">Wk {g.week}</span>
                        : <span className="text-amber-500 font-bold">{g.game_type}</span>
                      }
                    </td>
                    <td className="py-2 px-4">
                      <div className="flex items-center gap-1.5">
                        <img src={teamLogoUrl(g.opponent)} alt={g.opponent} className="w-5 h-5 object-contain opacity-60" />
                        <Link
                          to={`/games/${g.game_id}`}
                          state={{ fromPlayer: { playerId, playerName, fromGame } }}
                          className="text-indigo-400 hover:underline text-sm"
                        >
                          {g.location === 'away' ? '@' : 'vs'} {g.opponent}
                        </Link>
                      </div>
                    </td>
                    <td className="py-2 px-4">
                      <div className="flex items-center gap-1.5">
                        {resultBadge(g.result)}
                        {score && <span className="text-gray-600 text-xs">{score}</span>}
                      </div>
                    </td>
                    {gameCols.map(c => {
                      const val = c.cell(g)
                      const isNull = val === null || val === undefined
                      const strVal = isNull ? null : String(val)
                      const isSigned = c.label === 'EPA'
                      const isPos = isSigned && strVal?.startsWith('+')
                      const isNeg = isSigned && strVal?.startsWith('-')
                      return (
                        <td key={c.label} className={`py-2 px-4 tabular-nums text-sm whitespace-nowrap
                          ${isNull ? 'text-gray-700' : isPos ? 'text-emerald-400' : isNeg ? 'text-red-400' : c.highlight ? 'text-white font-semibold' : 'text-gray-300'}`}>
                          {isNull ? '—' : strVal}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// — page —
export default function PlayerPage() {
  const { playerId } = useParams<{ playerId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const fromGame = (location.state as any)?.fromGame
  const [player, setPlayer] = useState<PlayerProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [seasonMap, setSeasonMap] = useState<Record<number, string>>({})

  const statsRef = useRef<HTMLDivElement>(null)
  const advRef   = useRef<HTMLDivElement>(null)
  const postRef  = useRef<HTMLDivElement>(null)
  const logRef   = useRef<HTMLDivElement>(null)
  function scrollTo(ref: ReturnType<typeof useRef<HTMLDivElement>>) {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  useEffect(() => {
    if (!playerId) return
    Promise.all([api.player(playerId), api.seasons()])
      .then(([p, allSeasons]) => {
        setPlayer(p)
        setSeasonMap(Object.fromEntries(allSeasons.map(s => [s.season, s.status])))
      })
      .finally(() => setLoading(false))
  }, [playerId])

  useEffect(() => {
    if (!player || !player.entry_year) return
    const loadedForPlayer = new Set(player.games.map(g => g.season))
    const toQueue: number[] = []
    for (let y = CURRENT_NFL_SEASON; y >= player.entry_year; y--) {
      if (!loadedForPlayer.has(y) && seasonMap[y] === 'available') toQueue.push(y)
    }
    if (toQueue.length === 0) return
    toQueue.forEach(y => api.loadSeason(y))
    setSeasonMap(prev => { const n = { ...prev }; toQueue.forEach(y => { n[y] = 'queued' }); return n })
  }, [player?.player_id, player?.entry_year])

  useEffect(() => {
    if (!player || !player.entry_year) return
    const entryYear = player.entry_year
    const anyInFlight = Object.entries(seasonMap).some(([y, s]) =>
      Number(y) >= entryYear && (s === 'loading' || s === 'queued')
    )
    if (!anyInFlight) return
    const loadedForPlayer = new Set(player.games.map(g => g.season))
    const interval = setInterval(async () => {
      const allSeasons = await api.seasons().catch(() => [] as typeof import('../api').SeasonEntry[])
      const updated = Object.fromEntries(allSeasons.map(s => [s.season, s.status]))
      setSeasonMap(updated)
      const newlyDone = allSeasons.filter(
        s => s.season >= entryYear && !loadedForPlayer.has(s.season) && s.status === 'loaded'
      )
      if (newlyDone.length > 0) api.player(playerId!).then(setPlayer)
      const stillInFlight = allSeasons.some(
        s => s.season >= entryYear && (s.status === 'loading' || s.status === 'queued')
      )
      if (!stillInFlight) clearInterval(interval)
    }, 4000)
    return () => clearInterval(interval)
  }, [player?.player_id, seasonMap])

  if (loading) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Loading...</p></div>
  if (!player) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Player not found.</p></div>

  const regGames     = player.games.filter(g => g.game_type === 'REG')
  const playoffGames = player.games.filter(g => g.game_type !== 'REG')

  const regBySeason = regGames.reduce<Record<number, PlayerGame[]>>((acc, g) => {
    ;(acc[g.season] ??= []).push(g)
    return acc
  }, {})
  const playoffBySeason = playoffGames.reduce<Record<number, PlayerGame[]>>((acc, g) => {
    ;(acc[g.season] ??= []).push(g)
    return acc
  }, {})

  // All games per season for the game log (reg + playoffs together, ordered by week)
  const allBySeason = player.games.reduce<Record<number, PlayerGame[]>>((acc, g) => {
    ;(acc[g.season] ??= []).push(g)
    return acc
  }, {})

  const seasons        = Object.keys(regBySeason).map(Number).sort((a, b) => b - a)
  const playoffSeasons = Object.keys(playoffBySeason).map(Number).sort((a, b) => b - a)
  const allSeasons     = [...new Set([...seasons, ...playoffSeasons])].sort((a, b) => b - a)

  const recentGames = allSeasons.length > 0 ? allBySeason[allSeasons[0]] : []
  const recentTeams = [...new Set(recentGames.map(g => g.team))]
  const currentTeam = recentGames[recentGames.length - 1]?.team ?? player.team

  // Highlights bar and career table use regular season only
  const allTotals   = seasons.length > 0 ? sumGames(seasons.flatMap(s => regBySeason[s])) : sumGames([])
  const careerGames = seasons.reduce((acc, s) => acc + regBySeason[s].length, 0)
  const playerPos   = detectPos(allTotals, player.position)
  const hasAdvanced = playerPos !== 'DEF'

  const careerInFlight = player.entry_year != null
    ? Object.entries(seasonMap).some(([y, s]) => Number(y) >= player.entry_year! && (s === 'loading' || s === 'queued'))
    : false

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">

        {/* Breadcrumb */}
        <div className="flex items-center gap-2 mb-6">
          <button onClick={() => navigate(`/?season=${CURRENT_NFL_SEASON}`)} className="font-black text-base tracking-tight shrink-0">
            <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
          </button>
          {fromGame && (
            <>
              <span className="text-gray-700">/</span>
              <Link to={`/?season=${fromGame.season}`} className="text-gray-400 hover:text-white text-sm transition-colors">{fromGame.season}</Link>
              {fromGame.fromWeek !== undefined && (
                <>
                  <span className="text-gray-700">/</span>
                  <Link to={`/?season=${fromGame.season}&week=${fromGame.fromWeek}`} className="text-gray-400 hover:text-white text-sm transition-colors">Wk {fromGame.fromWeek}</Link>
                </>
              )}
              <span className="text-gray-700">/</span>
              <Link to={`/games/${fromGame.gameId}`} state={{ fromWeek: fromGame.fromWeek }} className="text-gray-400 hover:text-white text-sm transition-colors">{fromGame.awayTeam} @ {fromGame.homeTeam}</Link>
            </>
          )}
          <span className="text-gray-700">/</span>
          <span className="text-gray-400 text-sm truncate">{player.player_name}</span>
          <button
            onClick={() => fromGame ? navigate(`/games/${fromGame.gameId}`, { state: { fromWeek: fromGame.fromWeek } }) : navigate(-1)}
            className="ml-auto shrink-0 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-1.5 transition-colors"
          >
            ← Back
          </button>
        </div>

        {/* Profile header */}
        <div className="flex items-center gap-5 mb-8">
          {player.headshot_url
            ? <img src={player.headshot_url} alt={player.player_name} className="w-20 h-20 rounded-full object-cover bg-gray-800 shrink-0 object-top" />
            : <div className="w-20 h-20 rounded-full bg-gray-800 shrink-0" />
          }
          <div className="flex-1 min-w-0">
            <h1 className="text-3xl font-bold text-white leading-tight">{player.player_name}</h1>
            <div className="text-gray-400 mt-1 flex flex-wrap items-center gap-x-1 text-sm">
              {player.position && <span className="font-medium">{player.position}</span>}
              {recentTeams.length > 0 && (
                <>
                  <span className="text-gray-700 mx-0.5">·</span>
                  {recentTeams.map((t, i) => (
                    <span key={t} className="flex items-center gap-1">
                      {i > 0 && <span className="text-gray-700 mx-0.5">/</span>}
                      <Link to={`/teams/${t}`} className="hover:text-indigo-400 transition-colors">{t}</Link>
                    </span>
                  ))}
                </>
              )}
              {player.jersey_number !== null && currentTeam && <><span className="text-gray-700 mx-0.5">·</span><span>#{player.jersey_number}</span></>}
            </div>
            <div className="flex flex-wrap gap-3 mt-2 text-sm text-gray-600">
              {player.height && <span>{player.height}</span>}
              {player.weight && <span>{player.weight} lbs</span>}
              {player.age && <span>Age {player.age}</span>}
              {player.college && <span>{player.college}</span>}
              {player.entry_year && <span>Since {player.entry_year}</span>}
            </div>
          </div>
        </div>

        {/* Highlights bar — regular season only */}
        {seasons.length > 0 && (
          <HighlightsBar
            pos={playerPos}
            totals={allTotals}
            games={careerGames}
            ngs={player.ngs ?? {}}
          />
        )}

        {/* Sticky section nav */}
        {seasons.length > 0 && (
          <div className="sticky top-0 z-20 -mx-4 px-4 py-2 bg-gray-950/95 backdrop-blur border-b border-gray-800/60 mb-6 flex gap-1">
            <button onClick={() => scrollTo(statsRef)} className="px-3 py-1.5 text-xs font-semibold text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors">Stats</button>
            {hasAdvanced && <button onClick={() => scrollTo(advRef)} className="px-3 py-1.5 text-xs font-semibold text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors">Advanced</button>}
            {playoffSeasons.length > 0 && <button onClick={() => scrollTo(postRef)} className="px-3 py-1.5 text-xs font-semibold text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors">Postseason</button>}
            <button onClick={() => scrollTo(logRef)} className="px-3 py-1.5 text-xs font-semibold text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors">Game Log</button>
          </div>
        )}

        {/* Regular season — main stats */}
        <div ref={statsRef} className="scroll-mt-12 text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">
          Regular Season
        </div>
        <CareerTable
          seasons={seasons}
          bySeason={regBySeason}
          ngs={player.ngs ?? {}}
          snapTotals={player.snap_totals ?? {}}
          situational={player.situational ?? {}}
          wpa={player.wpa ?? {}}
          position={player.position}
          onlyKinds={['trad', 'snap']}
          showGroupHeaders={false}
        />
        {careerInFlight && (
          <p className="text-xs text-gray-600 -mt-2 mb-4 pl-1 flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
            Loading historical seasons — stats will update automatically.
          </p>
        )}

        {/* Regular season — advanced stats */}
        {hasAdvanced && seasons.length > 0 && (
          <>
            <div ref={advRef} className="scroll-mt-12 text-xs font-bold text-gray-500 uppercase tracking-widest mb-3 mt-2">
              Advanced Stats
            </div>
            <CareerTable
              seasons={seasons}
              bySeason={regBySeason}
              ngs={player.ngs ?? {}}
              snapTotals={player.snap_totals ?? {}}
              situational={player.situational ?? {}}
              wpa={player.wpa ?? {}}
              position={player.position}
              onlyKinds={['adv', 'ngs', 'sit', 'wpa']}
            />
          </>
        )}

        {/* Postseason stats */}
        {playoffSeasons.length > 0 && (
          <>
            <div ref={postRef} className="scroll-mt-12 text-xs font-bold text-gray-500 uppercase tracking-widest mb-3 mt-6 flex items-center gap-2">
              Postseason
              <span className="text-gray-700 font-normal normal-case tracking-normal text-xs">
                ({playoffGames.length} game{playoffGames.length !== 1 ? 's' : ''})
              </span>
            </div>
            <CareerTable
              seasons={playoffSeasons}
              bySeason={playoffBySeason}
              ngs={{}}
              snapTotals={player.snap_totals ?? {}}
              situational={{}}
              position={player.position}
              onlyKinds={['trad', 'snap', 'adv']}
              showGroupHeaders={false}
            />

          </>
        )}

        {/* Team splits — regular season only */}
        <TeamSplits seasons={seasons} bySeason={regBySeason} position={player.position} />

        {/* Game log — all games, playoff games show their round label */}
        <div ref={logRef} className="scroll-mt-12 text-xs font-bold text-gray-500 uppercase tracking-widest mb-3 mt-2">Game Log</div>
        <div className="space-y-2">
          {allSeasons.map((s, i) => (
            <GameLog
              key={s}
              season={s}
              games={allBySeason[s]}
              pos={playerPos}
              playerId={player.player_id}
              playerName={player.player_name}
              fromGame={fromGame}
              defaultOpen={i === 0}
            />
          ))}
        </div>

      </div>
    </div>
  )
}
