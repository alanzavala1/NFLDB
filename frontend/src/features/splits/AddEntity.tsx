import { useState } from 'react'
import type { SearchResult } from '../../types'
import type { ComparisonMode } from './types'
import { useEntitySearch } from '../search/useEntitySearch'
import { SearchResults } from '../search/SearchResults'

export function AddEntity({ mode, onAdd }: { mode: ComparisonMode; onAdd: (r: SearchResult) => void }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const search = useEntitySearch(q, open)
  return (
    <div className="relative min-w-0 flex-1 sm:min-w-44" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false) }}>
      <input aria-label={mode === 'players' ? 'Add player' : 'Add team'} value={q} onChange={e => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onClick={() => setOpen(true)} onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}
        placeholder={mode === 'players' ? '+ Add player…' : '+ Add team…'}
        className="min-h-10 w-full bg-surface-card border border-surface-line text-ink text-sm rounded-lg px-3 py-2 focus-visible:outline-2 focus-visible:outline-indigo-400 focus-visible:outline-offset-2 placeholder:text-ink-dim" />
      {open && search.term && (
        <div className="absolute left-0 right-0 z-30 mt-2 max-h-72 overflow-y-auto bg-surface-card border border-surface-line rounded-lg shadow-2xl">
          <SearchResults search={search} kind={mode === 'players' ? 'player' : 'team'} limit={12} onSelect={result => { onAdd(result); setQ(''); setOpen(false) }} />
        </div>
      )}
    </div>
  )
}
