import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { LeagueLeader, SeasonEntry } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl } from '../utils/teams'

function pct(a: number, b: number) { return b > 0 ? (a / b * 100).toFixed(1) : null }
function ratio(y: number, a: number, d = 1) { return a > 0 ? (y / a).toFixed(d) : null }
function sfmt(x: number) { return `${x >= 0 ? '+' : ''}${x.toFixed(3)}` }

function passerRating(cmp: number, att: number, yds: number, td: number, int_: number) {
  if (att === 0) return null
  const clamp = (x: number) => Math.min(2.375, Math.max(0, x))
  const a = clamp((cmp / att - 0.3) / 0.2)
  const b = clamp((yds / att - 3) / 4)
  const c = clamp((td / att) / 0.05)
  const d = clamp(2.375 - (int_ / att) / 0.04)
  return ((a + b + c + d) / 6) * 100
}

type SortDir = 'asc' | 'desc'

type Col = {
  key: string
  label: string
  desc: string
  highlight?: boolean
  dim?: boolean
  sortVal: (p: LeagueLeader) => number
  render: (p: LeagueLeader) => string | number | null
}

const QB_COLS: Col[] = [
  { key: 'g',    label: 'G',     desc: 'Games played',        dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'catt', label: 'C/ATT', desc: 'Completions/Attempts',                 sortVal: p => p.completions,    render: p => `${p.completions}/${p.attempts}` },
  { key: 'cpct', label: 'CMP%',  desc: 'Completion %',        dim: true,       sortVal: p => p.attempts ? p.completions / p.attempts : 0, render: p => pct(p.completions, p.attempts) },
  { key: 'yds',  label: 'YDS',   desc: 'Passing yards',       highlight: true, sortVal: p => p.pass_yards,     render: p => p.pass_yards.toLocaleString() },
  { key: 'ya',   label: 'Y/A',   desc: 'Yards per attempt',   dim: true,       sortVal: p => p.attempts ? p.pass_yards / p.attempts : 0, render: p => ratio(p.pass_yards, p.attempts) },
  { key: 'td',   label: 'TD',    desc: 'Passing touchdowns',                   sortVal: p => p.pass_tds,       render: p => p.pass_tds },
  { key: 'int',  label: 'INT',   desc: 'Interceptions',                        sortVal: p => p.interceptions_thrown, render: p => p.interceptions_thrown },
  { key: 'rate', label: 'RATE',  desc: 'Passer rating',                        sortVal: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown) ?? 0, render: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown)?.toFixed(1) ?? null },
  { key: 'epaa', label: 'EPA/A', desc: 'EPA per attempt',     dim: true,       sortVal: p => p.attempts > 0 && p.pass_epa != null ? p.pass_epa / p.attempts : 0, render: p => p.attempts > 0 && p.pass_epa != null ? sfmt(p.pass_epa / p.attempts) : null },
]

const RB_COLS: Col[] = [
  { key: 'g',    label: 'G',     desc: 'Games played',        dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'car',  label: 'CAR',   desc: 'Carries',                              sortVal: p => p.carries,        render: p => p.carries },
  { key: 'yds',  label: 'YDS',   desc: 'Rushing yards',       highlight: true, sortVal: p => p.rush_yards,     render: p => p.rush_yards.toLocaleString() },
  { key: 'ypc',  label: 'Y/C',   desc: 'Yards per carry',     dim: true,       sortVal: p => p.carries ? p.rush_yards / p.carries : 0, render: p => ratio(p.rush_yards, p.carries) },
  { key: 'td',   label: 'TD',    desc: 'Rushing touchdowns',                   sortVal: p => p.rush_tds,       render: p => p.rush_tds },
  { key: 'ypg',  label: 'Y/G',   desc: 'Rushing yards per game', dim: true,    sortVal: p => p.games_played ? p.rush_yards / p.games_played : 0, render: p => ratio(p.rush_yards, p.games_played) },
  { key: 'rec',  label: 'REC',   desc: 'Receptions',          dim: true,       sortVal: p => p.receptions,     render: p => p.receptions > 0 ? p.receptions : null },
  { key: 'ryds', label: 'REC YDS', desc: 'Receiving yards',                    sortVal: p => p.rec_yards,      render: p => p.rec_yards > 0 ? p.rec_yards.toLocaleString() : null },
  { key: 'epac', label: 'EPA/C', desc: 'EPA per carry',       dim: true,       sortVal: p => p.carries > 0 && p.rush_epa != null ? p.rush_epa / p.carries : 0, render: p => p.carries > 0 && p.rush_epa != null ? sfmt(p.rush_epa / p.carries) : null },
]

