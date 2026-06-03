import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, Tooltip, Cell, ResponsiveContainer, ReferenceLine } from 'recharts'
import { api } from '../api'
import type { TeamProfile, TeamGame, TeamLeader, SeasonEntry, RosterPlayer, TeamAnalyticsTeam, TeamSplit } from '../api'
import { useTeamDepthChart, useTeamInjuries, useTeamSplits } from '../queries'
import Nav, { backBtnCls } from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'

const GAME_TYPE_LABELS: Record<string, string> = { WC: 'Wild Card', DIV: 'Divisional', CON: 'Conference', SB: 'Super Bowl' }
function weekLabel(week: number, gameType?: string | null) {
  if (gameType && GAME_TYPE_LABELS[gameType]) return GAME_TYPE_LABELS[gameType]
  return `Wk ${week}`
}

function gameResult(g: TeamGame, team: string): 'W' | 'L' | 'T' | null {
  const isAway = g.away_team === team
  const ts = isAway ? g.away_score : g.home_score
  const os = isAway ? g.home_score : g.away_score
  if (ts === null || os === null) return null
  return ts > os ? 'W' : ts < os ? 'L' : 'T'
}

function computeRecord(games: TeamGame[], team: string) {
  let w = 0, l = 0, t = 0
  for (const g of games) {
    const r = gameResult(g, team)
    if (r === 'W') w++; else if (r === 'L') l++; else if (r === 'T') t++
  }
  return { w, l, t, label: t > 0 ? `${w}-${l}-${t}` : `${w}-${l}` }
}

function sv(n: number | null | undefined) { return !n || n === 0 ? '—' : String(n) }
function pct(a: number, b: number) { return b === 0 ? '—' : (a / b * 100).toFixed(1) + '%' }
function avg(y: number, c: number) { return c === 0 ? '—' : (y / c).toFixed(1) }
function ratio(y: number, a: number, d = 1) { return a > 0 ? (y / a).toFixed(d) : null }
function sfmt(x: number, d = 3) { return `${x >= 0 ? '+' : ''}${x.toFixed(d)}` }
function passerRating(cmp: number, att: number, yds: number, td: number, int_: number): number | null {
  if (att === 0) return null
  const clamp = (x: number) => Math.min(2.375, Math.max(0, x))
  const a = clamp((cmp / att - 0.3) / 0.2)
  const b = clamp((yds / att - 3) / 4)
  const c = clamp((td / att) / 0.05)
  const d = clamp(2.375 - (int_ / att) / 0.04)
  return ((a + b + c + d) / 6) * 100
}

type SortDir = 'asc' | 'desc'
type ColKind = 'trad' | 'adv'
type SectionKind = 'passing' | 'rushing' | 'receiving' | 'scrimmage' | 'defense'
type TCol = {
  key: string; label: string; kind: ColKind
  sortVal: (p: TeamLeader) => number
  render: (p: TeamLeader, totals: SectionTotals) => string | number | null
  highlight?: boolean; dim?: boolean
  share?: (p: TeamLeader, totals: SectionTotals) => number
  total?: (totals: SectionTotals, games: number) => string | number | null
}

type SectionTotals = {
  attempts: number; completions: number; pass_yards: number; pass_tds: number
  interceptions_thrown: number; sacks_taken: number; pass_epa: number
  carries: number; rush_yards: number; rush_tds: number; rush_epa: number
  targets: number; receptions: number; rec_yards: number; rec_tds: number
  air_yards: number; yac: number; rec_epa: number
  solo_tackles: number; assist_tackles: number; sacks: number; tackles_for_loss: number
  qb_hits: number; def_interceptions: number; pass_breakups: number
  forced_fumbles: number; fumble_recoveries: number
}

function aggregateTotals(players: TeamLeader[]): SectionTotals {
  const t: SectionTotals = {
    attempts: 0, completions: 0, pass_yards: 0, pass_tds: 0,
    interceptions_thrown: 0, sacks_taken: 0, pass_epa: 0,
    carries: 0, rush_yards: 0, rush_tds: 0, rush_epa: 0,
    targets: 0, receptions: 0, rec_yards: 0, rec_tds: 0,
    air_yards: 0, yac: 0, rec_epa: 0,
    solo_tackles: 0, assist_tackles: 0, sacks: 0, tackles_for_loss: 0,
    qb_hits: 0, def_interceptions: 0, pass_breakups: 0,
    forced_fumbles: 0, fumble_recoveries: 0,
  }
  for (const p of players) {
    t.attempts += p.attempts; t.completions += p.completions
    t.pass_yards += p.pass_yards; t.pass_tds += p.pass_tds
    t.interceptions_thrown += p.interceptions_thrown
    t.sacks_taken += p.sacks_taken
    if (p.pass_epa != null) t.pass_epa += p.pass_epa
    t.carries += p.carries; t.rush_yards += p.rush_yards; t.rush_tds += p.rush_tds
    if (p.rush_epa != null) t.rush_epa += p.rush_epa
    t.targets += p.targets; t.receptions += p.receptions
    t.rec_yards += p.rec_yards; t.rec_tds += p.rec_tds
    if (p.air_yards != null) t.air_yards += p.air_yards
    t.yac += p.yac
    if (p.rec_epa != null) t.rec_epa += p.rec_epa
    t.solo_tackles += p.solo_tackles; t.assist_tackles += p.assist_tackles
    t.sacks += p.sacks; t.tackles_for_loss += p.tackles_for_loss
    t.qb_hits += p.qb_hits; t.def_interceptions += p.def_interceptions
    t.pass_breakups += p.pass_breakups
    t.forced_fumbles += p.forced_fumbles; t.fumble_recoveries += p.fumble_recoveries
  }
  return t
}

type SummaryBox = { label: string; value: string; hint?: string }

function buildSummary(section: SectionKind, t: SectionTotals, games: number): SummaryBox[] {
  const pct = (a: number, b: number) => b > 0 ? `${(a / b * 100).toFixed(1)}%` : '—'
  const rat = (a: number, b: number, d = 1) => b > 0 ? (a / b).toFixed(d) : '—'
  const epa = (a: number, b: number) => b > 0 ? sfmt(a / b) : '—'
  const perg = (a: number) => games > 0 ? (a / games).toFixed(1) : '—'
  switch (section) {
    case 'passing': {
      const rate = passerRating(t.completions, t.attempts, t.pass_yards, t.pass_tds, t.interceptions_thrown)
      return [
        { label: 'CMP/ATT', value: `${t.completions}/${t.attempts}` },
        { label: 'CMP%',    value: pct(t.completions, t.attempts) },
        { label: 'YDS',     value: t.pass_yards.toLocaleString() },
        { label: 'Y/A',     value: rat(t.pass_yards, t.attempts) },
        { label: 'TD-INT',  value: `${t.pass_tds}-${t.interceptions_thrown}` },
        { label: 'SCK',     value: String(t.sacks_taken) },
        { label: 'RATE',    value: rate != null ? rate.toFixed(1) : '—' },
        { label: 'EPA/Att', value: epa(t.pass_epa, t.attempts) },
      ]
    }
    case 'rushing':
      return [
        { label: 'CAR',     value: String(t.carries) },
        { label: 'YDS',     value: t.rush_yards.toLocaleString() },
        { label: 'Y/C',     value: rat(t.rush_yards, t.carries) },
        { label: 'TD',      value: String(t.rush_tds) },
        { label: 'Y/G',     value: perg(t.rush_yards) },
        { label: 'EPA/Car', value: epa(t.rush_epa, t.carries) },
      ]
    case 'receiving':
      return [
        { label: 'REC/TGT', value: `${t.receptions}/${t.targets}` },
        { label: 'CTH%',    value: pct(t.receptions, t.targets) },
        { label: 'YDS',     value: t.rec_yards.toLocaleString() },
        { label: 'Y/R',     value: rat(t.rec_yards, t.receptions) },
        { label: 'TD',      value: String(t.rec_tds) },
        { label: 'YAC',     value: t.yac.toLocaleString() },
        { label: 'aDOT',    value: rat(t.air_yards, t.targets) },
        { label: 'EPA/Tgt', value: epa(t.rec_epa, t.targets) },
      ]
    case 'scrimmage': {
      const tch = t.carries + t.receptions
      const scrim = t.rush_yards + t.rec_yards
      const rushPct = scrim > 0 ? Math.round(t.rush_yards / scrim * 100) : 0
      return [
        { label: 'TCH',     value: String(tch) },
        { label: 'SCRIM',   value: scrim.toLocaleString() },
        { label: 'Y/T',     value: rat(scrim, tch) },
        { label: 'TD',      value: String(t.rush_tds + t.rec_tds) },
        { label: 'Y/G',     value: perg(scrim) },
        { label: 'RUN/REC', value: scrim > 0 ? `${rushPct}/${100 - rushPct}` : '—' },
      ]
    }
    case 'defense': {
      const tkl = t.solo_tackles + t.assist_tackles
      return [
        { label: 'TKL',   value: String(tkl) },
        { label: 'TKL/G', value: perg(tkl) },
        { label: 'SACK',  value: String(t.sacks) },
        { label: 'TFL',   value: String(t.tackles_for_loss) },
        { label: 'QBH',   value: String(t.qb_hits) },
        { label: 'INT',   value: String(t.def_interceptions) },
        { label: 'PBU',   value: String(t.pass_breakups) },
        { label: 'TO',    value: String(t.forced_fumbles + t.fumble_recoveries + t.def_interceptions) },
      ]
    }
  }
}

