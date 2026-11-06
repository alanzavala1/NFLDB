import type { EntityCard } from './types'

export function MatchupHeader({ entities, onRemove }: { entities: EntityCard[]; onRemove: (key: string) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {entities.map(e => (
        <div key={e.key} className="relative min-w-0 flex items-center gap-3 bg-surface-card border border-surface-line rounded-xl pl-3 pr-12 py-3" style={{ boxShadow: `inset 0 2px 0 0 rgba(${e.color},0.9)` }}>
          {e.logo ? <img src={e.logo} className="w-10 h-10 object-contain shrink-0" alt="" />
            : e.headshot ? <img src={e.headshot} className="w-10 h-10 rounded-full object-cover object-top bg-surface-raise shrink-0" style={{ boxShadow: `0 0 0 2px rgba(${e.color},0.55)` }} alt="" /> : <div className="w-10 h-10 rounded-full bg-surface-raise shrink-0" />}
          <div className="min-w-0">
            <div className="text-sm font-bold text-ink break-words leading-snug">{e.label}</div>
            {e.sub && <div className="text-[11px] text-ink-dim truncate">{e.sub}</div>}
          </div>
          <button aria-label={`Remove ${e.label}`} onClick={() => onRemove(e.key)} className="absolute top-1/2 right-1.5 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-lg text-lg text-ink-dim hover:text-data-loss hover:bg-surface-raise focus-visible:outline-2 focus-visible:outline-indigo-400">×</button>
        </div>
      ))}
    </div>
  )
}
