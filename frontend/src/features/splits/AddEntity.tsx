import { useState, useEffect, useRef } from 'react'
import { api } from '../../api'
import type { SearchResult } from '../../types'
import type { ComparisonMode } from './types'
import { teamLogoUrl, teamName } from '../../utils/teams'

export function AddEntity({ mode, onAdd }: { mode: ComparisonMode; onAdd: (r: SearchResult) => void }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current)
    const trimmed = q.trim()
    if (!trimmed) return
    let cancelled = false
    debounce.current = setTimeout(async () => {
      try { const res = await api.search(trimmed); if (!cancelled) setResults(res.filter(r => mode === 'players' ? r.type === 'player' : r.type === 'team')) }
      catch { if (!cancelled) setResults([]) }
    }, 250)
    return () => {
      cancelled = true
      if (debounce.current) clearTimeout(debounce.current)
    }
  }, [q, mode])
  return (
    <div className="relative">
      <input value={q} onChange={e => { const value = e.target.value; setQ(value); if (!value.trim()) setResults([]); setOpen(true) }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={mode === 'players' ? '+ Add player…' : '+ Add team…'}
        className="bg-surface-card border border-surface-line text-ink text-sm rounded-lg px-3 py-2 w-52 focus:outline-none focus:border-surface-line placeholder:text-ink-dim" />
      {open && q.trim() && results.length > 0 && (
        <div className="absolute z-30 mt-1 w-64 max-h-72 overflow-y-auto bg-surface-card border border-surface-line rounded-lg shadow-2xl">
          {results.slice(0, 12).map(r => (
            <button key={r.id} onMouseDown={() => { onAdd(r); setQ(''); setResults([]) }} className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-surface-raise text-left">
              {r.type === 'team' ? <img src={teamLogoUrl(r.id)} className="w-6 h-6 object-contain shrink-0" alt="" />
                : r.headshot_url ? <img src={r.headshot_url} className="w-6 h-6 rounded-full object-cover object-top shrink-0 bg-surface-raise" alt="" /> : <div className="w-6 h-6 rounded-full bg-surface-raise shrink-0" />}
              <div className="min-w-0">
                <div className="text-sm font-semibold text-ink truncate">{r.type === 'team' ? teamName(r.id) : r.name}</div>
                <div className="text-xs text-ink-dim truncate">{r.type === 'team' ? r.id : [r.position, r.team].filter(Boolean).join(' · ')}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