function SectionStrip({ items }: { items: SummaryBox[] }) {
  return (
    <div className="px-4 py-3 bg-gray-950/40 border-b border-gray-800/80">
      <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
        {items.map(b => (
          <div key={b.label} className="text-center">
            <div className="text-base font-bold text-white tabular-nums leading-tight">{b.value}</div>
            <div className="text-[10px] text-gray-600 uppercase tracking-wider mt-0.5">{b.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SortableTable({ title, section, players, cols, sortKey, sortDir, onSort, onClose, defaultLimit, totals, games }: {
  title: string; section: SectionKind; players: TeamLeader[]; cols: TCol[]
  sortKey: string; sortDir: SortDir; onSort: (k: string) => void; onClose: () => void
  defaultLimit?: number
  totals: SectionTotals
  games: number
}) {
  const [expanded, setExpanded] = useState(false)
  if (!players.length) return null
  const tradCount = cols.filter(c => c.kind === 'trad').length
  const advCount  = cols.filter(c => c.kind === 'adv').length
  const sorted = [...players].sort((a, b) => {
    const col = cols.find(c => c.key === sortKey)
    if (!col) return 0
    const diff = col.sortVal(b) - col.sortVal(a)
    return sortDir === 'desc' ? diff : -diff
  })
  const visible = defaultLimit && !expanded ? sorted.slice(0, defaultLimit) : sorted
  const hiddenCount = sorted.length - (defaultLimit ?? sorted.length)
  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-right cursor-pointer select-none hover:text-white transition-colors'
  return (
    <div className="mb-6 bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{title}</span>
        <span className="text-[10px] text-gray-600 uppercase tracking-wider">Team Totals</span>
      </div>
      <SectionStrip items={buildSummary(section, totals, games)} />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800/50">
              <th colSpan={3} />
              {tradCount > 0 && <th colSpan={tradCount} className="py-1 text-center text-[10px] font-semibold text-gray-600 uppercase tracking-widest border-l border-gray-800/40">Stats</th>}
              {advCount  > 0 && <th colSpan={advCount}  className="py-1 text-center text-[10px] font-semibold text-amber-500/60 uppercase tracking-widest bg-amber-950/20 border-l border-gray-800/40">Advanced</th>}
            </tr>
            <tr className="border-b border-gray-800 bg-gray-800/60">
              <th className="py-2 pl-4 pr-2 text-xs font-medium text-gray-500 text-left whitespace-nowrap">Player</th>
              <th className="py-2 px-2 text-xs font-medium text-gray-500 text-left whitespace-nowrap">Pos</th>
              <th className="py-2 px-3 text-xs font-medium text-gray-500 text-right whitespace-nowrap">G</th>
              {cols.map((c, i) => {
                const active = sortKey === c.key
                const sep = i === 0 || cols[i - 1].kind !== c.kind
                return (
                  <th key={c.key} onClick={() => onSort(c.key)}
                    className={`${thBase} ${sep ? 'border-l border-gray-800/40' : ''}
                      ${c.kind === 'adv' ? 'bg-amber-950/10 text-amber-300/50 hover:text-amber-200' : active ? 'text-white' : 'text-gray-500'}`}>
                    <span className="flex items-center justify-end gap-1">
                      {c.label}
                      <span className={`text-[10px] ${active ? 'opacity-100' : 'opacity-0'}`}>{sortDir === 'desc' ? '↓' : '↑'}</span>
                    </span>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map(p => (
              <tr key={p.player_id} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                <td className="py-2 pl-4 pr-2 whitespace-nowrap">
                  <Link to={`/players/${p.player_id}`} onClick={onClose} className="text-indigo-400 hover:underline font-medium text-sm">{p.player_name}</Link>
                </td>
                <td className="py-2 px-2 text-xs text-gray-500 whitespace-nowrap">{p.position ?? '—'}</td>
                <td className="py-2 px-3 text-right tabular-nums text-gray-500 text-sm">{p.games_played}</td>
                {cols.map((c, i) => {
                  const sep = i === 0 || cols[i - 1].kind !== c.kind
                  const val = c.render(p, totals)
                  const isNull = val === null || val === undefined
                  const str = isNull ? null : String(val)
                  const isPos = !isNull && str!.startsWith('+')
                  const isNeg = !isNull && str!.startsWith('-')
                  const shareVal = c.share ? c.share(p, totals) : 0
                  return (
                    <td key={c.key} className={`relative py-2 px-3 text-right tabular-nums text-sm whitespace-nowrap
                      ${sep ? 'border-l border-gray-800/30' : ''}
                      ${c.kind === 'adv' ? 'bg-amber-950/10' : ''}
                      ${isNull ? 'text-gray-700' : isPos ? 'text-emerald-400 font-semibold' : isNeg ? 'text-red-400 font-semibold' : c.highlight ? 'text-white font-bold' : c.kind === 'adv' ? 'text-amber-200/80' : c.dim ? 'text-gray-500' : 'text-gray-300'}`}>
                      {c.share && shareVal > 0 && !isNull && (
                        <div className="pointer-events-none absolute inset-y-0 left-0 bg-indigo-500/20" style={{ width: `${Math.min(100, shareVal * 100)}%` }} />
                      )}
                      <span className="relative">{isNull ? '—' : str}</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-700/80 bg-gray-800/40">
              <td className="py-2.5 pl-4 pr-2 text-[11px] font-bold text-gray-400 uppercase tracking-wider">Team</td>
              <td />
              <td className="py-2.5 px-3 text-right tabular-nums text-gray-400 text-sm font-semibold">{games > 0 ? games : '—'}</td>
              {cols.map((c, i) => {
                const sep = i === 0 || cols[i - 1].kind !== c.kind
                const val = c.total ? c.total(totals, games) : null
                const isNull = val === null || val === undefined
                const str = isNull ? null : String(val)
                const isPos = !isNull && str!.startsWith('+')
                const isNeg = !isNull && str!.startsWith('-')
                return (
                  <td key={c.key} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap font-bold
                    ${sep ? 'border-l border-gray-800/30' : ''}
                    ${c.kind === 'adv' ? 'bg-amber-950/10' : ''}
                    ${isNull ? 'text-gray-700' : isPos ? 'text-emerald-300' : isNeg ? 'text-red-300' : c.kind === 'adv' ? 'text-amber-200/90' : 'text-gray-200'}`}>
                    <span className="relative">{isNull ? '—' : str}</span>
                  </td>
                )
              })}
            </tr>
            {defaultLimit && hiddenCount > 0 && (
              <tr className="border-t border-gray-800/60">
                <td colSpan={3 + cols.length} className="py-0">
                  <button
                    onClick={() => setExpanded(e => !e)}
                    className="w-full py-2 text-xs text-gray-600 hover:text-gray-400 transition-colors flex items-center justify-center gap-1"
                  >
                    {expanded ? <>show less <span className="text-[10px]">↑</span></> : <>{hiddenCount} more <span className="text-[10px]">↓</span></>}
                  </button>
                </td>
              </tr>
            )}
          </tfoot>
        </table>
      </div>
    </div>
  )
}

const PASS_COLS: TCol[] = [
  { key: 'catt', label: 'C/ATT',   kind: 'trad',                  sortVal: p => p.completions,    render: p => `${p.completions}/${p.attempts}`,
    total: t => `${t.completions}/${t.attempts}` },
  { key: 'cpct', label: 'CMP%',    kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.completions / p.attempts : 0, render: p => p.attempts > 0 ? (p.completions / p.attempts * 100).toFixed(1) : null,
    total: t => t.attempts > 0 ? (t.completions / t.attempts * 100).toFixed(1) : null },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.pass_yards,     render: p => p.pass_yards > 0 ? p.pass_yards.toLocaleString() : null,
    total: t => t.pass_yards > 0 ? t.pass_yards.toLocaleString() : null },
  { key: 'tmpct', label: '% TM',   kind: 'trad', dim: true,       sortVal: p => p.pass_yards,
    render: (p, t) => t.pass_yards > 0 ? `${(p.pass_yards / t.pass_yards * 100).toFixed(1)}%` : null,
    share: (p, t) => t.pass_yards > 0 ? p.pass_yards / t.pass_yards : 0,
    total: () => '100%' },
  { key: 'ya',   label: 'Y/A',     kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.pass_yards / p.attempts : 0, render: p => ratio(p.pass_yards, p.attempts),
    total: t => ratio(t.pass_yards, t.attempts) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.pass_tds,       render: p => p.pass_tds > 0 ? p.pass_tds : null,
    total: t => t.pass_tds > 0 ? t.pass_tds : null },
  { key: 'int',  label: 'INT',     kind: 'trad',                  sortVal: p => p.interceptions_thrown, render: p => p.interceptions_thrown > 0 ? p.interceptions_thrown : null,
    total: t => t.interceptions_thrown > 0 ? t.interceptions_thrown : null },
  { key: 'sck',  label: 'SCK',     kind: 'trad', dim: true,       sortVal: p => p.sacks_taken,    render: p => p.sacks_taken > 0 ? p.sacks_taken : null,
    total: t => t.sacks_taken > 0 ? t.sacks_taken : null },
  { key: 'sckpct', label: 'SCK%',  kind: 'trad', dim: true,       sortVal: p => (p.attempts + p.sacks_taken) > 0 ? p.sacks_taken / (p.attempts + p.sacks_taken) : 0,
    render: p => (p.attempts + p.sacks_taken) > 0 ? (p.sacks_taken / (p.attempts + p.sacks_taken) * 100).toFixed(1) : null,
    total: t => (t.attempts + t.sacks_taken) > 0 ? (t.sacks_taken / (t.attempts + t.sacks_taken) * 100).toFixed(1) : null },
  { key: 'rate', label: 'RATE',    kind: 'trad',                  sortVal: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown) ?? 0, render: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown)?.toFixed(1) ?? null,
    total: t => passerRating(t.completions, t.attempts, t.pass_yards, t.pass_tds, t.interceptions_thrown)?.toFixed(1) ?? null },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.pass_yards / p.games_played : 0, render: p => p.attempts > 0 ? ratio(p.pass_yards, p.games_played) : null,
    total: (t, g) => g > 0 && t.pass_yards > 0 ? (t.pass_yards / g).toFixed(1) : null },
  { key: 'car',  label: 'CAR',     kind: 'trad', dim: true,       sortVal: p => p.carries,        render: p => p.carries > 0 ? p.carries : null,
    total: t => t.carries > 0 ? t.carries : null },
  { key: 'ryds', label: 'RYDS',    kind: 'trad',                  sortVal: p => p.rush_yards,     render: p => p.carries > 0 ? p.rush_yards : null,
    total: t => t.carries > 0 ? t.rush_yards : null },
  { key: 'rtd',  label: 'RTD',     kind: 'trad', dim: true,       sortVal: p => p.rush_tds,       render: p => p.carries > 0 && p.rush_tds > 0 ? p.rush_tds : null,
    total: t => t.carries > 0 && t.rush_tds > 0 ? t.rush_tds : null },
  { key: 'aya',  label: 'AY/A',    kind: 'adv',                   sortVal: p => p.attempts > 0 ? (p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts : 0, render: p => p.attempts > 0 ? ((p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts).toFixed(1) : null,
    total: t => t.attempts > 0 ? ((t.pass_yards + 20 * t.pass_tds - 45 * t.interceptions_thrown) / t.attempts).toFixed(1) : null },
  { key: 'epaa', label: 'EPA/Att', kind: 'adv',                   sortVal: p => p.attempts > 0 && p.pass_epa != null ? p.pass_epa / p.attempts : 0, render: p => p.attempts > 0 && p.pass_epa != null ? sfmt(p.pass_epa / p.attempts) : null,
    total: t => t.attempts > 0 ? sfmt(t.pass_epa / t.attempts) : null },
]
const RUSH_COLS: TCol[] = [
  { key: 'car',  label: 'CAR',     kind: 'trad',                  sortVal: p => p.carries,        render: p => p.carries,
    total: t => t.carries },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rush_yards,     render: p => p.rush_yards > 0 ? p.rush_yards.toLocaleString() : null,
    total: t => t.rush_yards > 0 ? t.rush_yards.toLocaleString() : null },
  { key: 'tmpct', label: '% TM',   kind: 'trad', dim: true,       sortVal: p => p.rush_yards,
    render: (p, t) => t.rush_yards > 0 ? `${(p.rush_yards / t.rush_yards * 100).toFixed(1)}%` : null,
    share: (p, t) => t.rush_yards > 0 ? p.rush_yards / t.rush_yards : 0,
    total: () => '100%' },
  { key: 'ypc',  label: 'Y/C',     kind: 'trad', dim: true,       sortVal: p => p.carries ? p.rush_yards / p.carries : 0, render: p => ratio(p.rush_yards, p.carries),
    total: t => ratio(t.rush_yards, t.carries) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rush_tds,       render: p => p.rush_tds > 0 ? p.rush_tds : null,
    total: t => t.rush_tds > 0 ? t.rush_tds : null },
  { key: 'tdpct', label: 'TD%',    kind: 'trad', dim: true,       sortVal: p => p.carries > 0 ? p.rush_tds / p.carries : 0,
    render: p => p.carries > 0 && p.rush_tds > 0 ? (p.rush_tds / p.carries * 100).toFixed(1) : null,
    total: t => t.carries > 0 && t.rush_tds > 0 ? (t.rush_tds / t.carries * 100).toFixed(1) : null },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rush_yards / p.games_played : 0, render: p => ratio(p.rush_yards, p.games_played),
    total: (t, g) => g > 0 && t.rush_yards > 0 ? (t.rush_yards / g).toFixed(1) : null },
  { key: 'epac', label: 'EPA/Car', kind: 'adv',                   sortVal: p => p.carries > 0 && p.rush_epa != null ? p.rush_epa / p.carries : 0, render: p => p.carries > 0 && p.rush_epa != null ? sfmt(p.rush_epa / p.carries) : null,
    total: t => t.carries > 0 ? sfmt(t.rush_epa / t.carries) : null },
]
const REC_COLS: TCol[] = [
  { key: 'tgt',  label: 'TGT',     kind: 'trad', dim: true,       sortVal: p => p.targets,        render: p => p.targets > 0 ? p.targets : null,
    total: t => t.targets > 0 ? t.targets : null },
  { key: 'rec',  label: 'REC',     kind: 'trad',                  sortVal: p => p.receptions,     render: p => p.receptions > 0 ? p.receptions : null,
    total: t => t.receptions > 0 ? t.receptions : null },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rec_yards,      render: p => p.rec_yards > 0 ? p.rec_yards.toLocaleString() : null,
    total: t => t.rec_yards > 0 ? t.rec_yards.toLocaleString() : null },
  { key: 'tmpct', label: '% TM',   kind: 'trad', dim: true,       sortVal: p => p.rec_yards,
    render: (p, t) => t.rec_yards > 0 ? `${(p.rec_yards / t.rec_yards * 100).toFixed(1)}%` : null,
    share: (p, t) => t.rec_yards > 0 ? p.rec_yards / t.rec_yards : 0,
    total: () => '100%' },
  { key: 'ypr',  label: 'Y/R',     kind: 'trad', dim: true,       sortVal: p => p.receptions ? p.rec_yards / p.receptions : 0, render: p => ratio(p.rec_yards, p.receptions),
    total: t => ratio(t.rec_yards, t.receptions) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rec_tds,        render: p => p.rec_tds > 0 ? p.rec_tds : null,
    total: t => t.rec_tds > 0 ? t.rec_tds : null },
  { key: 'cpct', label: 'CTH%',    kind: 'trad', dim: true,       sortVal: p => p.targets ? p.receptions / p.targets : 0, render: p => p.targets > 0 ? (p.receptions / p.targets * 100).toFixed(1) : null,
    total: t => t.targets > 0 ? (t.receptions / t.targets * 100).toFixed(1) : null },
  { key: 'tdpct', label: 'TD%',    kind: 'trad', dim: true,       sortVal: p => p.targets > 0 ? p.rec_tds / p.targets : 0,
    render: p => p.targets > 0 && p.rec_tds > 0 ? (p.rec_tds / p.targets * 100).toFixed(1) : null,
    total: t => t.targets > 0 && t.rec_tds > 0 ? (t.rec_tds / t.targets * 100).toFixed(1) : null },
  { key: 'yac',  label: 'YAC',     kind: 'trad', dim: true,       sortVal: p => p.yac,
    render: p => p.yac > 0 ? p.yac.toLocaleString() : null,
    total: t => t.yac > 0 ? t.yac.toLocaleString() : null },
  { key: 'yacr', label: 'YAC/R',   kind: 'trad', dim: true,       sortVal: p => p.receptions > 0 ? p.yac / p.receptions : 0,
    render: p => p.receptions > 0 && p.yac > 0 ? (p.yac / p.receptions).toFixed(1) : null,
    total: t => t.receptions > 0 && t.yac > 0 ? (t.yac / t.receptions).toFixed(1) : null },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rec_yards / p.games_played : 0, render: p => ratio(p.rec_yards, p.games_played),
    total: (t, g) => g > 0 && t.rec_yards > 0 ? (t.rec_yards / g).toFixed(1) : null },
  { key: 'ytgt', label: 'Y/TGT',   kind: 'adv',                   sortVal: p => p.targets ? p.rec_yards / p.targets : 0, render: p => ratio(p.rec_yards, p.targets),
    total: t => ratio(t.rec_yards, t.targets) },
  { key: 'aytg', label: 'AY/TGT',  kind: 'adv',                   sortVal: p => p.targets > 0 && p.air_yards != null ? p.air_yards / p.targets : 0, render: p => p.targets > 0 && p.air_yards != null ? ratio(p.air_yards, p.targets) : null,
    total: t => t.targets > 0 ? ratio(t.air_yards, t.targets) : null },
  { key: 'epat', label: 'EPA/Tgt', kind: 'adv',                   sortVal: p => p.targets > 0 && p.rec_epa != null ? p.rec_epa / p.targets : 0, render: p => p.targets > 0 && p.rec_epa != null ? sfmt(p.rec_epa / p.targets) : null,
    total: t => t.targets > 0 ? sfmt(t.rec_epa / t.targets) : null },
]
const SCRIM_COLS: TCol[] = [
  { key: 'tch',   label: 'TCH',   kind: 'trad',                  sortVal: p => p.carries + p.receptions, render: p => (p.carries + p.receptions) > 0 ? (p.carries + p.receptions) : null,
    total: t => (t.carries + t.receptions) > 0 ? (t.carries + t.receptions) : null },
  { key: 'scrim', label: 'SCRIM', kind: 'trad', highlight: true, sortVal: p => p.rush_yards + p.rec_yards, render: p => {
      const v = p.rush_yards + p.rec_yards; return v > 0 ? v.toLocaleString() : null
    },
    total: t => {
      const v = t.rush_yards + t.rec_yards; return v > 0 ? v.toLocaleString() : null
    } },
  { key: 'tmpct', label: '% TM',  kind: 'trad', dim: true,       sortVal: p => p.rush_yards + p.rec_yards,
    render: (p, t) => {
      const team = t.rush_yards + t.rec_yards
      const player = p.rush_yards + p.rec_yards
      return team > 0 ? `${(player / team * 100).toFixed(1)}%` : null
    },
    share: (p, t) => {
      const team = t.rush_yards + t.rec_yards
      return team > 0 ? (p.rush_yards + p.rec_yards) / team : 0
    },
    total: () => '100%' },
  { key: 'ypt',   label: 'Y/T',   kind: 'trad', dim: true,       sortVal: p => (p.carries + p.receptions) > 0 ? (p.rush_yards + p.rec_yards) / (p.carries + p.receptions) : 0,
    render: p => {
      const tch = p.carries + p.receptions
      return tch > 0 ? ((p.rush_yards + p.rec_yards) / tch).toFixed(1) : null
    },
    total: t => {
      const tch = t.carries + t.receptions
      return tch > 0 ? ((t.rush_yards + t.rec_yards) / tch).toFixed(1) : null
    } },
  { key: 'td',    label: 'TD',    kind: 'trad',                  sortVal: p => p.rush_tds + p.rec_tds, render: p => {
      const td = p.rush_tds + p.rec_tds; return td > 0 ? td : null
    },
    total: t => {
      const td = t.rush_tds + t.rec_tds; return td > 0 ? td : null
    } },
  { key: 'ypg',   label: 'Y/G',   kind: 'trad', dim: true,       sortVal: p => p.games_played > 0 ? (p.rush_yards + p.rec_yards) / p.games_played : 0,
    render: p => {
      const v = p.rush_yards + p.rec_yards
      return p.games_played > 0 && v > 0 ? (v / p.games_played).toFixed(1) : null
    },
    total: (t, g) => {
      const v = t.rush_yards + t.rec_yards
      return g > 0 && v > 0 ? (v / g).toFixed(1) : null
    } },
  { key: 'rush',  label: 'RUSH',  kind: 'trad', dim: true,       sortVal: p => p.rush_yards, render: p => p.rush_yards > 0 ? p.rush_yards.toLocaleString() : null,
    total: t => t.rush_yards > 0 ? t.rush_yards.toLocaleString() : null },
  { key: 'rec',   label: 'REC',   kind: 'trad', dim: true,       sortVal: p => p.rec_yards,  render: p => p.rec_yards > 0 ? p.rec_yards.toLocaleString() : null,
    total: t => t.rec_yards > 0 ? t.rec_yards.toLocaleString() : null },
  { key: 'mix',   label: 'RUN/REC', kind: 'adv',                 sortVal: p => {
      const v = p.rush_yards + p.rec_yards; return v > 0 ? p.rush_yards / v : 0
    },
    render: p => {
      const v = p.rush_yards + p.rec_yards
      if (v === 0) return null
      const rushPct = Math.round(p.rush_yards / v * 100)
      return `${rushPct}/${100 - rushPct}`
    },
    total: t => {
      const v = t.rush_yards + t.rec_yards
      if (v === 0) return null
      const rushPct = Math.round(t.rush_yards / v * 100)
      return `${rushPct}/${100 - rushPct}`
    } },
  { key: 'epa',   label: 'EPA',   kind: 'adv',                   sortVal: p => (p.rush_epa ?? 0) + (p.rec_epa ?? 0),
    render: p => {
      const tch = p.carries + p.receptions
      if (tch === 0) return null
      return sfmt((p.rush_epa ?? 0) + (p.rec_epa ?? 0), 1)
    },
    total: t => {
      const tch = t.carries + t.receptions
      return tch > 0 ? sfmt(t.rush_epa + t.rec_epa, 1) : null
    } },
]
const DEF_COLS: TCol[] = [
  { key: 'tot',  label: 'TOT',  kind: 'trad', highlight: true, sortVal: p => p.solo_tackles + p.assist_tackles, render: p => p.solo_tackles + p.assist_tackles,
    total: t => t.solo_tackles + t.assist_tackles },
  { key: 'tmpct', label: '% TM', kind: 'trad', dim: true,       sortVal: p => p.solo_tackles + p.assist_tackles,
    render: (p, t) => {
      const team = t.solo_tackles + t.assist_tackles
      const player = p.solo_tackles + p.assist_tackles
      return team > 0 ? `${(player / team * 100).toFixed(1)}%` : null
    },
    share: (p, t) => {
      const team = t.solo_tackles + t.assist_tackles
      return team > 0 ? (p.solo_tackles + p.assist_tackles) / team : 0
    },
    total: () => '100%' },
  { key: 'tklpg', label: 'TKL/G', kind: 'trad', dim: true,       sortVal: p => p.games_played > 0 ? (p.solo_tackles + p.assist_tackles) / p.games_played : 0,
    render: p => p.games_played > 0 ? ((p.solo_tackles + p.assist_tackles) / p.games_played).toFixed(1) : null,
    total: (t, g) => g > 0 ? ((t.solo_tackles + t.assist_tackles) / g).toFixed(1) : null },
  { key: 'solo', label: 'SOLO', kind: 'trad',                  sortVal: p => p.solo_tackles,        render: p => p.solo_tackles,
    total: t => t.solo_tackles },
  { key: 'ast',  label: 'AST',  kind: 'trad', dim: true,       sortVal: p => p.assist_tackles,      render: p => p.assist_tackles,
    total: t => t.assist_tackles },
  { key: 'tfl',  label: 'TFL',  kind: 'trad',                  sortVal: p => p.tackles_for_loss,    render: p => p.tackles_for_loss > 0 ? p.tackles_for_loss : null,
    total: t => t.tackles_for_loss > 0 ? t.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', kind: 'trad',                  sortVal: p => p.sacks,               render: p => p.sacks > 0 ? p.sacks : null,
    total: t => t.sacks > 0 ? t.sacks : null },
  { key: 'qbh',  label: 'QBH',  kind: 'trad', dim: true,       sortVal: p => p.qb_hits,             render: p => p.qb_hits > 0 ? p.qb_hits : null,
    total: t => t.qb_hits > 0 ? t.qb_hits : null },
  { key: 'int',  label: 'INT',  kind: 'trad',                  sortVal: p => p.def_interceptions,   render: p => p.def_interceptions > 0 ? p.def_interceptions : null,
    total: t => t.def_interceptions > 0 ? t.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  kind: 'trad', dim: true,       sortVal: p => p.pass_breakups,       render: p => p.pass_breakups > 0 ? p.pass_breakups : null,
    total: t => t.pass_breakups > 0 ? t.pass_breakups : null },
  { key: 'ff',   label: 'FF',   kind: 'trad',                  sortVal: p => p.forced_fumbles,      render: p => p.forced_fumbles > 0 ? p.forced_fumbles : null,
    total: t => t.forced_fumbles > 0 ? t.forced_fumbles : null },
  { key: 'fr',   label: 'FR',   kind: 'trad', dim: true,       sortVal: p => p.fumble_recoveries,   render: p => p.fumble_recoveries > 0 ? p.fumble_recoveries : null,
    total: t => t.fumble_recoveries > 0 ? t.fumble_recoveries : null },
]

// ── Season summary ───────────────────────────────────────────────────────────

function SeasonSummary({ profile }: { profile: TeamProfile }) {
  const playedGames = profile.games.filter(g => {
    return (g.away_team === profile.team ? g.away_score : g.home_score) !== null
  })
  const n = playedGames.length

  const pfTotal = playedGames.reduce((s, g) =>
    s + ((g.away_team === profile.team ? g.away_score : g.home_score) ?? 0), 0)
  const paTotal = playedGames.reduce((s, g) =>
    s + ((g.away_team === profile.team ? g.home_score : g.away_score) ?? 0), 0)

  const passYds  = profile.leaders.filter(p => p.attempts >= 1).reduce((s, p) => s + p.pass_yards, 0)
  const rushYds  = profile.leaders.filter(p => p.carries >= 1).reduce((s, p) => s + p.rush_yards, 0)
  const passTDs  = profile.leaders.filter(p => p.attempts >= 1).reduce((s, p) => s + p.pass_tds, 0)
  const rushTDs  = profile.leaders.filter(p => p.carries >= 1).reduce((s, p) => s + p.rush_tds, 0)
  const ints     = profile.leaders.filter(p => p.attempts >= 1).reduce((s, p) => s + p.interceptions_thrown, 0)
  const offEPA   = profile.leaders.reduce((s, p) => {
    if (p.pass_epa != null && p.attempts >= 1) s += p.pass_epa
    if (p.rush_epa != null && p.carries >= 1)  s += p.rush_epa
    return s
  }, 0)

  const diff = pfTotal - paTotal
  const boxes = [
    { label: 'PF/G',     val: n > 0 ? (pfTotal / n).toFixed(1) : '—' },
    { label: 'PA/G',     val: n > 0 ? (paTotal / n).toFixed(1) : '—' },
    { label: 'DIFF',     val: n > 0 ? `${diff >= 0 ? '+' : ''}${diff}` : '—', signed: true },
    { label: 'PASS YDS', val: passYds > 0 ? passYds.toLocaleString() : '—' },
    { label: 'RUSH YDS', val: rushYds > 0 ? rushYds.toLocaleString() : '—' },
    { label: 'TD',       val: (passTDs + rushTDs) || '—' },
    { label: 'INT',      val: ints || '—' },
    { label: 'OFF EPA',  val: offEPA !== 0 ? `${offEPA >= 0 ? '+' : ''}${offEPA.toFixed(1)}` : '—', signed: true },
  ]

  return (
    <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 mb-4">
      {boxes.map(b => {
        const str = String(b.val)
        const isPos = b.signed && str.startsWith('+')
        const isNeg = b.signed && str.startsWith('-')
        return (
          <div key={b.label} className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2.5 text-center">
            <div className={`text-sm font-bold tabular-nums ${isPos ? 'text-emerald-400' : isNeg ? 'text-red-400' : 'text-white'}`}>
              {b.val}
            </div>
            <div className="text-[10px] text-gray-600 uppercase tracking-wider mt-0.5 leading-tight">{b.label}</div>
          </div>
        )
      })}
    </div>
  )
}

// ── Point differential chart ─────────────────────────────────────────────────

function ScoreChart({ profile }: { profile: TeamProfile }) {
  const data = profile.games
    .filter(g => (g.away_team === profile.team ? g.away_score : g.home_score) !== null)
    .map(g => {
      const isAway = g.away_team === profile.team
      const pf = (isAway ? g.away_score : g.home_score) ?? 0
      const pa = (isAway ? g.home_score : g.away_score) ?? 0
      return { name: weekLabel(g.week, (g as any).game_type), diff: pf - pa, pf, pa }
    })

  if (data.length === 0) return null

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 pt-4 pb-2 mb-4">
      <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Point Differential</div>
      <ResponsiveContainer width="100%" height={90}>
        <BarChart data={data} barSize={14} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#4b5563' }} axisLine={false} tickLine={false} interval={0} />
          <ReferenceLine y={0} stroke="#374151" strokeWidth={1} />
          <Tooltip
            contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(_v: unknown, _n: unknown, entry: any) => {
              const { pf, pa, diff } = entry.payload
              return [`${pf}–${pa}  (${diff >= 0 ? '+' : ''}${diff})`, 'Score']
            }}
          />
          <Bar dataKey="diff" radius={[2, 2, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.diff >= 0 ? '#34d399' : '#f87171'} fillOpacity={0.75} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Schedule panel ──────────────────────────────────────────────────────────

function SchedulePanel({ profile }: { profile: TeamProfile }) {
  let w = 0, l = 0, t = 0
  return (
    <div className="overflow-y-auto divide-y divide-gray-800/60 flex-1 min-h-0">
      {profile.games.map(g => {
        const isAway = g.away_team === profile.team
        const opponent = isAway ? g.home_team : g.away_team
        const teamScore = isAway ? g.away_score : g.home_score
        const oppScore = isAway ? g.home_score : g.away_score
        const result = gameResult(g, profile.team)
        const finished = teamScore !== null && oppScore !== null
        const resultColor = result === 'W' ? 'text-green-400' : result === 'L' ? 'text-red-400' : 'text-gray-400'

        if (result === 'W') w++
        else if (result === 'L') l++
        else if (result === 'T') t++
        const runningRec = finished ? (t > 0 ? `${w}-${l}-${t}` : `${w}-${l}`) : null

        return (
          <Link
            key={g.game_id}
            to={`/games/${g.game_id}`}
            className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800/50 transition-colors group"
          >
            <span className="text-xs text-gray-600 w-14 shrink-0">{weekLabel(g.week, (g as any).game_type)}</span>
            <img src={teamLogoUrl(opponent)} alt={opponent} className="w-5 h-5 object-contain shrink-0 opacity-60 group-hover:opacity-100 transition-opacity" />
            <span className="text-sm text-gray-400 flex-1 group-hover:text-white transition-colors">
              {isAway ? '@' : 'vs'} {opponent}
            </span>
            {finished ? (
              <>
                <span className={`text-xs font-bold w-4 text-center ${resultColor}`}>{result}</span>
                <span className="text-xs tabular-nums text-gray-500 w-12 text-right">{teamScore}–{oppScore}</span>
                <span className="text-xs tabular-nums text-gray-700 w-10 text-right">{runningRec}</span>
              </>
            ) : (
              <span className="text-xs text-gray-700 w-16 text-right">{g.gameday}</span>
            )}
          </Link>
        )
      })}
    </div>
  )
}

// ── Leaders panel ────────────────────────────────────────────────────────────

const LEADERS_PREVIEW = 3

interface LeaderRowProps {
  player: TeamLeader
  primary: { value: string; label: string }
  secondary: string
}
function LeaderRow({ player, primary, secondary }: LeaderRowProps) {
  return (
    <Link to={`/players/${player.player_id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800/50 transition-colors group">
      {player.headshot_url
        ? <img src={player.headshot_url} alt={player.player_name} className="w-8 h-8 rounded-full object-cover shrink-0 opacity-80 group-hover:opacity-100 transition-opacity" />
        : <div className="w-8 h-8 rounded-full bg-gray-800 shrink-0 flex items-center justify-center text-xs text-gray-600">#</div>
      }
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-gray-200 truncate group-hover:text-white transition-colors">{player.player_name}</div>
        <div className="text-xs text-gray-600">{player.position ?? '—'} · {player.games_played}G</div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-base font-bold text-white tabular-nums">{primary.value} <span className="text-xs font-normal text-gray-500">{primary.label}</span></div>
        <div className="text-xs text-gray-500 tabular-nums">{secondary}</div>
      </div>
    </Link>
  )
}

function LeaderSection({ title, rows }: { title: string; rows: React.ReactNode[] }) {
  if (!rows.length) return null
  return (
    <div>
      <div className="px-4 py-1.5 bg-gray-800/40 border-t border-gray-800">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{title}</span>
      </div>
      {rows}
    </div>
  )
}

function LeadersPanel({ leaders, onViewFull }: { leaders: TeamLeader[]; onViewFull: () => void }) {
  const passers   = leaders.filter(p => p.attempts >= 50).sort((a, b) => b.pass_yards - a.pass_yards).slice(0, LEADERS_PREVIEW)
  const rushers   = leaders.filter(p => p.carries >= 20).sort((a, b) => b.rush_yards - a.rush_yards).slice(0, LEADERS_PREVIEW)
  const receivers = leaders.filter(p => p.targets >= 10).sort((a, b) => b.rec_yards - a.rec_yards).slice(0, LEADERS_PREVIEW)
  const defenders = leaders
    .filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
    .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles))
    .slice(0, LEADERS_PREVIEW)

  return (
    <div>
      <LeaderSection title="Passing" rows={passers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.pass_yards), label: 'YDS' }}
          secondary={`${sv(p.pass_tds)} TD · ${sv(p.interceptions_thrown)} INT · ${pct(p.completions, p.attempts)}`}
        />
      ))} />
      <LeaderSection title="Rushing" rows={rushers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.rush_yards), label: 'YDS' }}
          secondary={`${sv(p.carries)} CAR · ${avg(p.rush_yards, p.carries)} YPC · ${sv(p.rush_tds)} TD`}
        />
      ))} />
      <LeaderSection title="Receiving" rows={receivers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.rec_yards), label: 'YDS' }}
          secondary={`${sv(p.receptions)}/${sv(p.targets)} REC · ${avg(p.rec_yards, p.receptions)} YPR · ${sv(p.rec_tds)} TD`}
        />
      ))} />
      <LeaderSection title="Defense" rows={defenders.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.solo_tackles + p.assist_tackles), label: 'TKL' }}
          secondary={`${sv(p.sacks)} SCK · ${sv(p.def_interceptions)} INT · ${sv(p.pass_breakups)} PBU`}
        />
      ))} />
      <button
        onClick={onViewFull}
        className="w-full text-xs text-indigo-400 hover:text-indigo-300 py-2.5 border-t border-gray-800 transition-colors font-medium"
      >
        Full season stats →
      </button>
    </div>
  )
}

