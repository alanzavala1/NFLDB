import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../api'
import type { TeamProfile, TeamGame, TeamLeader, SeasonEntry } from '../api'
import Nav from '../components/Nav'
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
type TCol = {
  key: string; label: string; kind: ColKind
  sortVal: (p: TeamLeader) => number
  render: (p: TeamLeader) => string | number | null
  highlight?: boolean; dim?: boolean
}

function SortableTable({ title, players, cols, sortKey, sortDir, onSort, onClose, defaultLimit }: {
  title: string; players: TeamLeader[]; cols: TCol[]
  sortKey: string; sortDir: SortDir; onSort: (k: string) => void; onClose: () => void
  defaultLimit?: number
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
      <div className="px-4 py-3 border-b border-gray-800">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{title}</span>
      </div>
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
                  const val = c.render(p)
                  const isNull = val === null || val === undefined
                  const str = isNull ? null : String(val)
                  const isPos = !isNull && str!.startsWith('+')
                  const isNeg = !isNull && str!.startsWith('-')
                  return (
                    <td key={c.key} className={`py-2 px-3 text-right tabular-nums text-sm whitespace-nowrap
                      ${sep ? 'border-l border-gray-800/30' : ''}
                      ${c.kind === 'adv' ? 'bg-amber-950/10' : ''}
                      ${isNull ? 'text-gray-700' : isPos ? 'text-emerald-400 font-semibold' : isNeg ? 'text-red-400 font-semibold' : c.highlight ? 'text-white font-bold' : c.kind === 'adv' ? 'text-amber-200/80' : c.dim ? 'text-gray-500' : 'text-gray-300'}`}>
                      {isNull ? '—' : str}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
          {defaultLimit && hiddenCount > 0 && (
            <tfoot>
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
            </tfoot>
          )}
        </table>
      </div>
    </div>
  )
}

const PASS_COLS: TCol[] = [
  { key: 'catt', label: 'C/ATT',   kind: 'trad',                  sortVal: p => p.completions,    render: p => `${p.completions}/${p.attempts}` },
  { key: 'cpct', label: 'CMP%',    kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.completions / p.attempts : 0, render: p => p.attempts > 0 ? (p.completions / p.attempts * 100).toFixed(1) : null },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.pass_yards,     render: p => p.pass_yards > 0 ? p.pass_yards.toLocaleString() : null },
  { key: 'ya',   label: 'Y/A',     kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.pass_yards / p.attempts : 0, render: p => ratio(p.pass_yards, p.attempts) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.pass_tds,       render: p => p.pass_tds > 0 ? p.pass_tds : null },
  { key: 'int',  label: 'INT',     kind: 'trad',                  sortVal: p => p.interceptions_thrown, render: p => p.interceptions_thrown > 0 ? p.interceptions_thrown : null },
  { key: 'sck',  label: 'SCK',     kind: 'trad', dim: true,       sortVal: p => p.sacks_taken,    render: p => p.sacks_taken > 0 ? p.sacks_taken : null },
  { key: 'rate', label: 'RATE',    kind: 'trad',                  sortVal: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown) ?? 0, render: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown)?.toFixed(1) ?? null },
  { key: 'car',  label: 'CAR',     kind: 'trad', dim: true,       sortVal: p => p.carries,        render: p => p.carries > 0 ? p.carries : null },
  { key: 'ryds', label: 'RYDS',    kind: 'trad',                  sortVal: p => p.rush_yards,     render: p => p.carries > 0 ? p.rush_yards : null },
  { key: 'rtd',  label: 'RTD',     kind: 'trad', dim: true,       sortVal: p => p.rush_tds,       render: p => p.carries > 0 && p.rush_tds > 0 ? p.rush_tds : null },
  { key: 'aya',  label: 'AY/A',    kind: 'adv',                   sortVal: p => p.attempts > 0 ? (p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts : 0, render: p => p.attempts > 0 ? ((p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts).toFixed(1) : null },
  { key: 'epaa', label: 'EPA/Att', kind: 'adv',                   sortVal: p => p.attempts > 0 && p.pass_epa != null ? p.pass_epa / p.attempts : 0, render: p => p.attempts > 0 && p.pass_epa != null ? sfmt(p.pass_epa / p.attempts) : null },
]
const RUSH_COLS: TCol[] = [
  { key: 'car',  label: 'CAR',     kind: 'trad',                  sortVal: p => p.carries,        render: p => p.carries },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rush_yards,     render: p => p.rush_yards > 0 ? p.rush_yards.toLocaleString() : null },
  { key: 'ypc',  label: 'Y/C',     kind: 'trad', dim: true,       sortVal: p => p.carries ? p.rush_yards / p.carries : 0, render: p => ratio(p.rush_yards, p.carries) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rush_tds,       render: p => p.rush_tds > 0 ? p.rush_tds : null },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rush_yards / p.games_played : 0, render: p => ratio(p.rush_yards, p.games_played) },
  { key: 'epac', label: 'EPA/Car', kind: 'adv',                   sortVal: p => p.carries > 0 && p.rush_epa != null ? p.rush_epa / p.carries : 0, render: p => p.carries > 0 && p.rush_epa != null ? sfmt(p.rush_epa / p.carries) : null },
]
const REC_COLS: TCol[] = [
  { key: 'tgt',  label: 'TGT',     kind: 'trad', dim: true,       sortVal: p => p.targets,        render: p => p.targets > 0 ? p.targets : null },
  { key: 'rec',  label: 'REC',     kind: 'trad',                  sortVal: p => p.receptions,     render: p => p.receptions > 0 ? p.receptions : null },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rec_yards,      render: p => p.rec_yards > 0 ? p.rec_yards.toLocaleString() : null },
  { key: 'ypr',  label: 'Y/R',     kind: 'trad', dim: true,       sortVal: p => p.receptions ? p.rec_yards / p.receptions : 0, render: p => ratio(p.rec_yards, p.receptions) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rec_tds,        render: p => p.rec_tds > 0 ? p.rec_tds : null },
  { key: 'cpct', label: 'CTH%',    kind: 'trad', dim: true,       sortVal: p => p.targets ? p.receptions / p.targets : 0, render: p => p.targets > 0 ? (p.receptions / p.targets * 100).toFixed(1) : null },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rec_yards / p.games_played : 0, render: p => ratio(p.rec_yards, p.games_played) },
  { key: 'ytgt', label: 'Y/TGT',   kind: 'adv',                   sortVal: p => p.targets ? p.rec_yards / p.targets : 0, render: p => ratio(p.rec_yards, p.targets) },
  { key: 'aytg', label: 'AY/TGT',  kind: 'adv',                   sortVal: p => p.targets > 0 && p.air_yards != null ? p.air_yards / p.targets : 0, render: p => p.targets > 0 && p.air_yards != null ? ratio(p.air_yards, p.targets) : null },
  { key: 'epat', label: 'EPA/Tgt', kind: 'adv',                   sortVal: p => p.targets > 0 && p.rec_epa != null ? p.rec_epa / p.targets : 0, render: p => p.targets > 0 && p.rec_epa != null ? sfmt(p.rec_epa / p.targets) : null },
]
const DEF_COLS: TCol[] = [
  { key: 'tot',  label: 'TOT',  kind: 'trad', highlight: true, sortVal: p => p.solo_tackles + p.assist_tackles, render: p => p.solo_tackles + p.assist_tackles },
  { key: 'solo', label: 'SOLO', kind: 'trad',                  sortVal: p => p.solo_tackles,        render: p => p.solo_tackles },
  { key: 'ast',  label: 'AST',  kind: 'trad', dim: true,       sortVal: p => p.assist_tackles,      render: p => p.assist_tackles },
  { key: 'tfl',  label: 'TFL',  kind: 'trad',                  sortVal: p => p.tackles_for_loss,    render: p => p.tackles_for_loss > 0 ? p.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', kind: 'trad',                  sortVal: p => p.sacks,               render: p => p.sacks > 0 ? p.sacks : null },
  { key: 'qbh',  label: 'QBH',  kind: 'trad', dim: true,       sortVal: p => p.qb_hits,             render: p => p.qb_hits > 0 ? p.qb_hits : null },
  { key: 'int',  label: 'INT',  kind: 'trad',                  sortVal: p => p.def_interceptions,   render: p => p.def_interceptions > 0 ? p.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  kind: 'trad', dim: true,       sortVal: p => p.pass_breakups,       render: p => p.pass_breakups > 0 ? p.pass_breakups : null },
  { key: 'ff',   label: 'FF',   kind: 'trad',                  sortVal: p => p.forced_fumbles,      render: p => p.forced_fumbles > 0 ? p.forced_fumbles : null },
  { key: 'fr',   label: 'FR',   kind: 'trad', dim: true,       sortVal: p => p.fumble_recoveries,   render: p => p.fumble_recoveries > 0 ? p.fumble_recoveries : null },
]

// ── Schedule panel ──────────────────────────────────────────────────────────

function SchedulePanel({ profile }: { profile: TeamProfile }) {
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

function StatsSections({ leaders, sorts, onSort, onClose }: {
  leaders: TeamLeader[]
  sorts: Record<string, { key: string; dir: SortDir }>
  onSort: (section: string, key: string) => void
  onClose: () => void
}) {
  const passers   = leaders.filter(p => p.attempts >= 1).sort((a, b) => b.pass_yards - a.pass_yards)
  const rushers   = leaders.filter(p => p.carries >= 1).sort((a, b) => b.rush_yards - a.rush_yards)
  const receivers = leaders.filter(p => p.targets >= 1).sort((a, b) => b.rec_yards - a.rec_yards)
  const defenders = leaders
    .filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
    .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles))
  return (
    <>
      <SortableTable title="Passing"   players={passers}   cols={PASS_COLS} sortKey={sorts.passing.key}   sortDir={sorts.passing.dir}   onSort={k => onSort('passing',   k)} onClose={onClose} />
      <SortableTable title="Rushing"   players={rushers}   cols={RUSH_COLS} sortKey={sorts.rushing.key}   sortDir={sorts.rushing.dir}   onSort={k => onSort('rushing',   k)} onClose={onClose} />
      <SortableTable title="Receiving" players={receivers} cols={REC_COLS}  sortKey={sorts.receiving.key} sortDir={sorts.receiving.dir} onSort={k => onSort('receiving', k)} onClose={onClose} />
      <SortableTable title="Defense"   players={defenders} cols={DEF_COLS}  sortKey={sorts.defense.key}   sortDir={sorts.defense.dir}   onSort={k => onSort('defense',   k)} onClose={onClose} defaultLimit={15} />
    </>
  )
}

