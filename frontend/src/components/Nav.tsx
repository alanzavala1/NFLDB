import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { SearchResult } from '../api'
import { teamLogoUrl, teamName } from '../utils/teams'

const LINKS = [
  { label: 'Scores',    to: '/',          isActive: (p: string) => p === '/' || p.startsWith('/games') },
  { label: 'Standings', to: '/standings', isActive: (p: string) => p.startsWith('/standings') },
  { label: 'Leaders',   to: '/leaders',   isActive: (p: string) => p.startsWith('/leaders') },
  { label: 'Splits',    to: '/splits',    isActive: (p: string) => p.startsWith('/splits') },
  { label: 'Ask',       to: '/ask',       isActive: (p: string) => p.startsWith('/ask') },
]

function SearchModal({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const navigate = useNavigate()

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    let cancelled = false
    const trimmed = query.trim()
    if (!trimmed) return
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.search(trimmed)
        if (!cancelled) setResults(res)
      } catch { if (!cancelled) setResults([]) }
    }, 300)
    return () => { cancelled = true; if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [query])

  function go(to: string) { onClose(); navigate(to) }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/65 pt-24 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="mx-4 w-full max-w-lg overflow-hidden rounded-card border border-surface-line bg-surface-card shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="relative border-b border-surface-line">
          <svg
            className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-dim"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => {
              const value = e.target.value
              setQuery(value)
              if (!value.trim()) setResults([])
            }}
            placeholder="Search players or teams..."
            className="w-full bg-transparent py-3.5 pl-11 pr-4 text-sm text-ink placeholder-ink-dim focus:outline-none"
          />
        </div>
        {query.trim() && (
          <div className="max-h-80 overflow-y-auto">
            {results.length === 0 ? (
              <div className="px-4 py-3 text-sm text-ink-dim">No results for "{query.trim()}"</div>
            ) : results.map(r => r.type === 'team' ? (
              <button
                key={r.id}
                onClick={() => go(`/teams/${r.id}`)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface-raise"
              >
                <img src={teamLogoUrl(r.id)} className="h-7 w-7 shrink-0 object-contain" alt="" />
                <div>
                  <div className="text-sm font-semibold text-ink">{teamName(r.id)}</div>
                  <div className="text-xs text-ink-dim">{r.id}</div>
                </div>
              </button>
            ) : (
              <button
                key={r.id}
                onClick={() => go(`/players/${r.id}`)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface-raise"
              >
                {r.headshot_url
                  ? <img src={r.headshot_url} className="h-7 w-7 shrink-0 rounded-full bg-surface-raise object-cover object-top" alt="" />
                  : <div className="h-7 w-7 shrink-0 rounded-full bg-surface-raise" />
                }
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-ink">{r.name}</div>
                  <div className="text-xs text-ink-dim">{[r.position, r.team].filter(Boolean).join(' - ')}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Nav() {
  const [searchOpen, setSearchOpen] = useState(false)
  const { pathname } = useLocation()

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const inField = (e.target as HTMLElement)?.closest('input, textarea, select, [contenteditable]')
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      } else if (e.key === '/' && !inField) {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <nav className="sticky top-0 z-40 border-b border-surface-line bg-surface-bg/90 backdrop-blur">
        <div className="flex h-14 items-center gap-1 px-4 sm:px-6">
          <Link to="/" className="mr-3 shrink-0 select-none text-lg font-black leading-none tracking-tight">
            <span className="text-ink">NFL</span><span className="text-indigo-400">DB</span>
          </Link>
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {LINKS.map(l => (
              <Link
                key={l.label}
                to={l.to}
                className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  l.isActive(pathname)
                    ? 'bg-surface-raise text-ink'
                    : 'text-ink-mid hover:bg-surface-raise/70 hover:text-ink'
                }`}
              >
                {l.label}
              </Link>
            ))}
          </div>
          <button
            onClick={() => setSearchOpen(true)}
            className="flex shrink-0 items-center gap-2 rounded-lg border border-surface-line bg-surface-card px-3 py-1.5 text-sm text-ink-mid transition-colors hover:border-ink-dim hover:text-ink"
            title="Search players or teams"
          >
            <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span className="hidden sm:inline">Search</span>
            <kbd className="hidden rounded border border-surface-line bg-surface-raise px-1.5 py-px font-sans text-[10px] text-ink-dim md:inline">Ctrl K</kbd>
          </button>
        </div>
      </nav>
      {searchOpen && <SearchModal onClose={() => setSearchOpen(false)} />}
    </>
  )
}
