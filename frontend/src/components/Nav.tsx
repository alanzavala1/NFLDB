import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { SearchModal } from '../features/search/SearchModal'

const LINKS = [
  { label: 'Scores',    to: '/',          isActive: (p: string) => p === '/' || p.startsWith('/games') },
  { label: 'Standings', to: '/standings', isActive: (p: string) => p.startsWith('/standings') },
  { label: 'Leaders',   to: '/leaders',   isActive: (p: string) => p.startsWith('/leaders') },
  { label: 'Splits',    to: '/splits',    isActive: (p: string) => p.startsWith('/splits') },
  { label: 'Ask NFLDB', to: '/ask',       isActive: (p: string) => p.startsWith('/ask') },
]

export default function Nav() {
  const [searchOpen, setSearchOpen] = useState(false)
  const searchTrigger = useRef<HTMLButtonElement>(null)
  function closeSearch() { setSearchOpen(false); searchTrigger.current?.focus() }
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
            <span className="text-ink">NFL</span><span className="text-ink-mid">DB</span>
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
            ref={searchTrigger}
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
      {searchOpen && <SearchModal onClose={closeSearch} />}
    </>
  )
}