// ── Full stats modal ─────────────────────────────────────────────────────────

function StatsSections({ leaders, sorts, onSort, onClose, games }: {
  leaders: TeamLeader[]
  sorts: Record<string, { key: string; dir: SortDir }>
  onSort: (section: string, key: string) => void
  onClose: () => void
  games: number
}) {
  const passers   = leaders.filter(p => p.attempts >= 1).sort((a, b) => b.pass_yards - a.pass_yards)
  const rushers   = leaders.filter(p => p.carries >= 1).sort((a, b) => b.rush_yards - a.rush_yards)
  const receivers = leaders.filter(p => p.targets >= 1).sort((a, b) => b.rec_yards - a.rec_yards)
  const scrimmers = leaders.filter(p => (p.carries + p.receptions) >= 1).sort((a, b) => (b.rush_yards + b.rec_yards) - (a.rush_yards + a.rec_yards))
  const defenders = leaders
    .filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
    .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles))
  const passT = aggregateTotals(passers)
  const rushT = aggregateTotals(rushers)
  const recT  = aggregateTotals(receivers)
  const scrimT = aggregateTotals(scrimmers)
  const defT  = aggregateTotals(defenders)
  return (
    <>
      <SortableTable title="Passing"   section="passing"   players={passers}   cols={PASS_COLS}  sortKey={sorts.passing.key}   sortDir={sorts.passing.dir}   onSort={k => onSort('passing',   k)} onClose={onClose} totals={passT}  games={games} />
      <SortableTable title="Rushing"   section="rushing"   players={rushers}   cols={RUSH_COLS}  sortKey={sorts.rushing.key}   sortDir={sorts.rushing.dir}   onSort={k => onSort('rushing',   k)} onClose={onClose} totals={rushT}  games={games} />
      <SortableTable title="Receiving" section="receiving" players={receivers} cols={REC_COLS}   sortKey={sorts.receiving.key} sortDir={sorts.receiving.dir} onSort={k => onSort('receiving', k)} onClose={onClose} totals={recT}   games={games} />
      <SortableTable title="Scrimmage" section="scrimmage" players={scrimmers} cols={SCRIM_COLS} sortKey={sorts.scrimmage.key} sortDir={sorts.scrimmage.dir} onSort={k => onSort('scrimmage', k)} onClose={onClose} totals={scrimT} games={games} defaultLimit={10} />
      <SortableTable title="Defense"   section="defense"   players={defenders} cols={DEF_COLS}   sortKey={sorts.defense.key}   sortDir={sorts.defense.dir}   onSort={k => onSort('defense',   k)} onClose={onClose} totals={defT}   games={games} defaultLimit={15} />
    </>
  )
}

