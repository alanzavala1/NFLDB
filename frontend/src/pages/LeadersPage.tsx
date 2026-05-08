import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { LeagueLeader, SeasonEntry, WpaLeader, WpaLeaders } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl } from '../utils/teams'

function passerRating(cmp: number, att: number, yds: number, td: number, int_: number): number | null {
  if (att === 0) return null
  const clamp = (x: number) => Math.min(2.375, Math.max(0, x))
  const a = clamp((cmp / att - 0.3) / 0.2)
  const b = clamp((yds / att - 3) / 4)
  const c = clamp((td / att) / 0.05)
  const d = clamp(2.375 - (int_ / att) / 0.04)
  return ((a + b + c + d) / 6) * 100
}
function pct(a: number, b: number) { return b > 0 ? (a / b * 100).toFixed(1) : null }
function ratio(y: number, a: number, d = 1) { return a > 0 ? (y / a).toFixed(d) : null }
function sfmt(x: number, d = 3) { return `${x >= 0 ? '+' : ''}${x.toFixed(d)}` }

type SortDir = 'asc' | 'desc'
type ColKind = 'trad' | 'adv'

type Col = {
  key: string
  label: string
  kind: ColKind
  sortVal: (p: LeagueLeader) => number
  render: (p: LeagueLeader) => string | number | null
  highlight?: boolean
  dim?: boolean
}

const PASSING_COLS: Col[] = [
  { key: 'g',    label: 'G',       kind: 'trad', dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'catt', label: 'C/ATT',   kind: 'trad',                  sortVal: p => p.completions,    render: p => `${p.completions}/${p.attempts}` },
  { key: 'cpct', label: 'CMP%',    kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.completions / p.attempts : 0, render: p => pct(p.completions, p.attempts) },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.pass_yards,     render: p => p.pass_yards.toLocaleString() },
  { key: 'ya',   label: 'Y/A',     kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.pass_yards / p.attempts : 0, render: p => ratio(p.pass_yards, p.attempts) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.pass_tds,       render: p => p.pass_tds },
  { key: 'int',  label: 'INT',     kind: 'trad',                  sortVal: p => p.interceptions_thrown, render: p => p.interceptions_thrown },
  { key: 'sck',  label: 'SCK',     kind: 'trad', dim: true,       sortVal: p => p.sacks_taken,    render: p => p.sacks_taken },
  { key: 'rate', label: 'RATE',    kind: 'trad',                  sortVal: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown) ?? 0, render: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown)?.toFixed(1) ?? null },
  { key: 'car',  label: 'CAR',     kind: 'trad', dim: true,       sortVal: p => p.carries,        render: p => p.carries > 0 ? p.carries : null },
  { key: 'ryds', label: 'RYDS',    kind: 'trad',                  sortVal: p => p.rush_yards,     render: p => p.carries > 0 ? p.rush_yards : null },
  { key: 'rtd',  label: 'RTD',     kind: 'trad', dim: true,       sortVal: p => p.rush_tds,       render: p => p.carries > 0 && p.rush_tds > 0 ? p.rush_tds : null },
  { key: 'aya',  label: 'AY/A',    kind: 'adv',                   sortVal: p => p.attempts > 0 ? (p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts : 0, render: p => p.attempts > 0 ? ((p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts).toFixed(1) : null },
  { key: 'epaa', label: 'EPA/Att', kind: 'adv',                   sortVal: p => p.attempts > 0 && p.pass_epa != null ? p.pass_epa / p.attempts : 0, render: p => p.attempts > 0 && p.pass_epa != null ? sfmt(p.pass_epa / p.attempts) : null },
]

const RUSHING_COLS: Col[] = [
  { key: 'g',    label: 'G',       kind: 'trad', dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'car',  label: 'CAR',     kind: 'trad',                  sortVal: p => p.carries,        render: p => p.carries },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rush_yards,     render: p => p.rush_yards.toLocaleString() },
  { key: 'ypc',  label: 'Y/C',     kind: 'trad', dim: true,       sortVal: p => p.carries ? p.rush_yards / p.carries : 0, render: p => ratio(p.rush_yards, p.carries) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rush_tds,       render: p => p.rush_tds },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rush_yards / p.games_played : 0, render: p => ratio(p.rush_yards, p.games_played) },
  { key: 'epac', label: 'EPA/Car', kind: 'adv',                   sortVal: p => p.carries > 0 && p.rush_epa != null ? p.rush_epa / p.carries : 0, render: p => p.carries > 0 && p.rush_epa != null ? sfmt(p.rush_epa / p.carries) : null },
]

