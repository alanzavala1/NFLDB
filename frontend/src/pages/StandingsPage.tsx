import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { DivisionStandings, SeasonEntry, StandingsTeam } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'

function DivisionCard({ division, teams }: { division: string; teams: StandingsTeam[] }) {
  const anyTies = teams.some(t => t.t > 0)
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{division}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-800/40">
              <th className="py-2 pl-4 pr-3 text-left text-xs font-medium text-gray-600 whitespace-nowrap">Team</th>
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-8">W</th>
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-8">L</th>
              {anyTies && <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-8">T</th>}
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-12">PCT</th>
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-8">GB</th>
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-10">PF</th>
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-10">PA</th>
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-14 hidden sm:table-cell">HOME</th>
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-14 hidden sm:table-cell">AWAY</th>
              <th className="py-2 px-2 text-center text-xs font-medium text-gray-600 w-14 hidden md:table-cell">DIV</th>
              <th className="py-2 pr-4 pl-2 text-center text-xs font-medium text-gray-600 w-12">STRK</th>
            </tr>
          </thead>
          <tbody>
            {teams.map((t, i) => {
              const leader = i === 0
              const streakCls = t.strk.startsWith('W') ? 'text-green-400 font-semibold' : t.strk.startsWith('L') ? 'text-red-400 font-semibold' : 'text-gray-500'
              const pctStr = t.pct === 1 ? '1.000' : t.pct === 0 ? '.000' : t.pct.toFixed(3).replace(/^0/, '')
              return (
                <tr key={t.team} className={`border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors ${leader ? 'bg-gray-800/20' : ''}`}>
                  <td className="py-2.5 pl-4 pr-3 whitespace-nowrap">
                    <Link to={`/teams/${t.team}`} className="flex items-center gap-2 group w-fit">
                      <img src={teamLogoUrl(t.team)} alt={t.team} className="w-5 h-5 object-contain shrink-0 opacity-70 group-hover:opacity-100 transition-opacity" />
                      <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">{t.team}</span>
                      {leader && <span className="text-[10px] font-bold text-indigo-400 leading-none">●</span>}
                    </Link>
                  </td>
                  <td className="py-2.5 px-2 text-center tabular-nums text-sm text-white font-semibold">{t.w}</td>
                  <td className="py-2.5 px-2 text-center tabular-nums text-sm text-gray-400">{t.l}</td>
                  {anyTies && <td className="py-2.5 px-2 text-center tabular-nums text-sm text-gray-600">{t.t || '—'}</td>}
                  <td className="py-2.5 px-2 text-center tabular-nums text-sm text-gray-300">{pctStr}</td>
                  <td className="py-2.5 px-2 text-center tabular-nums text-sm text-gray-500">{t.gb}</td>
                  <td className="py-2.5 px-2 text-center tabular-nums text-sm text-gray-400">{t.pf}</td>
                  <td className="py-2.5 px-2 text-center tabular-nums text-sm text-gray-400">{t.pa}</td>
                  <td className="py-2.5 px-2 text-center tabular-nums text-xs text-gray-500 hidden sm:table-cell">{t.home}</td>
                  <td className="py-2.5 px-2 text-center tabular-nums text-xs text-gray-500 hidden sm:table-cell">{t.away}</td>
                  <td className="py-2.5 px-2 text-center tabular-nums text-xs text-gray-500 hidden md:table-cell">{t.div}</td>
                  <td className={`py-2.5 pr-4 pl-2 text-center tabular-nums text-sm ${streakCls}`}>{t.strk}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ConferenceSection({ label, divisions }: { label: string; divisions: DivisionStandings[] }) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="text-sm font-bold text-indigo-400 uppercase tracking-widest">{label}</span>
        <div className="flex-1 h-px bg-gray-800" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-8">
        {divisions.map(d => (
          <DivisionCard key={d.division} division={d.division} teams={d.teams} />
        ))}
      </div>
    </div>
  )
}

export default function StandingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [seasons, setSeasons] = useState<SeasonEntry[]>([])
  const [standings, setStandings] = useState<DivisionStandings[]>([])
  const [loading, setLoading] = useState(true)

  const season = Number(searchParams.get('season') ?? CURRENT_NFL_SEASON)

  useEffect(() => {
    api.seasons().then(all => setSeasons(all.filter(s => s.status === 'loaded')))
  }, [])

  useEffect(() => {
    setLoading(true)
    setStandings([])
    api.standings(season).then(setStandings).finally(() => setLoading(false))
  }, [season])

  const afc = standings.filter(d => d.division.startsWith('AFC'))
  const nfc = standings.filter(d => d.division.startsWith('NFC'))

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">

        <div className="flex items-center gap-2 mb-6">
          <button onClick={() => navigate(`/?season=${CURRENT_NFL_SEASON}`)} className="font-black text-base tracking-tight shrink-0">
            <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
          </button>
          <span className="text-gray-700">/</span>
          <span className="text-gray-400 text-sm">Standings</span>
          <button onClick={() => navigate(-1)}
            className="ml-auto shrink-0 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-1.5 transition-colors"
          >
            ← Back
          </button>
        </div>

        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Standings</h1>
            <p className="text-gray-500 text-sm mt-0.5">{season} NFL Season</p>
          </div>
          <select
            value={season}
            onChange={e => setSearchParams({ season: e.target.value })}
            className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500 cursor-pointer hover:border-gray-500 transition-colors"
          >
            {seasons.map(s => (
              <option key={s.season} value={s.season}>{s.season}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <p className="text-gray-500 text-sm">Loading…</p>
        ) : standings.length === 0 ? (
          <p className="text-gray-600 text-sm">No data for {season}.</p>
        ) : (
          <>
            <ConferenceSection label="AFC" divisions={afc} />
            <ConferenceSection label="NFC" divisions={nfc} />
          </>
        )}

      </div>
    </div>
  )
}