const DEFAULT_SORTS = {
  passing:   { key: 'yds', dir: 'desc' as SortDir },
  rushing:   { key: 'yds', dir: 'desc' as SortDir },
  receiving: { key: 'yds', dir: 'desc' as SortDir },
  scrimmage: { key: 'scrim', dir: 'desc' as SortDir },
  defense:   { key: 'tot', dir: 'desc' as SortDir },
}

function countTeamGames(profile: TeamProfile, type: 'reg' | 'post'): number {
  return profile.games.filter(g => {
    const gt = (g as any).game_type as string | undefined
    const isReg = !gt || gt === 'REG'
    const matchType = type === 'reg' ? isReg : !isReg
    if (!matchType) return false
    const ts = g.away_team === profile.team ? g.away_score : g.home_score
    const os = g.away_team === profile.team ? g.home_score : g.away_score
    return ts !== null && os !== null
  }).length
}

function FullStatsModal({ profile, onClose }: { profile: TeamProfile; onClose: () => void }) {
  const hasPlayoffs = profile.playoff_leaders?.length > 0
  const [regSorts, setRegSorts]  = useState({ ...DEFAULT_SORTS })
  const [postSorts, setPostSorts] = useState({ ...DEFAULT_SORTS })
  const regGames = countTeamGames(profile, 'reg')
  const postGames = countTeamGames(profile, 'post')

  function makeSort(setSorts: typeof setRegSorts) {
    return (section: string, key: string) => setSorts(prev => {
      const cur = prev[section as keyof typeof prev]
      return { ...prev, [section]: { key, dir: cur.key === key && cur.dir === 'desc' ? 'asc' : 'desc' } }
    })
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-gray-950">
      <div className="flex items-center gap-2 px-6 py-4 border-b border-gray-800 shrink-0">
        <span className="font-black text-base tracking-tight select-none shrink-0">
          <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
        </span>
        <span className="text-gray-700">/</span>
        <img src={teamLogoUrl(profile.team)} alt={profile.team} className="w-5 h-5 object-contain shrink-0" />
        <span className="text-gray-400 text-sm">{teamName(profile.team)}</span>
        <span className="text-gray-700">/</span>
        <span className="text-gray-400 text-sm">{profile.season} Stats</span>
        <button onClick={onClose}
          className="ml-auto shrink-0 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-1.5 transition-colors"
        >
          ← Back
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-6xl mx-auto w-full">
        <div className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-5">Regular Season</div>
        <StatsSections leaders={profile.leaders} sorts={regSorts} onSort={makeSort(setRegSorts)} onClose={onClose} games={regGames} />

        {hasPlayoffs && (
          <>
            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-5 mt-4">Postseason</div>
            <StatsSections leaders={profile.playoff_leaders} sorts={postSorts} onSort={makeSort(setPostSorts)} onClose={onClose} games={postGames} />
          </>
        )}
      </div>
    </div>
  )
}

