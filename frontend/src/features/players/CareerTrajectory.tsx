import type { PlayerGame } from '../../types'
import Card from '../../components/Card'
import { sumGames, type Totals } from './stats'

function getPrimaryStat(t: Totals, pos: string): { value: number; label: string } {
  if (pos === 'QB') return { value: t.pass_yards, label: 'Pass YDS' }
  if (pos === 'RB') return { value: t.rush_yards + t.rec_yards, label: 'Scrim YDS' }
  if (pos === 'WR') return { value: t.rec_yards, label: 'Rec YDS' }
  if (pos === 'K')  return { value: t.fg_made * 3 + t.xp_made, label: 'Points' }
  if (pos === 'P')  return { value: t.punt_yards, label: 'Punt YDS' }
  return { value: t.solo_tackles + t.assist_tackles, label: 'Tackles' }
}

export default function CareerTrajectory({ seasons, bySeason, pos }: {
  seasons: number[]
  bySeason: Record<number, PlayerGame[]>
  pos: string
}) {
  if (seasons.length < 2) return null
  const data = [...seasons]
    .sort((a, b) => a - b)
    .map(s => {
      const totals = sumGames(bySeason[s])
      const games = bySeason[s].length
      const { value, label } = getPrimaryStat(totals, pos)
      return { season: s, value, games, label }
    })
  const max = Math.max(...data.map(d => d.value), 1)
  const peakSeason = data.reduce((p, c) => c.value > p.value ? c : p, data[0]).season
  const statLabel = data[0]?.label ?? ''
  const BAR_MAX_H = 96  // px

  return (
    <Card
      title={<span>Career Trajectory <span className="ml-2 text-[10px] font-bold uppercase tracking-widest text-ink-dim">{statLabel} by season</span></span>}
      action={<span className="text-[10px] tabular-nums text-ink-dim">{data[0].season}–{data[data.length - 1].season}</span>}
      className="mb-8"
    >
      <div className="border-t border-surface-line p-4">
        <div className="flex items-end gap-2 overflow-x-auto" style={{ minHeight: BAR_MAX_H + 28 }}>
          {data.map(d => {
            const isPeak = d.season === peakSeason
            const barH = d.value > 0 ? Math.max(2, Math.round((d.value / max) * BAR_MAX_H)) : 0
            return (
              <div key={d.season} className="flex flex-col items-center shrink-0 w-12">
                <div className="text-[10px] tabular-nums text-ink-mid mb-1 font-semibold leading-none h-3">
                  {d.value > 0 ? d.value.toLocaleString() : ''}
                </div>
                <div
                  className={`w-full rounded-t transition-colors ${isPeak ? 'bg-indigo-500' : 'bg-surface-raise opacity-70 hover:opacity-100'}`}
                  style={{ height: `${barH}px` }}
                  title={`${d.season}: ${d.value.toLocaleString()} ${d.label} · ${d.games}G`}
                />
                <div className={`text-[10px] tabular-nums mt-1 leading-none ${isPeak ? 'text-indigo-400 font-bold' : 'text-ink-dim'}`}>
                  {String(d.season).slice(-2)}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </Card>
  )
}
