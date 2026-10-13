import type { TeamProfile } from '../../types'
import { computeRecord } from './selectors'

export default function SeasonSidebar({ profiles, years, selected, onSelect, nextYear, onShowOlder }: {
  profiles: TeamProfile[]
  years: number[]
  selected: number
  onSelect: (season: number) => void
  nextYear: number | undefined
  onShowOlder: (year: number) => void
}) {
  const profileMap = Object.fromEntries(profiles.map(p => [p.season, p]))
  return (
    <div className="flex flex-col border border-surface-line rounded-xl overflow-hidden bg-surface-card shrink-0 lg:w-40">
      <div className="px-4 py-2.5 border-b border-surface-line bg-surface-raise/40">
        <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">Seasons</span>
      </div>
      <div className="overflow-y-auto">
        {years.map(year => {
          const profile = profileMap[year]
          const active = year === selected
          const rec = profile ? computeRecord(profile.games, profile.team) : null
          return (
            <button key={year} onClick={() => onSelect(year)} aria-pressed={active}
              className={`w-full text-left px-4 py-3 border-b border-surface-line/60 transition-colors
                ${active ? 'bg-indigo-900/30 border-l-2 border-l-indigo-500' : 'hover:bg-surface-raise/60'}`}>
              <div className="flex items-center gap-1.5">
                <span className={`text-sm font-bold ${active ? 'text-indigo-300' : 'text-ink-mid'}`}>{year}</span>
              </div>
              <div className="text-xs text-ink-dim mt-0.5">{rec?.label ?? ''}</div>
            </button>
          )
        })}
      </div>
      {nextYear !== undefined && (
        <button onClick={() => onShowOlder(nextYear)}
          className="text-xs text-ink-dim hover:text-ink-mid py-2.5 border-t border-surface-line transition-colors">
          Show {nextYear}
        </button>
      )}
    </div>
  )
}
