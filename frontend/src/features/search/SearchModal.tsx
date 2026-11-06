import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useEntitySearch } from './useEntitySearch'
import { SearchResults } from './SearchResults'

export function SearchModal({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const search = useEntitySearch(text)
  const navigate = useNavigate()
  useEffect(() => { inputRef.current?.focus() }, [])
  useEffect(() => {
    function onKey(event: KeyboardEvent) { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/65 pt-24 backdrop-blur-sm" onClick={onClose}>
    <div role="dialog" aria-label="Search players or teams" className="mx-4 w-full max-w-lg overflow-hidden rounded-card border border-surface-line bg-surface-card shadow-2xl" onClick={event => event.stopPropagation()}>
      <div className="relative border-b border-surface-line">
        <svg className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input ref={inputRef} type="text" aria-label="Search players or teams" value={text} onChange={event => setText(event.target.value)} placeholder="Search players or teams..."
          className="w-full bg-transparent py-3.5 pl-11 pr-4 text-sm text-ink placeholder-ink-dim focus:outline-none" />
      </div>
      {search.term && <div className="max-h-80 overflow-y-auto"><SearchResults search={search} onSelect={result => {
        onClose()
        navigate(result.type === 'team' ? `/teams/${result.id}` : `/players/${result.id}`)
      }} /></div>}
    </div>
  </div>
}