const REC_COLS: Col[] = [
  { key: 'g',    label: 'G',     desc: 'Games played',        dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'tgt',  label: 'TGT',   desc: 'Targets',             dim: true,       sortVal: p => p.targets,        render: p => p.targets },
  { key: 'rec',  label: 'REC',   desc: 'Receptions',                           sortVal: p => p.receptions,     render: p => p.receptions },
  { key: 'yds',  label: 'YDS',   desc: 'Receiving yards',     highlight: true, sortVal: p => p.rec_yards,      render: p => p.rec_yards.toLocaleString() },
  { key: 'ypr',  label: 'Y/R',   desc: 'Yards per reception', dim: true,       sortVal: p => p.receptions ? p.rec_yards / p.receptions : 0, render: p => ratio(p.rec_yards, p.receptions) },
  { key: 'td',   label: 'TD',    desc: 'Receiving touchdowns',                 sortVal: p => p.rec_tds,        render: p => p.rec_tds },
  { key: 'cth',  label: 'CTH%',  desc: 'Catch rate',          dim: true,       sortVal: p => p.targets ? p.receptions / p.targets : 0, render: p => pct(p.receptions, p.targets) },
  { key: 'ypg',  label: 'Y/G',   desc: 'Yards per game',      dim: true,       sortVal: p => p.games_played ? p.rec_yards / p.games_played : 0, render: p => ratio(p.rec_yards, p.games_played) },
  { key: 'epat', label: 'EPA/T', desc: 'EPA per target',      dim: true,       sortVal: p => p.targets > 0 && p.rec_epa != null ? p.rec_epa / p.targets : 0, render: p => p.targets > 0 && p.rec_epa != null ? sfmt(p.rec_epa / p.targets) : null },
]

const K_COLS: Col[] = [
  { key: 'g',    label: 'G',    desc: 'Games played',   dim: true,       sortVal: p => p.games_played,  render: p => p.games_played },
  { key: 'fg',   label: 'FG',   desc: 'Field goals made/att', highlight: true, sortVal: p => p.fg_made, render: p => p.fg_att > 0 ? `${p.fg_made}/${p.fg_att}` : null },
  { key: 'fgp',  label: 'FG%',  desc: 'FG make rate',                    sortVal: p => p.fg_att ? p.fg_made / p.fg_att : 0, render: p => pct(p.fg_made, p.fg_att) },
  { key: 'xp',   label: 'XP',   desc: 'Extra points made/att', dim: true, sortVal: p => p.xp_made,     render: p => p.xp_att > 0 ? `${p.xp_made}/${p.xp_att}` : null },
  { key: 'xpp',  label: 'XP%',  desc: 'XP make rate',   dim: true,       sortVal: p => p.xp_att ? p.xp_made / p.xp_att : 0, render: p => pct(p.xp_made, p.xp_att) },
  { key: 'pts',  label: 'PTS',  desc: 'Points scored',                   sortVal: p => p.fg_made * 3 + p.xp_made, render: p => (p.fg_made * 3 + p.xp_made) || null },
]