// ── Roster modal ─────────────────────────────────────────────────────────────

const ROSTER_GROUPS = [
  { label: 'Quarterbacks',   positions: new Set(['QB']) },
  { label: 'Running Backs',  positions: new Set(['RB', 'FB', 'HB']) },
  { label: 'Wide Receivers', positions: new Set(['WR']) },
  { label: 'Tight Ends',     positions: new Set(['TE']) },
  { label: 'Offensive Line', positions: new Set(['C', 'G', 'T', 'OT', 'OG', 'OL', 'RT', 'LT', 'RG', 'LG', 'LS']) },
  { label: 'Defensive Line', positions: new Set(['DE', 'DT', 'NT', 'EDGE', 'DL']) },
  { label: 'Linebackers',    positions: new Set(['LB', 'ILB', 'OLB', 'MLB']) },
  { label: 'Cornerbacks',    positions: new Set(['CB', 'DB']) },
  { label: 'Safeties',       positions: new Set(['S', 'SS', 'FS', 'SAF']) },
  { label: 'Kickers',        positions: new Set(['K']) },
  { label: 'Punters',        positions: new Set(['P']) },
  { label: 'Special Teams',  positions: new Set(['KR', 'PR', 'ST']) },
]
const ROSTER_MAPPED = new Set(ROSTER_GROUPS.flatMap(g => [...g.positions]))

