import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { DivisionStandings, SeasonEntry, StandingsTeam } from '../api'
import Nav from '../components/Nav'
import Card from '../components/Card'
import { teamLogoUrl } from '../utils/teams'
import { PlayoffBracket } from '../components/PlayoffBracket'

// ── Standings ───────────────────────────────────────────────────────────────

function DivisionCard({ division, teams }: { division: string; teams: StandingsTeam[] }) {
  const anyTies = teams.some(t => t.t > 0)
  const leaderBorder = 'border-l-data-win'
  return (
    <Card title={division}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-line/60 bg-surface-raise/20">
              <th className="py-2 pl-4 pr-3 text-left text-[11px] font-medium text-ink-dim whitespace-nowrap">Team</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-9">W</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-9">L</th>
              {anyTies && <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-9">T</th>}
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-12">PCT</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-9">GB</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-10">PF</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-10">PA</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-12">DIFF</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-14 hidden sm:table-cell">HOME</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-14 hidden sm:table-cell">AWAY</th>
              <th className="py-2 px-1.5 text-center text-[11px] font-medium text-ink-dim w-14 hidden md:table-cell">DIV</th>
              <th className="py-2 pr-4 pl-1.5 text-center text-[11px] font-medium text-ink-dim w-12">STRK</th>
            </tr>
          </thead>
          <tbody>
            {teams.map((t, i) => {
              const leader = i === 0
              const streakCls = t.strk.startsWith('W') ? 'text-data-win font-semibold' : t.strk.startsWith('L') ? 'text-rose-400 font-semibold' : 'text-ink-dim'
              const pctStr = t.pct === 1 ? '1.000' : t.pct === 0 ? '.000' : t.pct.toFixed(3).replace(/^0/, '')
              const diff = t.pf - t.pa
              const diffCls = diff > 0 ? 'text-data-win font-semibold' : diff < 0 ? 'text-rose-400 font-semibold' : 'text-ink-dim'
              return (
                <tr key={t.team} className={`border-t border-surface-line/60 hover:bg-surface-raise/30 transition-colors ${leader ? `border-l-2 ${leaderBorder}` : 'border-l-2 border-l-transparent'}`}>
                  <td className="py-2.5 pl-3 pr-3 whitespace-nowrap">
                    <Link to={`/teams/${t.team}`} className="flex items-center gap-2 group w-fit">
                      <img src={teamLogoUrl(t.team)} alt={t.team} className="w-5 h-5 object-contain shrink-0 opacity-90 group-hover:opacity-100 transition-opacity" />
                      <span className={`text-sm font-semibold transition-colors ${leader ? 'text-ink' : 'text-ink-mid'} group-hover:text-ink`}>{t.team}</span>
                    </Link>
                  </td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-ink font-bold">{t.w}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-ink-mid">{t.l}</td>
                  {anyTies && <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-ink-dim">{t.t || '—'}</td>}
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-ink">{pctStr}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-ink-dim">{t.gb}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-ink-mid">{t.pf}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-sm text-ink-mid">{t.pa}</td>
                  <td className={`py-2.5 px-1.5 text-center tabular-nums text-sm ${diffCls}`}>
                    {diff > 0 ? '+' : ''}{diff}
                  </td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-xs text-ink-dim hidden sm:table-cell">{t.home}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-xs text-ink-dim hidden sm:table-cell">{t.away}</td>
                  <td className="py-2.5 px-1.5 text-center tabular-nums text-xs text-ink-dim hidden md:table-cell">{t.div}</td>
                  <td className={`py-2.5 pr-4 pl-1.5 text-center tabular-nums text-sm ${streakCls}`}>{t.strk}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function ConferenceSection({ divisions }: { divisions: DivisionStandings[] }) {
  return (
    <div className="mb-4">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {divisions.map(d => (
          <DivisionCard key={d.division} division={d.division} teams={d.teams} />
        ))}
      </div>
    </div>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

export default function StandingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
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
    <div className="min-h-screen bg-surface-bg">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <Card title="Standings" className="mb-5"><div className="flex items-center justify-between gap-4 border-t border-surface-line px-4 py-3">
            <p className="text-ink-dim text-[10px] uppercase tracking-widest font-bold">{season} NFL Season</p>
          <select
            value={season}
            onChange={e => setSearchParams({ season: e.target.value })}
            className="bg-surface-raise border border-surface-line text-ink text-sm font-semibold rounded-lg px-4 py-2.5 focus:outline-none focus:border-indigo-500 cursor-pointer hover:border-surface-line transition-colors"
          >
            {seasons.map(s => (
              <option key={s.season} value={s.season}>{s.season}</option>
            ))}
          </select>
        </div></Card>

        {loading ? (
          <p className="text-ink-dim text-sm">Loading…</p>
        ) : standings.length === 0 ? (
          <p className="text-ink-dim text-sm">No data for {season}.</p>
        ) : (
          <>
            <PlayoffBracket season={season} />
            <ConferenceSection divisions={afc} />
            <ConferenceSection divisions={nfc} />
          </>
        )}

      </div>
    </div>
  )
}
