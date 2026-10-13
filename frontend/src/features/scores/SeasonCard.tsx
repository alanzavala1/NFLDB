import type { SeasonStatus } from '../../types'
import Card from '../../components/Card'
import { SELECTABLE } from './selectors'

export function SeasonCard({
  seasons,
  season,
  onSeasonChange,
}: {
  seasons: SeasonStatus[]
  season: number | null
  onSeasonChange: (season: number) => void
}) {
  const sorted = seasons.filter(entry => SELECTABLE.has(entry.status)).sort((a, b) => b.season - a.season)
  const selected = sorted.find(entry => entry.season === season)

  return (
    <Card title="Season">
      <div className="relative border-t border-surface-line px-4 py-[11px] transition-colors hover:bg-surface-raise">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-bold tabular-nums text-ink">{season ?? 'Season'}</span>
          <span className="text-xs text-ink-dim">current ▾</span>
        </div>
        <select
          id="season-picker"
          aria-label="Season"
          value={selected?.season ?? ''}
          disabled={!sorted.length}
          onChange={e => onSeasonChange(Number(e.target.value))}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        >
          {!selected && <option value="" disabled>Choose a season</option>}
          {sorted.map(entry => (
            <option key={entry.season} value={entry.season}>{entry.season}</option>
          ))}
        </select>
      </div>
    </Card>
  )
}
