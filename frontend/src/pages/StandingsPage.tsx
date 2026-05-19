import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { DivisionStandings, SeasonEntry, StandingsTeam } from '../api'
import Nav, { backBtnCls } from '../components/Nav'
import { teamLogoUrl } from '../utils/teams'
import { PlayoffBracket, CONF_STYLE, type ConfKey } from '../components/PlayoffBracket'

// ── Standings ───────────────────────────────────────────────────────────────

function DivisionCard({ division, teams, conf }: { division: string; teams: StandingsTeam[]; conf: ConfKey }) {
  const anyTies = teams.some(t => t.t > 0)
  const style = CONF_STYLE[conf]
  const leaderBorder = conf === 'AFC' ? 'border-l-rose-500' : 'border-l-indigo-500'
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-800 bg-gray-800/40 flex items-center gap-2">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${style.dot}`} />
        <span className="text-sm font-bold text-white uppercase tracking-wider">{division.replace(/^(AFC|NFC)\s*/, '')}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800/60 bg-gray-800/20">
              <th className="py-2 pl-4 pr-3 text-left text-[11px] font-medium text-gray-600 whitespace-nowrap">Team</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-9">W</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-9">L</th>
              {anyTies && <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-9">T</th>}
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-12">PCT</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-9">GB</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-10">PF</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-10">PA</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-12">DIFF</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-14 hidden sm:table-cell">HOME</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-14 hidden sm:table-cell">AWAY</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-gray-600 w-14 hidden md:table-cell">DIV</th>
              <th className="py-2 pr-4 pl-1.5 text-center text-[11px] font-medium text-gray-600 w-12">STRK</th>
            </tr>
          </thead>
          <tbody>
            {teams.map((t, i) => {
              const leader = i === 0
              const streakCls = t.strk.startsWith('W') ? 'text-emerald-400 font-semibold' : t.strk.startsWith('L') ? 'text-rose-400 font-semibold' : 'text-gray-500'
              const pctStr = t.pct === 1 ? '1.000' : t.pct === 0 ? '.000' : t.pct.toFixed(3).replace(/^0/, '')
              const diff = t.pf - t.pa
              const diffCls = diff > 0 ? 'text-emerald-400 font-semibold' : diff < 0 ? 'text-rose-400 font-semibold' : 'text-gray-500'
              return (
                <tr key={t.team} className={`border-t border-gray-800/60 hover:bg-gray-800/30 transition-colors ${leader ? `border-l-2 ${leaderBorder}` : 'border-l-2 border-l-transparent'}`}>
                  <td className="py-2.5 pl-3 pr-3 whitespace-nowrap">
                    <Link to={`/teams/${t.team}`} className="flex items-center gap-2 group w-fit">
                      <img src={teamLogoUrl(t.team)} alt={t.team} className="w-5 h-5 object-contain shrink-0 opacity-90 group-hover:opacity-100 transition-opacity" />
                      <span className={`text-sm font-semibold transition-colors ${leader ? 'text-white' : 'text-gray-300'} group-hover:text-white`}>{t.team}</span>
                    </Link>
                  </td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-white font-bold">{t.w}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-gray-400">{t.l}</td>
                  {anyTies && <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-gray-600">{t.t || '—'}</td>}
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-gray-200">{pctStr}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-gray-500">{t.gb}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-gray-400">{t.pf}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-gray-400">{t.pa}</td>
                  <td className={`py-2.5 px-1.5 text-center tabular-nums text-sm ${diffCls}`}>
                    {diff > 0 ? '+' : ''}{diff}
                  </td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-xs text-gray-500 hidden sm:table-cell">{t.home}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-xs text-gray-500 hidden sm:table-cell">{t.away}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-xs text-gray-500 hidden md:table-cell">{t.div}</td>
                  <td className={`py-2.5 pr-4 pl-1.5 text-center tabular-nums text-sm ${streakCls}`}>{t.strk}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ConferenceSection({ conf, divisions }: { conf: ConfKey; divisions: DivisionStandings[] }) {
  const style = CONF_STYLE[conf]
  return (
    <div className="mb-10">
      <div className="flex items-center gap-3 mb-5">
        <span className={`inline-block w-2 h-7 rounded ${style.dot}`} />
        <h2 className={`text-2xl font-black tracking-tight ${style.text}`}>{conf}</h2>
        <div className="flex-1 h-px bg-gray-800" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {divisions.map(d => (
          <DivisionCard key={d.division} division={d.division} teams={d.teams} conf={conf} />
        ))}
      </div>
    </div>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

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
      <Nav title="Standings" />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <button onClick={() => navigate(-1)} className={`${backBtnCls} mb-6`}>← Back</button>

        <div className="flex items-end justify-between mb-10 gap-4 flex-wrap">
          <div>
            <h1 className="text-4xl font-black text-white tracking-tight leading-none">Standings</h1>
            <p className="text-gray-500 text-sm mt-2 uppercase tracking-widest font-medium">{season} NFL Season</p>
          </div>
          <select
            value={season}
            onChange={e => setSearchParams({ season: e.target.value })}
            className="bg-gray-800 border border-gray-700 text-white text-sm font-semibold rounded-lg px-4 py-2.5 focus:outline-none focus:border-indigo-500 cursor-pointer hover:border-gray-500 transition-colors"
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
            <PlayoffBracket season={season} />
            <ConferenceSection conf="AFC" divisions={afc} />
            <ConferenceSection conf="NFC" divisions={nfc} />
          </>
        )}

      </div>
    </div>
  )
}