const RECEIVING_COLS: Col[] = [
  { key: 'g',    label: 'G',       kind: 'trad', dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'tgt',  label: 'TGT',     kind: 'trad', dim: true,       sortVal: p => p.targets,        render: p => p.targets },
  { key: 'rec',  label: 'REC',     kind: 'trad',                  sortVal: p => p.receptions,     render: p => p.receptions },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rec_yards,      render: p => p.rec_yards.toLocaleString() },
  { key: 'ypr',  label: 'Y/R',     kind: 'trad', dim: true,       sortVal: p => p.receptions ? p.rec_yards / p.receptions : 0, render: p => ratio(p.rec_yards, p.receptions) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rec_tds,        render: p => p.rec_tds },
  { key: 'cpct', label: 'CTH%',    kind: 'trad', dim: true,       sortVal: p => p.targets ? p.receptions / p.targets : 0, render: p => pct(p.receptions, p.targets) },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rec_yards / p.games_played : 0, render: p => ratio(p.rec_yards, p.games_played) },
  { key: 'ytgt', label: 'Y/TGT',   kind: 'adv',                   sortVal: p => p.targets ? p.rec_yards / p.targets : 0, render: p => ratio(p.rec_yards, p.targets) },
  { key: 'aytg', label: 'AY/TGT',  kind: 'adv',                   sortVal: p => p.targets > 0 && p.air_yards != null ? p.air_yards / p.targets : 0, render: p => p.targets > 0 && p.air_yards != null ? ratio(p.air_yards, p.targets) : null },
  { key: 'epat', label: 'EPA/Tgt', kind: 'adv',                   sortVal: p => p.targets > 0 && p.rec_epa != null ? p.rec_epa / p.targets : 0, render: p => p.targets > 0 && p.rec_epa != null ? sfmt(p.rec_epa / p.targets) : null },
]