function RosterModal({ profile, roster, onClose }: { profile: TeamProfile; roster: RosterPlayer[]; onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const grouped = ROSTER_GROUPS
    .map(g => ({ label: g.label, players: roster.filter(p => g.positions.has(p.position ?? '')) }))
    .filter(g => g.players.length > 0)
  const other = roster.filter(p => !ROSTER_MAPPED.has(p.position ?? ''))

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-gray-950">
      <div className="flex items-center gap-2 px-6 py-4 border-b border-gray-800 shrink-0">
        <span className="font-black text-base tracking-tight select-none shrink-0">
          <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
        </span>
        <span className="text-gray-700">/</span>
        <img src={teamLogoUrl(profile.team)} alt={profile.team} className="w-5 h-5 object-contain shrink-0" />
        <span className="text-gray-400 text-sm">{teamName(profile.team)}</span>
        <span className="text-gray-700">/</span>
        <span className="text-gray-400 text-sm">{profile.season} Roster</span>
        <button onClick={onClose} className="ml-auto shrink-0 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-1.5 transition-colors">
          ← Back
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-5xl mx-auto w-full">
        {grouped.length === 0
          ? <p className="text-gray-600">No roster data available for this season.</p>
          : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[...grouped, ...(other.length > 0 ? [{ label: 'Other', players: other }] : [])].map(g => (
                <div key={g.label} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                  <div className="px-4 py-2.5 border-b border-gray-800">
                    <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{g.label}</span>
                  </div>
                  <div className="divide-y divide-gray-800/60">
                    {g.players.map(p => (
                      <Link key={p.player_id} to={`/players/${p.player_id}`} onClick={onClose}
                        className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800/40 transition-colors group">
                        {p.headshot_url
                          ? <img src={p.headshot_url} alt={p.player_name} className="w-8 h-8 rounded-full object-cover shrink-0 bg-gray-800" />
                          : <div className="w-8 h-8 rounded-full bg-gray-800 shrink-0 flex items-center justify-center text-xs text-gray-600">{p.player_name[0]}</div>
                        }
                        <div className="min-w-0">
                          <div className="text-sm text-indigo-400 group-hover:underline font-medium truncate">{p.player_name}</div>
                          {p.jersey_number != null && <div className="text-xs text-gray-600">#{p.jersey_number}</div>}
                        </div>
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )
        }
      </div>
    </div>
  )
}

// ── Team Analytics: 22 ranked league metrics ─────────────────────────────────

type MetricSpec = {
  key: string
  label: string
  hint?: string
  value: number | null | undefined
  rank: number | null | undefined
  fmt: (v: number) => string
}

function fmtSigned(d = 3) { return (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}` }
function fmtPct(d = 1)    { return (v: number) => `${v.toFixed(d)}%` }
function fmtNum(d = 1)    { return (v: number) => v.toFixed(d) }

function rankClasses(rank: number): string {
  if (rank <= 6)  return 'text-green-300 bg-green-950/60 border-green-800/60'
  if (rank <= 13) return 'text-emerald-300 bg-emerald-950/40 border-emerald-800/40'
  if (rank <= 19) return 'text-gray-300 bg-gray-800/60 border-gray-700/50'
  if (rank <= 26) return 'text-orange-300 bg-orange-950/40 border-orange-800/40'
  return 'text-red-300 bg-red-950/60 border-red-800/60'
}

function RankBadge({ rank }: { rank: number | null | undefined }) {
  if (rank == null) return <span className="text-gray-700 text-xs">—</span>
  return (
    <span className={`inline-block text-xs font-bold tabular-nums rounded px-1.5 py-0.5 border ${rankClasses(rank)}`}>
      #{rank}
    </span>
  )
}

function MetricRow({ m }: { m: MetricSpec }) {
  const hasValue = m.value != null && Number.isFinite(m.value as number)
  return (
    <tr className="border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors">
      <td className="py-1.5 pl-4 pr-2 text-gray-400 text-xs whitespace-nowrap" title={m.hint}>{m.label}</td>
      <td className="py-1.5 px-2 text-right tabular-nums text-white text-sm font-semibold whitespace-nowrap">
        {hasValue ? m.fmt(m.value as number) : <span className="text-gray-700">—</span>}
      </td>
      <td className="py-1.5 pr-4 pl-2 text-right whitespace-nowrap">
        <RankBadge rank={m.rank} />
      </td>
    </tr>
  )
}

function MetricPanel({ title, accent, metrics }: { title: string; accent: string; metrics: MetricSpec[] }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-800 flex items-center gap-2">
        <span className={`text-xs font-bold uppercase tracking-wider ${accent}`}>{title}</span>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {metrics.map(m => <MetricRow key={m.key} m={m} />)}
        </tbody>
      </table>
    </div>
  )
}

function buildOffenseMetrics(t: TeamAnalyticsTeam): MetricSpec[] {
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

function buildDefenseMetrics(t: TeamAnalyticsTeam): MetricSpec[] {
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

function buildOverallMetrics(t: TeamAnalyticsTeam): MetricSpec[] {
  return [
    { key: 'ptdiff', label: 'Point Diff / Game',   hint: '(PF − PA) / games',                               value: t.pt_diff_per_game,           rank: t.pt_diff_rank,                   fmt: fmtSigned(1) },
    { key: 'todiff', label: 'Turnover Diff / Game',hint: '(takeaways − giveaways) / games',                 value: t.turnover_diff_per_game,     rank: t.to_diff_rank,                   fmt: fmtSigned(2) },
  ]
}

// — team situational splits: offense/defense rate profile by situation —

const TEAM_SPLIT_DIMS: { key: string; label: string }[] = [
  { key: 'down',        label: 'Down' },
  { key: 'game_script', label: 'Game Script' },
  { key: 'field_zone',  label: 'Field Zone' },
  { key: 'quarter',     label: 'Quarter' },
]

const TEAM_SPLIT_VALUE_LABELS: Record<string, string> = {
  '1': '1st Down', '2': '2nd Down', '3': '3rd Down', '4': '4th Down',
  leading: 'Leading', tied: 'Tied', trailing: 'Trailing',
  red_zone: 'Red Zone', opp_territory: 'Opp Territory', own_territory: 'Own Territory',
}
function teamSplitValueLabel(dim: string, value: string): string {
  if (dim === 'quarter') return value === 'OT' ? 'OT' : `Q${value}`
  return TEAM_SPLIT_VALUE_LABELS[value] ?? value
}

const fmtSign3 = (v: number | null | undefined) => v == null ? null : `${v >= 0 ? '+' : ''}${v.toFixed(3)}`
const fmtPct1  = (v: number | null | undefined) => v == null ? null : `${v.toFixed(1)}%`
const fmtNum2  = (v: number | null | undefined) => v == null ? null : v.toFixed(2)

type TeamSplitCol = { label: string; get: (r: TeamSplit) => string | null; signed?: boolean; highlight?: boolean; heat?: 'epa' | 'pct' }
const TEAM_SPLIT_COLS: TeamSplitCol[] = [
  { label: 'PLAYS',    get: r => r.plays != null ? String(r.plays) : null },
  { label: 'EPA/play', get: r => fmtSign3(r.epa_play), signed: true, heat: 'epa' },
  { label: 'SUCC%',    get: r => fmtPct1(r.success_pct), heat: 'pct' },
  { label: 'YDS/play', get: r => fmtNum2(r.yards_play), highlight: true },
  { label: 'EXPL%',    get: r => fmtPct1(r.explosive_pct) },
  { label: 'PASS%',    get: r => fmtPct1(r.pass_rate) },
  { label: 'PASS EPA', get: r => fmtSign3(r.pass_epa), signed: true },
  { label: 'RUSH EPA', get: r => fmtSign3(r.rush_epa), signed: true },
]

function aggregateTeamSplit(rows: TeamSplit[]): TeamSplit | null {
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

function TeamSplitsPanel({ team, season }: { team: string; season: number }) {
  const { data: splits = [], isPending } = useTeamSplits(team, season)
  const [side, setSide] = useState<'offense' | 'defense'>('offense')
  const [dim, setDim] = useState('game_script')

  const rows = splits
    .filter(s => s.side === side && s.split_dim === dim)
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
  const totalRow = aggregateTeamSplit(rows)

  // Heat is goodness-aware: for defense, lower EPA/success allowed is better,
  // so the sign flips. Green = better than this unit's own average.
  const heatStyle = (r: TeamSplit, c: TeamSplitCol): React.CSSProperties | undefined => {
    if (!c.heat || !totalRow) return undefined
    const val  = c.heat === 'epa' ? r.epa_play : r.success_pct
    const base = c.heat === 'epa' ? totalRow.epa_play : totalRow.success_pct
    if (val == null || base == null) return undefined
    const good = (side === 'offense' ? 1 : -1) * (val - base)
    const alpha = Math.min(0.3, Math.abs(good) * (c.heat === 'epa' ? 0.7 : 0.022))
    if (alpha < 0.03) return undefined
    return { backgroundColor: `rgba(${good >= 0 ? '16,185,129' : '244,63,94'}, ${alpha.toFixed(3)})` }
  }

  const insight = (() => {
    const eligible = rows.filter(r => (r.plays ?? 0) >= 15 && r.epa_play != null)
    if (eligible.length < 2) return null
    const best = side === 'offense'
      ? eligible.reduce((a, b) => (b.epa_play! > a.epa_play! ? b : a))
      : eligible.reduce((a, b) => (b.epa_play! < a.epa_play! ? b : a))
    return { label: teamSplitValueLabel(dim, best.split_value), epa: best.epa_play! }
  })()

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-left'
  const segWrap = 'inline-flex items-center gap-0.5 bg-gray-900 border border-gray-800 rounded-lg p-0.5'

  const renderRow = (r: TeamSplit, isTotal: boolean) => (
    <tr key={r.split_value} className={isTotal
      ? 'border-t-2 border-gray-700 bg-gray-800/40'
      : 'border-t border-gray-800/60 hover:bg-gray-800/30'}>
      <td className={`py-2.5 pl-4 pr-3 whitespace-nowrap ${isTotal
        ? 'text-xs font-bold text-gray-400 uppercase tracking-wider'
        : 'font-semibold text-white'}`}>
        {isTotal ? 'Total' : teamSplitValueLabel(dim, r.split_value)}
      </td>
      {TEAM_SPLIT_COLS.map(c => {
        const raw = c.get(r)
        const isNull = raw == null
        const str = isNull ? '—' : raw
        const isPos = c.signed && !isNull && str.startsWith('+')
        const isNeg = c.signed && !isNull && str.startsWith('-')
        return (
          <td key={c.label}
            style={isTotal ? undefined : heatStyle(r, c)}
            className={`py-2.5 px-3 whitespace-nowrap tabular-nums ${isTotal ? 'font-semibold' : ''} ${
            isNull ? 'text-gray-700'
              : isPos ? 'text-emerald-300 font-semibold'
              : isNeg ? 'text-red-300 font-semibold'
              : c.highlight ? 'text-white font-bold'
              : 'text-gray-200'}`}>
            {str}
          </td>
        )
      })}
    </tr>
  )

  if (isPending || splits.length === 0) return null

  return (
    <div className="mb-4">
      <div className="flex items-baseline justify-between gap-3 mb-2 px-1">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Situational Splits</h3>
        {insight && (
          <span className="text-xs text-gray-500">
            {side === 'offense' ? 'Best' : 'Stingiest'}: <span className="text-emerald-400 font-semibold">{insight.label}</span>
            <span className="text-gray-600"> · {fmtSign3(insight.epa)} EPA</span>
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className={segWrap}>
          {(['offense', 'defense'] as const).map(s => (
            <button key={s} onClick={() => { setSide(s); setDim('game_script') }}
              className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded-md transition-colors ${
                side === s ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'}`}>
              {s}
            </button>
          ))}
        </div>
        <div className={`${segWrap} flex-wrap`}>
          {TEAM_SPLIT_DIMS.map(d => (
            <button key={d.key} onClick={() => setDim(d.key)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                dim === d.key ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}>
              {d.label}
            </button>
          ))}
        </div>
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className={`${thBase} text-gray-500 pl-4`}>
                  {TEAM_SPLIT_DIMS.find(d => d.key === dim)?.label}
                </th>
                {TEAM_SPLIT_COLS.map(c => (
                  <th key={c.label} className={`${thBase} text-gray-500`}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => renderRow(r, false))}
              {rows.length > 1 && totalRow && renderRow(totalRow, true)}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-2 px-1">
        <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: 'rgba(16,185,129,0.4)' }} />
        <span className="text-[11px] text-gray-600">better than this unit's average</span>
        <span className="inline-block w-2.5 h-2.5 rounded-sm ml-2" style={{ backgroundColor: 'rgba(244,63,94,0.4)' }} />
        <span className="text-[11px] text-gray-600">worse · {side === 'defense' ? 'lower EPA allowed = better' : 'regular season'}</span>
      </div>
    </div>
  )
}

