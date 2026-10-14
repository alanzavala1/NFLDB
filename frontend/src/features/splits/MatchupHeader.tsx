import type { EntityCard } from './types'

export function MatchupHeader({ entities, onRemove }: { entities: EntityCard[]; onRemove: (key: string) => void }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2 mb-5">
      {entities.map((e, i) => (
        <div key={e.key} className="group relative flex items-center gap-3 bg-surface-card border border-surface-line rounded-xl pl-3 pr-8 py-2.5 min-w-[150px]" style={{ boxShadow: `inset 0 2px 0 0 rgba(${e.color},0.9)` }}>
          {e.logo ? <img src={e.logo} className="w-10 h-10 object-contain shrink-0" alt="" />
            : e.headshot ? <img src={e.headshot} className="w-10 h-10 rounded-full object-cover object-top bg-surface-raise shrink-0" style={{ boxShadow: `0 0 0 2px rgba(${e.color},0.55)` }} alt="" /> : <div className="w-10 h-10 rounded-full bg-surface-raise shrink-0" />}
          <div className="min-w-0">
            <div className="text-sm font-bold text-ink truncate leading-tight">{e.label}</div>
            {e.sub && <div className="text-[11px] text-ink-dim truncate">{e.sub}</div>}
          </div>
          <button aria-label={`Remove ${e.label}`} onClick={() => onRemove(e.key)} className="absolute top-1.5 right-1.5 w-5 h-5 flex items-center justify-center rounded text-ink-dim hover:text-data-loss hover:bg-surface-raise">×</button>
          {i < entities.length - 1 && entities.length === 2 && <span className="absolute -right-3 top-1/2 -translate-y-1/2 z-10 text-[10px] font-black text-ink-dim">VS</span>}
        </div>
      ))}
    </div>
  )
}