const DEFAULT_SORTS = {
  passing:   { key: 'yds', dir: 'desc' as SortDir },
  rushing:   { key: 'yds', dir: 'desc' as SortDir },
  receiving: { key: 'yds', dir: 'desc' as SortDir },
  defense:   { key: 'tot', dir: 'desc' as SortDir },
}

function FullStatsModal({ profile, onClose }: { profile: TeamProfile; onClose: () => void }) {
  const hasPlayoffs = profile.playoff_leaders?.length > 0
  const [regSorts, setRegSorts]  = useState({ ...DEFAULT_SORTS })
  const [postSorts, setPostSorts] = useState({ ...DEFAULT_SORTS })

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
        <button onClick={onClose} className="font-black text-base tracking-tight shrink-0">
          <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
        </button>
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
        <StatsSections leaders={profile.leaders} sorts={regSorts} onSort={makeSort(setRegSorts)} onClose={onClose} />

        {hasPlayoffs && (
          <>
            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-5 mt-4">Postseason</div>
            <StatsSections leaders={profile.playoff_leaders} sorts={postSorts} onSort={makeSort(setPostSorts)} onClose={onClose} />
          </>
        )}
      </div>
    </div>
  )
}

// ── Season detail ────────────────────────────────────────────────────────────

function SeasonDetail({ profile }: { profile: TeamProfile }) {
  const [statsOpen, setStatsOpen] = useState(false)
  const { w, l, t, label } = computeRecord(profile.games, profile.team)
  const played = w + l + t

  return (
    <>
      {statsOpen && <FullStatsModal profile={profile} onClose={() => setStatsOpen(false)} />}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-white font-bold text-xl">{profile.season} Season</div>
          <div className="text-gray-500 text-sm">{played} games · {label}</div>
        </div>
        <button
          onClick={() => setStatsOpen(true)}
          className="text-sm text-indigo-400 hover:text-white bg-indigo-900/30 hover:bg-indigo-800/50 border border-indigo-700/50 rounded-lg px-4 py-2 transition-colors font-medium"
        >
          Full Stats
        </button>
      </div>
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
const FIRST_SEASON = 1999
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
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">

        <div className="flex items-center gap-2 mb-5">
          <button onClick={() => navigate(`/?season=${CURRENT_NFL_SEASON}`)} className="text-gray-500 hover:text-white transition-colors p-1 rounded-md hover:bg-gray-800" title="Home">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7A1 1 0 003 11h1v6a1 1 0 001 1h4v-4h2v4h4a1 1 0 001-1v-6h1a1 1 0 00.707-1.707l-7-7z" />
            </svg>
          </button>
          <span className="text-gray-700">/</span>
          <span className="text-gray-400 text-sm">{teamName(teamAbbrev)}</span>
          <button onClick={() => navigate(-1)} className="ml-auto flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-2 transition-colors">
            ← Back
          </button>
        </div>

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