function TeamAnalytics({ team, season }: { team: string; season: number }) {
  const [focal, setFocal] = useState<TeamAnalyticsTeam | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setFocal(null)
    let cancelled = false
    api.teamAnalytics(season)
      .then(res => {
        if (cancelled) return
        setFocal(res.league.find(t => t.team === team) ?? null)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [team, season])

  if (loading) {
    return (
      <div className="mb-4 bg-gray-900 border border-gray-800 rounded-xl px-4 py-8 text-center text-gray-600 text-sm">
        Loading analytics…
      </div>
    )
  }
  if (!focal) {
    return (
      <div className="mb-4 bg-gray-900 border border-gray-800 rounded-xl px-4 py-6 text-center text-gray-600 text-sm">
        Analytics unavailable for this season.
      </div>
    )
  }

  const offense = buildOffenseMetrics(focal)
  const defense = buildDefenseMetrics(focal)
  const overall = buildOverallMetrics(focal)

  return (
    <div className="mb-4">
      <div className="flex items-end justify-between mb-2 px-1">
        <div>
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Team Analytics</h3>
          <p className="text-xs text-gray-600 mt-0.5">League rank out of 32 · regular season · 1 = best</p>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <MetricPanel title="Offense"          accent="text-indigo-400"  metrics={offense} />
        <MetricPanel title="Defense"          accent="text-red-400"     metrics={defense} />
        <div className="space-y-4">
          <MetricPanel title="Overall"        accent="text-amber-400"   metrics={overall} />
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-xs text-gray-500">
            <div className="grid grid-cols-2 gap-y-1.5">
              <span>Record</span><span className="text-right text-gray-300 font-semibold">{focal.wins}-{focal.losses}{focal.ties ? `-${focal.ties}` : ''}</span>
              <span>Games</span><span className="text-right text-gray-300">{focal.games}</span>
              <span>Points For</span><span className="text-right text-gray-300">{focal.pf_total}</span>
              <span>Points Against</span><span className="text-right text-gray-300">{focal.pa_total}</span>
              <span>Off Drives</span><span className="text-right text-gray-300">{focal.total_drives ?? '—'}</span>
              <span>Def Drives</span><span className="text-right text-gray-300">{focal.total_drives_allowed ?? '—'}</span>
              <span>Giveaways</span><span className="text-right text-gray-300">{focal.off_turnovers_total}</span>
              <span>Takeaways</span><span className="text-right text-gray-300">{focal.def_takeaways_total}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Current-week injury report + starting lineup ────────────────────────────
// Both use vendor data loaded by load_supplemental_data — fall back to a
// "Not yet available" empty state if the season hasn't been refreshed since
// the supplemental ingest landed.

function injuryToneClasses(status: string | null | undefined): string {
  switch (status) {
    case 'Out':           return 'bg-rose-950/40 border-rose-800/70 text-rose-300'
    case 'Doubtful':      return 'bg-orange-950/40 border-orange-800/70 text-orange-300'
    case 'Questionable':  return 'bg-amber-950/40 border-amber-800/70 text-amber-300'
    case 'Probable':      return 'bg-emerald-950/40 border-emerald-800/70 text-emerald-300'
    default:              return 'bg-gray-900 border-gray-800 text-gray-400'
  }
}

function InjuryReportPanel({ team, season }: { team: string; season: number }) {
  const { data: injuries = [], isPending } = useTeamInjuries(team, season)
  if (isPending) return null
  if (injuries.length === 0) return null

  // injuries are already ordered server-side by severity
  const headline = `Week ${injuries[0].week} Injury Report`

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{headline}</span>
        <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">{injuries.length} listed</span>
      </div>
      <ul className="divide-y divide-gray-800/60">
        {injuries.map((inj, i) => (
          <li key={`${inj.gsis_id}-${i}`} className="px-4 py-2.5 flex items-center gap-3 text-sm">
            <span className={`shrink-0 inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${injuryToneClasses(inj.report_status)}`}>
              {inj.report_status ?? '—'}
            </span>
            <span className="shrink-0 text-[11px] text-gray-600 w-9 text-center font-bold">{inj.position ?? ''}</span>
            <span className="flex-1 min-w-0 text-gray-200 truncate">{inj.full_name ?? '—'}</span>
            <span className="text-xs text-gray-500 truncate max-w-[40%]">
              {inj.report_primary_injury ?? '—'}
              {inj.report_secondary_injury && <span className="text-gray-700"> · {inj.report_secondary_injury}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function StartingLineupPanel({ team, season }: { team: string; season: number }) {
  const { data: depth = [], isPending } = useTeamDepthChart(team, season)
  if (isPending) return null

  const starters = depth.filter(d => d.depth_team === '1')
  const offense = starters.filter(d => d.formation === 'Offense')
  const defense = starters.filter(d => d.formation === 'Defense')

  if (offense.length === 0 && defense.length === 0) return null

  const week = depth[0]?.week
  const headline = week ? `Week ${week} Starting Lineup` : 'Starting Lineup'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{headline}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-gray-800/60">
        {offense.length > 0 && <LineupColumn label="Offense" rows={offense} />}
        {defense.length > 0 && <LineupColumn label="Defense" rows={defense} />}
      </div>
    </div>
  )
}

function LineupColumn({ label, rows }: { label: string; rows: { depth_position: string | null; full_name: string | null; position: string | null }[] }) {
  return (
    <div className="p-3">
      <div className="text-[10px] font-bold text-gray-600 uppercase tracking-widest mb-2 px-1">{label}</div>
      <ul className="space-y-0.5">
        {rows.map((r, i) => (
          <li key={`${r.depth_position}-${i}`} className="flex items-center gap-2 px-1 py-1 text-sm">
            <span className="shrink-0 text-[10px] font-bold text-indigo-400 w-10 uppercase tracking-wider">
              {r.depth_position ?? r.position ?? ''}
            </span>
            <span className="flex-1 min-w-0 text-gray-300 truncate">{r.full_name ?? '—'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── Season detail ────────────────────────────────────────────────────────────

function SeasonDetail({ profile }: { profile: TeamProfile }) {
  const [statsOpen, setStatsOpen] = useState(false)
  const [rosterOpen, setRosterOpen] = useState(false)
  const [roster, setRoster] = useState<RosterPlayer[]>([])
  const { w, l, t, label } = computeRecord(profile.games, profile.team)
  const played = w + l + t

  useEffect(() => {
    api.teamRoster(profile.team, profile.season).then(setRoster).catch(() => {})
  }, [profile.team, profile.season])

  return (
    <>
      {statsOpen && <FullStatsModal profile={profile} onClose={() => setStatsOpen(false)} />}
      {rosterOpen && <RosterModal profile={profile} roster={roster} onClose={() => setRosterOpen(false)} />}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-white font-bold text-xl">{profile.season} Season</div>
          <div className="text-gray-500 text-sm">{played} games · {label}</div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setRosterOpen(true)}
            className="text-sm text-gray-400 hover:text-white bg-gray-800/60 hover:bg-gray-700/60 border border-gray-700 rounded-lg px-4 py-2 transition-colors font-medium"
          >
            Roster
          </button>
          <button
            onClick={() => setStatsOpen(true)}
            className="text-sm text-indigo-400 hover:text-white bg-indigo-900/30 hover:bg-indigo-800/50 border border-indigo-700/50 rounded-lg px-4 py-2 transition-colors font-medium"
          >
            Full Stats
          </button>
        </div>
      </div>
      <SeasonSummary profile={profile} />
      <TeamAnalytics team={profile.team} season={profile.season} />
      <TeamSplitsPanel team={profile.team} season={profile.season} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <InjuryReportPanel team={profile.team} season={profile.season} />
        <StartingLineupPanel team={profile.team} season={profile.season} />
      </div>
      <ScoreChart profile={profile} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden flex flex-col">
          <div className="px-4 py-2.5 border-b border-gray-800">
            <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Schedule</span>
          </div>
          <SchedulePanel profile={profile} />
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden flex flex-col">
          <div className="px-4 py-2.5 border-b border-gray-800">
            <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Leaders</span>
          </div>
          <LeadersPanel leaders={profile.leaders} onViewFull={() => setStatsOpen(true)} />
        </div>
      </div>
    </>
  )
}

// ── Season sidebar ───────────────────────────────────────────────────────────

type SeasonStatus = SeasonEntry['status']

function StatusDot({ status }: { status: SeasonStatus }) {
  if (status === 'loading')
    return <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse shrink-0" />
  if (status === 'queued')
    return <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-600 animate-pulse shrink-0" />
  return null
}

function SeasonSidebar({
  profiles, selected, onSelect, seasonStatuses, onQueueSeason,
}: {
  profiles: TeamProfile[]
  selected: number
  onSelect: (season: number) => void
  seasonStatuses: Record<number, SeasonStatus>
  onQueueSeason: (year: number) => void
}) {
  const team = profiles[0]?.team ?? ''
  const profileMap = Object.fromEntries(profiles.map(p => [p.season, p]))

  // Seasons to show: all loaded + queued/loading, sorted newest first
  const inFlight = Object.entries(seasonStatuses)
    .filter(([, s]) => s === 'loading' || s === 'queued')
    .map(([y]) => Number(y))
  const loadedYears = profiles.map(p => p.season)
  const visibleYears = [...new Set([...loadedYears, ...inFlight])].sort((a, b) => b - a)

  // Next year to surface — either the next un-fetched loaded season or the next available one
  const oldest = Math.min(...loadedYears, ...inFlight)
  const nextAvailable = oldest > 1999 ? oldest - 1 : null
  const nextStatus = nextAvailable ? seasonStatuses[nextAvailable] : null
  const nextHasProfile = nextAvailable ? !!profileMap[nextAvailable] : false
  const canLoadMore = nextAvailable && (
    !nextStatus || nextStatus === 'available' || nextStatus === 'error' ||
    (nextStatus === 'loaded' && !nextHasProfile)
  )

  return (
    <div className="flex flex-col border border-gray-800 rounded-xl overflow-hidden bg-gray-900 shrink-0 lg:w-40">
      <div className="px-4 py-2.5 border-b border-gray-800 bg-gray-800/40">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Seasons</span>
      </div>
      <div className="overflow-y-auto">
        {visibleYears.map(year => {
          const profile = profileMap[year]
          const status = seasonStatuses[year] ?? (profile ? 'loaded' : 'available')
          const active = year === selected
          const inProgress = status === 'loading' || status === 'queued'
          const rec = profile ? computeRecord(profile.games, team) : null

          return (
            <button
              key={year}
              onClick={() => profile ? onSelect(year) : undefined}
              disabled={inProgress && !profile}
              className={`w-full text-left px-4 py-3 border-b border-gray-800/60 transition-colors
                ${active ? 'bg-indigo-900/30 border-l-2 border-l-indigo-500' : 'hover:bg-gray-800/60'}
                ${inProgress && !profile ? 'cursor-default' : ''}`}
            >
              <div className="flex items-center gap-1.5">
                <StatusDot status={status} />
                <span className={`text-sm font-bold ${active ? 'text-indigo-300' : inProgress ? 'text-gray-400' : 'text-gray-300'}`}>
                  {year}
                </span>
              </div>
              <div className="text-xs text-gray-600 mt-0.5">
                {inProgress ? (status === 'loading' ? 'Loading…' : 'Queued') : rec ? rec.label : ''}
              </div>
            </button>
          )
        })}
      </div>
      {canLoadMore && (
        <button
          onClick={() => onQueueSeason(nextAvailable!)}
          className="text-xs text-gray-600 hover:text-gray-300 py-2.5 border-t border-gray-800 transition-colors"
        >
          + {nextAvailable}
        </button>
      )}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

import { CURRENT_NFL_SEASON } from '../api'
const CURRENT_SEASON = CURRENT_NFL_SEASON
const AUTO_SEASONS = 5  // fetch/queue this many recent seasons automatically

export default function TeamPage() {
  const { teamAbbrev } = useParams<{ teamAbbrev: string }>()
  const navigate = useNavigate()
  const [profiles, setProfiles] = useState<TeamProfile[]>([])
  const [selectedSeason, setSelectedSeason] = useState<number>(CURRENT_SEASON)
  const [initialLoading, setInitialLoading] = useState(true)
  const [seasonStatuses, setSeasonStatuses] = useState<Record<number, SeasonStatus>>({})

  // On mount: get season list, fetch loaded profiles, queue missing ones
  useEffect(() => {
    if (!teamAbbrev) return
    let cancelled = false
    setProfiles([])
    setInitialLoading(true)

    const years = Array.from({ length: AUTO_SEASONS }, (_, i) => CURRENT_SEASON - i)

    api.seasons().then(allSeasons => {
      if (cancelled) return
      const statuses = Object.fromEntries(allSeasons.map(s => [s.season, s.status])) as Record<number, SeasonStatus>
      setSeasonStatuses(statuses)
      setInitialLoading(false)

      const toFetch = years.filter(y => statuses[y] === 'loaded')
      const toQueue = years.filter(y => statuses[y] === 'available' || statuses[y] === 'error')

      if (toFetch.length > 0) {
        Promise.all(toFetch.map(y => api.team(teamAbbrev, y).catch(() => null))).then(results => {
          if (cancelled) return
          const fetched = results.filter(Boolean) as TeamProfile[]
          setProfiles(fetched.sort((a, b) => b.season - a.season))
          if (fetched.length > 0) setSelectedSeason(fetched[0].season)
        })
      }

      if (toQueue.length > 0) {
        toQueue.forEach(y => api.loadSeason(y))
        const next = { ...statuses }
        toQueue.forEach(y => { next[y] = 'queued' })
        setSeasonStatuses(next)
      }
    })

    return () => { cancelled = true }
  }, [teamAbbrev])

  // Poll while any season is in-flight; fetch team profile when one completes
  useEffect(() => {
    const anyInFlight = Object.values(seasonStatuses).some(s => s === 'loading' || s === 'queued')
    if (!anyInFlight || !teamAbbrev) return

    const loadedYears = new Set(profiles.map(p => p.season))

    const interval = setInterval(async () => {
      const allSeasons = await api.seasons().catch(() => [] as SeasonEntry[])
      const updated = Object.fromEntries(allSeasons.map(s => [s.season, s.status])) as Record<number, SeasonStatus>
      setSeasonStatuses(updated)

      // Fetch team profile for any season that just finished loading
      const newlyLoaded = allSeasons.filter(s => !loadedYears.has(s.season) && s.status === 'loaded')
      for (const s of newlyLoaded) {
        api.team(teamAbbrev, s.season)
          .then(p => setProfiles(prev => [...prev.filter(x => x.season !== p.season), p].sort((a, b) => b.season - a.season)))
          .catch(() => {})
      }

      if (!allSeasons.some(s => s.status === 'loading' || s.status === 'queued')) {
        clearInterval(interval)
      }
    }, 4000)

    return () => clearInterval(interval)
  }, [teamAbbrev, seasonStatuses])

  // Auto-select the newest available season when profiles first arrive
  useEffect(() => {
    if (profiles.length > 0 && !profiles.find(p => p.season === selectedSeason)) {
      setSelectedSeason(profiles[0].season)
    }
  }, [profiles])

  function handleQueueSeason(year: number) {
    if (seasonStatuses[year] === 'loaded') {
      api.team(teamAbbrev!, year)
        .then(p => setProfiles(prev => [...prev.filter(x => x.season !== p.season), p].sort((a, b) => b.season - a.season)))
        .catch(() => {})
    } else {
      api.loadSeason(year).catch(() => {})
      setSeasonStatuses(prev => ({ ...prev, [year]: 'queued' }))
    }
  }

  if (initialLoading) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Loading...</p></div>
  if (!teamAbbrev) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Team not found.</p></div>

  if (!profiles.length) {
    const anyInFlight = Object.values(seasonStatuses).some(s => s === 'loading' || s === 'queued')
    return (
      <div className="min-h-screen bg-gray-950">
        <Nav />
        <div className="max-w-6xl mx-auto px-4 py-8">
          <div className="flex items-center gap-5 mb-8">
            <img src={teamLogoUrl(teamAbbrev)} alt={teamAbbrev} className="w-20 h-20 object-contain shrink-0" />
            <div>
              <h1 className="text-3xl font-bold text-white leading-tight">{teamName(teamAbbrev)}</h1>
              {anyInFlight
                ? <div className="text-gray-500 mt-1 flex items-center gap-2">
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                    Loading season data — updates automatically…
                  </div>
                : <p className="text-gray-600 mt-1">No data available for this team.</p>
              }
            </div>
          </div>
        </div>
      </div>
    )
  }

  const allGames = profiles.flatMap(p => p.games)
  const allTime = computeRecord(allGames, teamAbbrev)
  const activeProfile = profiles.find(p => p.season === selectedSeason) ?? profiles[0]

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav title={teamName(teamAbbrev)} />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <button onClick={() => navigate(-1)} className={`${backBtnCls} mb-6`}>← Back</button>

        <div className="flex items-center gap-5 mb-8">
          <img src={teamLogoUrl(teamAbbrev)} alt={teamAbbrev} className="w-20 h-20 object-contain shrink-0" />
          <div>
            <h1 className="text-3xl font-bold text-white leading-tight">{teamName(teamAbbrev)}</h1>
            <div className="text-gray-400 mt-1">
              {profiles.length} season{profiles.length !== 1 ? 's' : ''} loaded ·{' '}
              <span className="text-white font-semibold">{allTime.label}</span>
              <span className="text-gray-600 text-xs ml-2">{allTime.w + allTime.l + allTime.t} games</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col lg:flex-row gap-4 items-start">
          <SeasonSidebar
            profiles={profiles}
            selected={activeProfile.season}
            onSelect={setSelectedSeason}
            seasonStatuses={seasonStatuses}
            onQueueSeason={handleQueueSeason}
          />
          <div className="flex-1 min-w-0">
            <SeasonDetail profile={activeProfile} />
          </div>
        </div>

      </div>
    </div>
  )
}
