import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { LeagueLeader, SeasonEntry } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl } from '../utils/teams'

type Tab = 'passing' | 'rushing' | 'receiving' | 'defense'

function pct(a: number, b: number) { return b > 0 ? (a / b * 100).toFixed(1) : '—' }
function avg(y: number, a: number) { return a > 0 ? (y / a).toFixed(1) : '—' }
function sv(n: number) { return n === 0 ? '—' : String(n) }

function RankBadge({ rank }: { rank: number }) {
  const gold = rank === 1 ? 'text-yellow-400 font-black' : rank === 2 ? 'text-gray-300 font-bold' : rank === 3 ? 'text-amber-600 font-bold' : 'text-gray-600 font-medium'
  return <span className={`text-sm tabular-nums w-6 text-right shrink-0 ${gold}`}>{rank}</span>
}

function PlayerCell({ p }: { p: LeagueLeader }) {
  return (
    <td className="py-2.5 pl-4 pr-3 whitespace-nowrap">
      <div className="flex items-center gap-2.5">
        {p.headshot_url
          ? <img src={p.headshot_url} className="w-8 h-8 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
          : <div className="w-8 h-8 rounded-full bg-gray-800 shrink-0" />
        }
        <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">
          {p.player_name}
        </Link>
      </div>
    </td>
  )
}

function TeamCell({ p }: { p: LeagueLeader }) {
  if (!p.team) return <td className="py-2.5 px-3 text-gray-600 text-xs">—</td>
  return (
    <td className="py-2.5 px-3">
      <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
        <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
        <span className="text-xs text-gray-400 group-hover:text-white transition-colors font-medium">{p.team}</span>
      </Link>
    </td>
  )
}

function Th({ children, right = true }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th className={`py-2.5 px-3 text-xs font-semibold text-gray-500 whitespace-nowrap ${right ? 'text-right' : 'text-left'}`}>
      {children}
    </th>
  )
}

