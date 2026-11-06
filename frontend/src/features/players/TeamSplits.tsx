import { Link } from 'react-router-dom'
import type { PlayerGame } from '../../types'
import { teamLogoUrl } from '../../utils/teams'
import { sumGames, detectPos } from './stats'
import { QB_COLS, RB_COLS, WR_COLS, DEF_COLS, K_COLS, P_COLS, OL_COLS } from './careerColumns'

export default function TeamSplits({ seasons, bySeason, position }: {
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
  const colSet = pos === 'QB' ? QB_COLS : pos === 'RB' ? RB_COLS : pos === 'WR' ? WR_COLS : pos === 'K' ? K_COLS : pos === 'P' ? P_COLS : pos === 'OL' ? OL_COLS : DEF_COLS
  const cols = colSet.filter(c => c.kind === 'trad' && c.key !== 'g' && !c.derived)

  return (
    <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden mb-4">
      <div className="px-4 py-2.5 border-b border-surface-line">
        <span className="text-xs font-bold text-ink-dim uppercase tracking-widest">Career by Team</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-line">
              <th className="py-2 pl-4 pr-3 text-xs font-medium text-ink-dim text-left whitespace-nowrap">Team</th>
              <th className="py-2 px-3 text-xs font-medium text-ink-dim text-left whitespace-nowrap">Seasons</th>
              {cols.map(c => (
                <th key={c.key} className="py-2 px-3 text-xs font-medium text-ink-dim text-left whitespace-nowrap">{c.label}</th>
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
                <tr key={team} className="border-t border-surface-line/60 hover:bg-surface-raise/30">
                  <td className="py-2.5 pl-4 pr-3">
                    <Link to={`/teams/${team}`} className="flex items-center gap-2 group w-fit">
                      <img src={teamLogoUrl(team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                      <span className="text-sm font-bold text-ink-mid group-hover:text-ink transition-colors">{team}</span>
                    </Link>
                  </td>
                  <td className="py-2.5 px-3 text-xs text-ink-dim whitespace-nowrap">{label}</td>
                  {cols.map(c => {
                    const raw = c.cell(t, games.length)
                    const isNull = raw === null || raw === undefined
                    return (
                      <td key={c.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums text-sm ${isNull ? 'text-ink-dim' : c.highlight ? 'text-ink font-bold' : 'text-ink-mid'}`}>
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
