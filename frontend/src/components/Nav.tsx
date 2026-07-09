import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { SearchResult } from '../api'
import { teamLogoUrl, teamName } from '../utils/teams'

// The one navigation bar, identical on every page: wordmark, sections, search.
// Season pickers stay inside the pages they scope; player/team pages simply
// have no highlighted section.

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
    if (!trimmed) { setResults([]); return }
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
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg mx-4 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        <div className="relative border-b border-gray-700">
          <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none"
            xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search players or teams…"
            className="w-full bg-transparent pl-11 pr-4 py-3.5 text-sm text-white placeholder-gray-600 focus:outline-none"
          />
        </div>
        {query.trim() && (
          <div className="max-h-80 overflow-y-auto">
            {results.length === 0 ? (
              <div className="px-4 py-3 text-sm text-gray-600">No results for "{query.trim()}"</div>
            ) : results.map(r => r.type === 'team' ? (
              <button key={r.id} onClick={() => go(`/teams/${r.id}`)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800 transition-colors text-left">
                <img src={teamLogoUrl(r.id)} className="w-7 h-7 object-contain shrink-0" alt="" />
                <div>
                  <div className="text-sm font-semibold text-white">{teamName(r.id)}</div>
                  <div className="text-xs text-gray-500">{r.id}</div>
                </div>
              </button>
            ) : (
              <button key={r.id} onClick={() => go(`/players/${r.id}`)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800 transition-colors text-left">
                {r.headshot_url
                  ? <img src={r.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                  : <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
                }
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-white truncate">{r.name}</div>
                  <div className="text-xs text-gray-500">{[r.position, r.team].filter(Boolean).join(' · ')}</div>
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

  // ⌘K / Ctrl+K (and "/" outside inputs) opens search from anywhere.
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
      <nav className="sticky top-0 z-40 border-b border-gray-800/60 bg-gray-950/85 backdrop-blur">
        <div className="flex h-14 items-center gap-1 px-4 sm:px-6">
          <Link to="/" className="mr-3 shrink-0 text-lg font-black tracking-tight leading-none select-none">
            <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
          </Link>
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {LINKS.map(l => (
              <Link
                key={l.label}
                to={l.to}
                className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  l.isActive(pathname)
                    ? 'bg-gray-800/80 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800/40'
                }`}
              >
                {l.label}
              </Link>
            ))}
          </div>
          <button
            onClick={() => setSearchOpen(true)}
            className="shrink-0 flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900 px-3 py-1.5 text-sm text-gray-400 transition-colors hover:border-gray-700 hover:text-white"
            title="Search players or teams (⌘K)"
          >
            <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span className="hidden sm:inline">Search</span>
            <kbd className="hidden md:inline rounded border border-gray-700/80 bg-gray-800/80 px-1.5 py-px font-sans text-[10px] text-gray-500">⌘K</kbd>
          </button>
        </div>
      </nav>
      {searchOpen && <SearchModal onClose={() => setSearchOpen(false)} />}
    </>
  )
}
