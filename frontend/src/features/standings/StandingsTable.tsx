import { Link } from 'react-router-dom'
import type { DivisionStandings, StandingsRow } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl } from '../../utils/teams'

function DivisionCard({ division, teams }: { division: string; teams: StandingsRow[] }) {
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
              const streakCls = t.strk.startsWith('W') ? 'text-data-win font-semibold' : t.strk.startsWith('L') ? 'text-data-loss font-semibold' : 'text-ink-dim'
              const pctStr = t.pct === 1 ? '1.000' : t.pct === 0 ? '.000' : t.pct.toFixed(3).replace(/^0/, '')
              const diff = t.pf - t.pa
              const diffCls = diff > 0 ? 'text-data-win font-semibold' : diff < 0 ? 'text-data-loss font-semibold' : 'text-ink-dim'
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

export function ConferenceSection({ divisions }: { divisions: DivisionStandings[] }) {
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
