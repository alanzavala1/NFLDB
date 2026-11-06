import Card from '../../components/Card'
import { STAT_TABS, POS_TABS } from './columns'

export type Mode = 'leaders' | 'positions'

export function LeaderHeader({ years, season, onSeasonChange }: {
  years: number[]
  season: number | null
  onSeasonChange: (year: string) => void
}) {
  return (
    <Card title="League Leaders" className="mb-5">
      <div className="flex items-center justify-between gap-4 border-t border-surface-line px-4 py-3">
        <p className="text-ink-dim text-[10px] uppercase tracking-widest font-bold">
          {season === null ? 'NFL Season' : `${season} NFL Season`}
        </p>
        <select
          aria-label="Season"
          value={season ?? ''}
          disabled={!years.length}
          onChange={e => onSeasonChange(e.target.value)}
          className="bg-surface-raise border border-surface-line text-ink text-sm font-semibold rounded-lg px-4 py-2.5 focus:outline-none focus:border-indigo-500 cursor-pointer hover:border-surface-line transition-colors"
        >
          {season === null && <option value="" disabled>Choose a season</option>}
          {years.map(year => <option key={year} value={year}>{year}</option>)}
        </select>
      </div>
    </Card>
  )
}

export function LeaderControls({ mode, statKey, posKey, onModeChange, onStatChange, onPositionChange }: {
  mode: Mode
  statKey: string
  posKey: string
  onModeChange: (mode: Mode) => void
  onStatChange: (key: string) => void
  onPositionChange: (key: string) => void
}) {
  const tabs = mode === 'leaders' ? [...STAT_TABS, { key: 'wpa', label: 'WPA' }] : POS_TABS
  const activeKey = mode === 'leaders' ? statKey : posKey
  return (
    <>
      <Card title="View" className="mb-5">
        <div className="flex flex-wrap gap-1 border-t border-surface-line p-2">
          {(['leaders', 'positions'] as const).map(value => (
            <button key={value} onClick={() => onModeChange(value)} aria-pressed={mode === value}
              className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${mode === value ? 'bg-indigo-600 text-ink' : 'text-ink-mid hover:text-ink'}`}>
              {value === 'leaders' ? 'Stat Leaders' : 'By Position'}
            </button>
          ))}
        </div>
      </Card>
      <div className="flex gap-1 mb-4 bg-surface-card border border-surface-line rounded-xl p-1 w-fit flex-wrap">
        {tabs.map(tab => (
          <button key={tab.key} aria-pressed={activeKey === tab.key}
            onClick={() => mode === 'leaders' ? onStatChange(tab.key) : onPositionChange(tab.key)}
            className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${activeKey === tab.key ? 'bg-indigo-600 text-ink' : 'text-ink-mid hover:text-ink'}`}>
            {tab.label}
          </button>
        ))}
      </div>
    </>
  )
}