const DEFENSE_COLS: Col[] = [
  { key: 'g',    label: 'G',    kind: 'trad', dim: true,       sortVal: p => p.games_played,             render: p => p.games_played },
  { key: 'tot',  label: 'TOT',  kind: 'trad', highlight: true, sortVal: p => p.solo_tackles + p.assist_tackles, render: p => p.solo_tackles + p.assist_tackles },
  { key: 'solo', label: 'SOLO', kind: 'trad',                  sortVal: p => p.solo_tackles,             render: p => p.solo_tackles },
  { key: 'ast',  label: 'AST',  kind: 'trad', dim: true,       sortVal: p => p.assist_tackles,           render: p => p.assist_tackles },
  { key: 'tfl',  label: 'TFL',  kind: 'trad',                  sortVal: p => p.tackles_for_loss,         render: p => p.tackles_for_loss > 0 ? p.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', kind: 'trad',                  sortVal: p => p.sacks,                    render: p => p.sacks > 0 ? p.sacks : null },
  { key: 'qbh',  label: 'QBH',  kind: 'trad', dim: true,       sortVal: p => p.qb_hits,                  render: p => p.qb_hits > 0 ? p.qb_hits : null },
  { key: 'int',  label: 'INT',  kind: 'trad',                  sortVal: p => p.def_interceptions,        render: p => p.def_interceptions > 0 ? p.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  kind: 'trad', dim: true,       sortVal: p => p.pass_breakups,            render: p => p.pass_breakups > 0 ? p.pass_breakups : null },
  { key: 'ff',   label: 'FF',   kind: 'trad',                  sortVal: p => p.forced_fumbles ?? 0,      render: p => (p.forced_fumbles ?? 0) > 0 ? p.forced_fumbles : null },
  { key: 'fr',   label: 'FR',   kind: 'trad', dim: true,       sortVal: p => p.fumble_recoveries ?? 0,   render: p => (p.fumble_recoveries ?? 0) > 0 ? p.fumble_recoveries : null },
]

type TabDef = {
  key: string
  label: string
  filter: (p: LeagueLeader) => boolean
  defaultSort: string
  cols: Col[]
}

const TABS: TabDef[] = [
  { key: 'passing',   label: 'Passing',   filter: p => p.attempts >= 100,                                    defaultSort: 'yds',  cols: PASSING_COLS },
  { key: 'rushing',   label: 'Rushing',   filter: p => p.carries >= 50,                                      defaultSort: 'yds',  cols: RUSHING_COLS },
  { key: 'receiving', label: 'Receiving', filter: p => p.targets >= 20,                                      defaultSort: 'yds',  cols: RECEIVING_COLS },
  { key: 'defense',   label: 'Defense',   filter: p => p.solo_tackles + p.assist_tackles >= 10,              defaultSort: 'tot',  cols: DEFENSE_COLS },
]

function RankBadge({ rank }: { rank: number }) {
  const cls = rank === 1 ? 'text-yellow-400 font-black' : rank === 2 ? 'text-gray-300 font-bold' : rank === 3 ? 'text-amber-600 font-bold' : 'text-gray-600 font-medium'
  return <span className={`text-sm tabular-nums ${cls}`}>{rank}</span>
}

function LeaderTable({ players, cols, sort, onSort }: {
  players: LeagueLeader[]
  cols: Col[]
  sort: { key: string; dir: SortDir }
  onSort: (key: string) => void
}) {
  const tradCount = cols.filter(c => c.kind === 'trad').length
  const advCount  = cols.filter(c => c.kind === 'adv').length

  const sorted = [...players].sort((a, b) => {
    const col = cols.find(c => c.key === sort.key)
    if (!col) return 0
    const diff = col.sortVal(b) - col.sortVal(a)
    return sort.dir === 'desc' ? diff : -diff
  })

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-right cursor-pointer select-none hover:text-white transition-colors'

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800/50">
            <th colSpan={4} />
            {tradCount > 0 && <th colSpan={tradCount} className="py-1 text-center text-[10px] font-semibold text-gray-600 uppercase tracking-widest border-l border-gray-800/40">Stats</th>}
            {advCount  > 0 && <th colSpan={advCount}  className="py-1 text-center text-[10px] font-semibold text-amber-500/60 uppercase tracking-widest bg-amber-950/20 border-l border-gray-800/40">Advanced</th>}
          </tr>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-gray-500 text-left">Player</th>
            <th className="py-2.5 px-2 text-xs font-semibold text-gray-500 text-left">Pos</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-500 text-left">Team</th>
            {cols.map((c, i) => {
              const active = sort.key === c.key
              const sep = i === 0 || cols[i - 1].kind !== c.kind
              return (
                <th
                  key={c.key}
                  onClick={() => onSort(c.key)}
                  className={`${thBase} ${sep ? 'border-l border-gray-800/40' : ''}
                    ${c.kind === 'adv'
                      ? 'bg-amber-950/10 text-amber-300/50 hover:text-amber-200'
                      : active ? 'text-white' : 'text-gray-500'}`}
                >
                  <span className="flex items-center justify-end gap-1">
                    {c.label}
                    <span className={`text-[10px] transition-opacity ${active ? 'opacity-100' : 'opacity-0'}`}>
                      {sort.dir === 'desc' ? '↓' : '↑'}
                    </span>
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => (
            <tr key={p.player_id} className="border-t border-gray-800/50 hover:bg-gray-800/30 transition-colors">
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  {p.headshot_url
                    ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                    : <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
                  }
                  <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{p.player_name}</Link>
                </div>
              </td>
              <td className="py-2.5 px-2 whitespace-nowrap">
                <span className="text-xs text-gray-500 font-medium">{p.position ?? '—'}</span>
              </td>
              <td className="py-2.5 px-3 whitespace-nowrap">
                {p.team
                  ? <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
                      <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                      <span className="text-xs text-gray-400 group-hover:text-white transition-colors font-medium">{p.team}</span>
                    </Link>
                  : <span className="text-gray-700 text-xs">—</span>
                }
              </td>
              {cols.map((c, i) => {
                const sep = i === 0 || cols[i - 1].kind !== c.kind
                const val = c.render(p)
                const isNull = val === null || val === undefined
                const str = isNull ? null : String(val)
                const isPos = !isNull && str!.startsWith('+')
                const isNeg = !isNull && str!.startsWith('-')
                return (
                  <td key={c.key} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap
                    ${sep ? 'border-l border-gray-800/30' : ''}
                    ${c.kind === 'adv' ? 'bg-amber-950/10' : ''}
                    ${isNull   ? 'text-gray-700'
                    : isPos    ? 'text-emerald-400 font-semibold'
                    : isNeg    ? 'text-red-400 font-semibold'
                    : c.highlight ? 'text-white font-bold'
                    : c.kind === 'adv' ? 'text-amber-200/80'
                    : c.dim    ? 'text-gray-500'
                    : 'text-gray-300'}`}>
                    {isNull ? '—' : str}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

type WpaSubTab = 'passing' | 'rushing' | 'receiving'

function WpaTable({ players, contextLabel }: { players: WpaLeader[]; contextLabel: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800/50">
            <th colSpan={4} />
            <th colSpan={1} className="py-1 text-center text-[10px] font-semibold text-violet-400/60 uppercase tracking-widest bg-violet-950/20 border-l border-gray-800/40">WPA</th>
            <th colSpan={2} className="py-1 text-center text-[10px] font-semibold text-gray-600 uppercase tracking-widest border-l border-gray-800/40">Context</th>
          </tr>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-gray-500 text-left">Player</th>
            <th className="py-2.5 px-2 text-xs font-semibold text-gray-500 text-left">Pos</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-500 text-left">Team</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-violet-400/50 text-right border-l border-gray-800/40 bg-violet-950/10">WPA</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-600 text-right border-l border-gray-800/40">G</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-600 text-right">{contextLabel}</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p, i) => {
            const wpaStr = `${p.wpa >= 0 ? '+' : ''}${p.wpa.toFixed(3)}`
            const isPos = p.wpa >= 0
            const ctx = p.attempts ?? p.carries ?? p.receptions ?? null
            return (
              <tr key={p.player_id} className="border-t border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                <td className="py-2.5 pl-4 pr-2 text-right">
                  <span className={`text-sm tabular-nums ${i === 0 ? 'text-yellow-400 font-black' : i === 1 ? 'text-gray-300 font-bold' : i === 2 ? 'text-amber-600 font-bold' : 'text-gray-600 font-medium'}`}>{i + 1}</span>
                </td>
                <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    {p.headshot_url
                      ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                      : <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
                    }
                    <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{p.player_name}</Link>
                  </div>
                </td>
                <td className="py-2.5 px-2 whitespace-nowrap">
                  <span className="text-xs text-gray-500 font-medium">{p.position ?? '—'}</span>
                </td>
                <td className="py-2.5 px-3 whitespace-nowrap">
                  {p.team
                    ? <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
                        <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                        <span className="text-xs text-gray-400 group-hover:text-white transition-colors font-medium">{p.team}</span>
                      </Link>
                    : <span className="text-gray-700 text-xs">—</span>
                  }
                </td>
                <td className={`py-2.5 px-3 text-right tabular-nums font-bold text-sm border-l border-gray-800/30 bg-violet-950/10 ${isPos ? 'text-emerald-400' : 'text-red-400'}`}>
                  {wpaStr}
                </td>
                <td className="py-2.5 px-3 text-right tabular-nums text-sm text-gray-600 border-l border-gray-800/30">{p.games_played}</td>
                <td className="py-2.5 px-3 text-right tabular-nums text-sm text-gray-500">{ctx ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function LeadersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [seasons, setSeasons] = useState<SeasonEntry[]>([])
  const [leaders, setLeaders] = useState<LeagueLeader[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState(0)
  const [wpaData, setWpaData] = useState<WpaLeaders | null>(null)
  const [wpaLoading, setWpaLoading] = useState(false)
  const [wpaSubTab, setWpaSubTab] = useState<WpaSubTab>('passing')
  const [sorts, setSorts] = useState<Record<string, { key: string; dir: SortDir }>>({
    passing:   { key: 'yds', dir: 'desc' },
    rushing:   { key: 'yds', dir: 'desc' },
    receiving: { key: 'yds', dir: 'desc' },
    defense:   { key: 'tot', dir: 'desc' },
  })

  const WPA_TAB_INDEX = TABS.length

  const season = Number(searchParams.get('season') ?? CURRENT_NFL_SEASON)
  const tab = TABS[activeTab] ?? TABS[0]

  useEffect(() => {
    api.seasons().then(all => setSeasons(all.filter(s => s.status === 'loaded')))
  }, [])

  useEffect(() => {
    setLoading(true)
    setLeaders([])
    api.leaders(season).then(setLeaders).finally(() => setLoading(false))
  }, [season])

  useEffect(() => {
    if (activeTab !== WPA_TAB_INDEX) return
    setWpaLoading(true)
    setWpaData(null)
    api.wpaLeaders(season).then(setWpaData).finally(() => setWpaLoading(false))
  }, [activeTab, season, WPA_TAB_INDEX])

  function handleSort(tabKey: string, colKey: string) {
    setSorts(prev => {
      const cur = prev[tabKey]
      return {
        ...prev,
        [tabKey]: cur.key === colKey
          ? { key: colKey, dir: cur.dir === 'desc' ? 'asc' : 'desc' }
          : { key: colKey, dir: 'desc' },
      }
    })
  }

  const filtered = leaders.filter(tab.filter)
  const sort = sorts[tab.key]

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">

        <div className="flex items-center gap-2 mb-6">
          <button onClick={() => navigate(`/?season=${CURRENT_NFL_SEASON}`)} className="font-black text-base tracking-tight shrink-0">
            <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
          </button>
          <span className="text-gray-700">/</span>
          <span className="text-gray-400 text-sm">League Leaders</span>
          <button onClick={() => navigate(-1)}
            className="ml-auto shrink-0 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-1.5 transition-colors"
          >
            ← Back
          </button>
        </div>

        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">League Leaders</h1>
            <p className="text-gray-500 text-sm mt-0.5">{season} NFL Season</p>
          </div>
          <select
            value={season}
            onChange={e => setSearchParams({ season: e.target.value })}
            className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500"
          >
            {seasons.map(s => (
              <option key={s.season} value={s.season}>{s.season}</option>
            ))}
          </select>
        </div>

        <div className="flex gap-1 mb-4 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit flex-wrap">
          {TABS.map((t, i) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(i)}
              className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors
                ${activeTab === i ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              {t.label}
            </button>
          ))}
          <button
            onClick={() => setActiveTab(WPA_TAB_INDEX)}
            className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors
              ${activeTab === WPA_TAB_INDEX ? 'bg-violet-700 text-white' : 'text-gray-400 hover:text-white'}`}
          >
            WPA
          </button>
        </div>

        {activeTab === WPA_TAB_INDEX ? (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
                {(['passing', 'rushing', 'receiving'] as WpaSubTab[]).map(s => (
                  <button
                    key={s}
                    onClick={() => setWpaSubTab(s)}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-colors
                      ${wpaSubTab === s ? 'bg-violet-700 text-white' : 'text-gray-400 hover:text-white'}`}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <span className="text-xs text-gray-600">
                {wpaSubTab === 'passing' ? 'Air WPA credited to passer (≥50 att)' :
                 wpaSubTab === 'rushing' ? 'WPA on rush plays (≥50 car)' :
                 'YAC WPA credited to receiver (≥20 rec)'}
              </span>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              {wpaLoading ? (
                <p className="p-8 text-gray-500 text-sm">Loading…</p>
              ) : !wpaData ? (
                <p className="p-8 text-gray-600 text-sm">No WPA data for {season}.</p>
              ) : (
                <WpaTable
                  players={wpaData[wpaSubTab]}
                  contextLabel={wpaSubTab === 'passing' ? 'ATT' : wpaSubTab === 'rushing' ? 'CAR' : 'REC'}
                />
              )}
            </div>
          </div>
        ) : (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            {loading ? (
              <p className="p-8 text-gray-500 text-sm">Loading…</p>
            ) : filtered.length === 0 ? (
              <p className="p-8 text-gray-600 text-sm">No data for {season}.</p>
            ) : (
              <LeaderTable
                players={filtered}
                cols={tab.cols}
                sort={sort}
                onSort={key => handleSort(tab.key, key)}
              />
            )}
          </div>
        )}

      </div>
    </div>
  )
}
