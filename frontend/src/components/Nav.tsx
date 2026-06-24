import React, { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { SearchResult } from '../api'
import { teamLogoUrl, teamName } from '../utils/teams'

export type Crumb = { label: React.ReactNode; to?: string; state?: unknown }

type NavProps = {
  crumbs?: Crumb[]
  title?: React.ReactNode
}

function HomeIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
      <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7A1 1 0 003 11h1v6a1 1 0 001 1h4v-4h2v4h4a1 1 0 001-1v-6h1a1 1 0 00.707-1.707l-7-7z" />
    </svg>
  )
}

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

export default function Nav({ crumbs, title }: NavProps) {
  const navigate = useNavigate()
  const [searchOpen, setSearchOpen] = useState(false)

  const allCrumbs: Crumb[] = crumbs ?? (title ? [{ label: title }] : [])

  return (
    <>
      <nav className="px-4 sm:px-6 py-4 flex items-center gap-3 border-b border-gray-800/50 bg-gray-950">
        <button
          onClick={() => navigate(`/?season=${CURRENT_NFL_SEASON}`)}
          className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 shrink-0"
          title="Home"
        >
          <HomeIcon />
        </button>
        <div className="flex items-center gap-1.5 flex-1 min-w-0 overflow-hidden">
          {allCrumbs.map((crumb, i) => {
            const isLast = i === allCrumbs.length - 1
            return (
              <React.Fragment key={i}>
                <span className="text-gray-700 shrink-0">/</span>
                {isLast || !crumb.to
                  ? <span className="text-gray-300 text-sm font-medium truncate">{crumb.label}</span>
                  : <Link to={crumb.to as string} state={crumb.state} className="text-gray-500 hover:text-white text-sm font-medium shrink-0 transition-colors">{crumb.label}</Link>
                }
              </React.Fragment>
            )
          })}
        </div>
        <button
          onClick={() => navigate('/ask')}
          className="shrink-0 flex items-center gap-1.5 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg px-3 py-1.5 transition-colors"
          title="Ask the data in plain English"
        >
          <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-4 4v-4z" />
          </svg>
          Ask AI
        </button>
        <button
          onClick={() => setSearchOpen(true)}
          className={backBtnCls + ' flex items-center gap-1.5'}
        >
          <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          Search
        </button>
      </nav>
      {searchOpen && <SearchModal onClose={() => setSearchOpen(false)} />}
    </>
  )
}

export const backBtnCls = 'text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-1.5 transition-colors'