const DEF_COLS: Col[] = [
  { key: 'g',    label: 'G',    desc: 'Games played',          dim: true,       sortVal: p => p.games_played,          render: p => p.games_played },
  { key: 'tot',  label: 'TOT',  desc: 'Total tackles',         highlight: true, sortVal: p => p.solo_tackles + p.assist_tackles, render: p => p.solo_tackles + p.assist_tackles },
  { key: 'solo', label: 'SOLO', desc: 'Solo tackles',                           sortVal: p => p.solo_tackles,          render: p => p.solo_tackles },
  { key: 'ast',  label: 'AST',  desc: 'Assisted tackles',      dim: true,       sortVal: p => p.assist_tackles,        render: p => p.assist_tackles },
  { key: 'tfl',  label: 'TFL',  desc: 'Tackles for loss',                       sortVal: p => p.tackles_for_loss,      render: p => p.tackles_for_loss > 0 ? p.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', desc: 'Sacks',                                  sortVal: p => p.sacks,                 render: p => p.sacks > 0 ? p.sacks : null },
  { key: 'int',  label: 'INT',  desc: 'Interceptions',                          sortVal: p => p.def_interceptions,     render: p => p.def_interceptions > 0 ? p.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  desc: 'Pass breakups',         dim: true,       sortVal: p => p.pass_breakups,         render: p => p.pass_breakups > 0 ? p.pass_breakups : null },
  { key: 'ff',   label: 'FF',   desc: 'Forced fumbles',        dim: true,       sortVal: p => p.forced_fumbles ?? 0,   render: p => (p.forced_fumbles ?? 0) > 0 ? p.forced_fumbles : null },
]

const DEF_POS = new Set(['LB', 'ILB', 'OLB', 'MLB', 'EDGE', 'DE', 'DT', 'NT', 'DL', 'CB', 'S', 'SS', 'FS', 'DB', 'SAF'])

type PosTab = {
  key: string
  label: string
  filter: (p: LeagueLeader) => boolean
  defaultSort: string
  cols: Col[]
}

const POS_TABS: PosTab[] = [
  { key: 'qb',  label: 'QB',      filter: p => p.position === 'QB' && p.attempts >= 1,              defaultSort: 'yds',  cols: QB_COLS },
  { key: 'rb',  label: 'RB',      filter: p => p.position === 'RB' && p.carries >= 1,               defaultSort: 'yds',  cols: RB_COLS },
  { key: 'wr',  label: 'WR',      filter: p => p.position === 'WR' && p.targets >= 1,               defaultSort: 'yds',  cols: REC_COLS },
  { key: 'te',  label: 'TE',      filter: p => p.position === 'TE' && p.targets >= 1,               defaultSort: 'yds',  cols: REC_COLS },
  { key: 'k',   label: 'K',       filter: p => p.position === 'K' && (p.fg_att + p.xp_att) >= 1,   defaultSort: 'pts',  cols: K_COLS },
  { key: 'def', label: 'Defense', filter: p => DEF_POS.has(p.position ?? '') && (p.solo_tackles + p.assist_tackles) >= 1, defaultSort: 'tot', cols: DEF_COLS },
]

function RankBadge({ rank }: { rank: number }) {
  const cls =
    rank === 1 ? 'text-yellow-400 font-black' :
    rank === 2 ? 'text-gray-300 font-bold' :
    rank === 3 ? 'text-amber-600 font-bold' :
    'text-gray-600 font-medium'
  return <span className={`text-sm tabular-nums ${cls}`}>{rank}</span>
}

function PlayerTable({ players, cols, sortKey, sortDir, onSort }: {
  players: LeagueLeader[]
  cols: Col[]
  sortKey: string
  sortDir: SortDir
  onSort: (key: string) => void
}) {
  const sorted = [...players].sort((a, b) => {
    const col = cols.find(c => c.key === sortKey)
    if (!col) return 0
    const diff = col.sortVal(b) - col.sortVal(a)
    return sortDir === 'desc' ? diff : -diff
  })

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-right cursor-pointer select-none hover:text-white transition-colors'

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-gray-500 text-left min-w-[160px]">Player</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-500 text-left">Team</th>
            {cols.map(c => {
              const active = sortKey === c.key
              return (
                <th
                  key={c.key}
                  onClick={() => onSort(c.key)}
                  title={c.desc}
                  className={`${thBase} ${active ? 'text-white' : c.dim ? 'text-gray-600' : 'text-gray-500'}`}
                >
                  <span className="flex items-center justify-end gap-1">
                    {c.label}
                    <span className={`text-[10px] transition-opacity ${active ? 'opacity-100' : 'opacity-0'}`}>
                      {sortDir === 'desc' ? '↓' : '↑'}
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
                  <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold leading-tight">{p.player_name}</Link>
                </div>
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
              {cols.map(c => {
                const val = c.render(p)
                const isNull = val === null || val === undefined
                const str = isNull ? null : String(val)
                const isPos = !isNull && str!.startsWith('+')
                const isNeg = !isNull && str!.startsWith('-')
                return (
                  <td key={c.key} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap
                    ${isNull   ? 'text-gray-700'
                    : isPos    ? 'text-emerald-400 font-semibold'
                    : isNeg    ? 'text-red-400 font-semibold'
                    : c.highlight ? 'text-white font-bold'
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

export default function PlayersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [seasons, setSeasons] = useState<SeasonEntry[]>([])
  const [leaders, setLeaders] = useState<LeagueLeader[]>([])
  const [loading, setLoading] = useState(true)

  const season = Number(searchParams.get('season') ?? CURRENT_NFL_SEASON)
  const posKey = searchParams.get('pos') ?? 'qb'
  const tabIdx = Math.max(0, POS_TABS.findIndex(t => t.key === posKey))
  const tab = POS_TABS[tabIdx]

  const [sorts, setSorts] = useState<Record<string, { key: string; dir: SortDir }>>(() =>
    Object.fromEntries(POS_TABS.map(t => [t.key, { key: t.defaultSort, dir: 'desc' as SortDir }]))
  )

  useEffect(() => {
    api.seasons().then(all => setSeasons(all.filter(s => s.status === 'loaded')))
  }, [])

  useEffect(() => {
    setLoading(true)
    setLeaders([])
    api.leaders(season).then(setLeaders).finally(() => setLoading(false))
  }, [season])

  function setTab(key: string) {
    setSearchParams(p => { p.set('pos', key); return p })
  }

  function handleSort(colKey: string) {
    setSorts(prev => {
      const cur = prev[tab.key]
      return {
        ...prev,
        [tab.key]: cur.key === colKey
          ? { key: colKey, dir: cur.dir === 'desc' ? 'asc' : 'desc' }
          : { key: colKey, dir: 'desc' },
      }
    })
  }

  const filtered = leaders.filter(tab.filter)
  const sort = sorts[tab.key]

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav title="Players" />
      <div className="max-w-6xl mx-auto px-4 py-8">

        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-white">Players</h1>
            <p className="text-gray-500 text-sm mt-0.5">{season} NFL Season · ranked by position</p>
          </div>
          <select
            value={season}
            onChange={e => setSearchParams(p => { p.set('season', e.target.value); return p })}
            className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500"
          >
            {seasons.map(s => (
              <option key={s.season} value={s.season}>{s.season}</option>
            ))}
          </select>
        </div>

        <div className="flex gap-1 mb-4 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit flex-wrap">
          {POS_TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors
                ${tab.key === t.key ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          {loading ? (
            <p className="p-8 text-gray-500 text-sm">Loading…</p>
          ) : filtered.length === 0 ? (
            <p className="p-8 text-gray-600 text-sm">No {tab.label} data for {season}.</p>
          ) : (
            <PlayerTable
              players={filtered}
              cols={tab.cols}
              sortKey={sort.key}
              sortDir={sort.dir}
              onSort={handleSort}
            />
          )}
        </div>

      </div>
    </div>
  )
}