function Td({ val, highlight = false, dim = false }: { val: string | number; highlight?: boolean; dim?: boolean }) {
  const isEmpty = val === '—' || val === 0 || val === '0'
  return (
    <td className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap
      ${isEmpty ? 'text-gray-700' : highlight ? 'text-white font-bold' : dim ? 'text-gray-500' : 'text-gray-300'}`}>
      {isEmpty ? '—' : val}
    </td>
  )
}

const rowCls = 'border-t border-gray-800/50 hover:bg-gray-800/30 transition-colors'

function PassingTable({ players }: { players: LeagueLeader[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <Th right={false}>Player</Th>
            <Th right={false}>Team</Th>
            <Th>G</Th>
            <Th>C/ATT</Th>
            <Th>CMP%</Th>
            <Th>YDS</Th>
            <Th>Y/A</Th>
            <Th>TD</Th>
            <Th>INT</Th>
            <Th>SCK</Th>
          </tr>
        </thead>
        <tbody>
          {players.map((p, i) => (
            <tr key={p.player_id} className={rowCls}>
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <PlayerCell p={p} />
              <TeamCell p={p} />
              <Td val={p.games_played} dim />
              <Td val={`${p.completions}/${p.attempts}`} />
              <Td val={pct(p.completions, p.attempts)} dim />
              <Td val={p.pass_yards} highlight />
              <Td val={avg(p.pass_yards, p.attempts)} dim />
              <Td val={p.pass_tds} />
              <Td val={p.interceptions_thrown} />
              <Td val={p.sacks_taken} dim />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RushingTable({ players }: { players: LeagueLeader[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <Th right={false}>Player</Th>
            <Th right={false}>Team</Th>
            <Th>G</Th>
            <Th>CAR</Th>
            <Th>YDS</Th>
            <Th>Y/C</Th>
            <Th>TD</Th>
            <Th>YDS/G</Th>
          </tr>
        </thead>
        <tbody>
          {players.map((p, i) => (
            <tr key={p.player_id} className={rowCls}>
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <PlayerCell p={p} />
              <TeamCell p={p} />
              <Td val={p.games_played} dim />
              <Td val={p.carries} />
              <Td val={p.rush_yards} highlight />
              <Td val={avg(p.rush_yards, p.carries)} dim />
              <Td val={p.rush_tds} />
              <Td val={avg(p.rush_yards, p.games_played)} dim />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ReceivingTable({ players }: { players: LeagueLeader[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <Th right={false}>Player</Th>
            <Th right={false}>Team</Th>
            <Th>G</Th>
            <Th>TGT</Th>
            <Th>REC</Th>
            <Th>YDS</Th>
            <Th>Y/R</Th>
            <Th>TD</Th>
            <Th>CTH%</Th>
            <Th>YAC</Th>
          </tr>
        </thead>
        <tbody>
          {players.map((p, i) => (
            <tr key={p.player_id} className={rowCls}>
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <PlayerCell p={p} />
              <TeamCell p={p} />
              <Td val={p.games_played} dim />
              <Td val={p.targets} dim />
              <Td val={p.receptions} />
              <Td val={p.rec_yards} highlight />
              <Td val={avg(p.rec_yards, p.receptions)} dim />
              <Td val={p.rec_tds} />
              <Td val={pct(p.receptions, p.targets)} dim />
              <Td val={sv(p.yac)} dim />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DefenseTable({ players }: { players: LeagueLeader[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <Th right={false}>Player</Th>
            <Th right={false}>Team</Th>
            <Th>G</Th>
            <Th>TOT</Th>
            <Th>SOLO</Th>
            <Th>AST</Th>
            <Th>TFL</Th>
            <Th>SACK</Th>
            <Th>INT</Th>
            <Th>PBU</Th>
          </tr>
        </thead>
        <tbody>
          {players.map((p, i) => (
            <tr key={p.player_id} className={rowCls}>
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <PlayerCell p={p} />
              <TeamCell p={p} />
              <Td val={p.games_played} dim />
              <Td val={p.solo_tackles + p.assist_tackles} highlight />
              <Td val={p.solo_tackles} />
              <Td val={p.assist_tackles} dim />
              <Td val={p.tackles_for_loss} dim />
              <Td val={sv(p.sacks)} />
              <Td val={p.def_interceptions} />
              <Td val={p.pass_breakups} dim />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const TABS: { key: Tab; label: string }[] = [
  { key: 'passing',   label: 'Passing' },
  { key: 'rushing',   label: 'Rushing' },
  { key: 'receiving', label: 'Receiving' },
  { key: 'defense',   label: 'Defense' },
]

export default function LeadersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [seasons, setSeasons] = useState<SeasonEntry[]>([])
  const [leaders, setLeaders] = useState<LeagueLeader[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('passing')

  const season = Number(searchParams.get('season') ?? CURRENT_NFL_SEASON)

  useEffect(() => {
    api.seasons().then(all => setSeasons(all.filter(s => s.status === 'loaded')))
  }, [])

  useEffect(() => {
    setLoading(true)
    setLeaders([])
    api.leaders(season).then(setLeaders).finally(() => setLoading(false))
  }, [season])

  const passers   = leaders.filter(p => p.attempts >= 100).sort((a, b) => b.pass_yards - a.pass_yards).slice(0, 30)
  const rushers   = leaders.filter(p => p.carries >= 50).sort((a, b) => b.rush_yards - a.rush_yards).slice(0, 30)
  const receivers = leaders.filter(p => p.targets >= 20).sort((a, b) => b.rec_yards - a.rec_yards).slice(0, 30)
  const defenders = leaders
    .filter(p => p.solo_tackles + p.assist_tackles >= 10)
    .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles))
    .slice(0, 30)

  const activeList = tab === 'passing' ? passers : tab === 'rushing' ? rushers : tab === 'receiving' ? receivers : defenders

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">

        {/* Header */}
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

        {/* Tabs */}
        <div className="flex gap-1 mb-4 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors
                ${tab === t.key ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          {loading ? (
            <p className="p-8 text-gray-500 text-sm">Loading…</p>
          ) : activeList.length === 0 ? (
            <p className="p-8 text-gray-600 text-sm">No data for {season}.</p>
          ) : tab === 'passing' ? <PassingTable players={passers} />
            : tab === 'rushing' ? <RushingTable players={rushers} />
            : tab === 'receiving' ? <ReceivingTable players={receivers} />
            : <DefenseTable players={defenders} />
          }
        </div>

      </div>
    </div>
  )
}
