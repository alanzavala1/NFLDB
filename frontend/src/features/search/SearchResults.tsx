import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import { teamLogoUrl, teamName } from '../../utils/teams'
import type { SearchResult } from '../../types'
import type { useEntitySearch } from './useEntitySearch'

export function SearchResults({ search, kind, limit, onSelect }: {
  search: ReturnType<typeof useEntitySearch>; kind?: 'player' | 'team'; limit?: number; onSelect: (result: SearchResult) => void
}) {
  const { term, query, ready, waiting } = search
  const results = ready ? (query.data ?? []).filter(result => !kind || result.type === kind) : []
  return <>
    {ready && query.error && <div className="p-3"><QueryFailure resource="search results" error={query.error}
      hasData={query.data !== undefined} onRetry={() => void query.refetch()} /></div>}
    {(waiting || (ready && query.isPending)) && <div className="p-3"><QueryLoading>Searching…</QueryLoading></div>}
    {ready && query.data !== undefined && results.length === 0 && <p className="p-3 text-sm text-ink-dim">No results for "{term}"{kind ? ` among ${kind === 'player' ? 'players' : 'teams'}` : ''}.</p>}
    {results.slice(0, limit).map(result => <button key={`${result.type}:${result.id}`} onMouseDown={event => event.preventDefault()} onClick={() => onSelect(result)}
      className="w-full flex items-center gap-2.5 px-3 py-3 text-left hover:bg-surface-raise focus-visible:bg-surface-raise focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-indigo-400">
      {result.type === 'team' ? <img src={teamLogoUrl(result.id)} className="w-6 h-6 object-contain shrink-0" alt="" />
        : result.headshot_url ? <img src={result.headshot_url} className="w-6 h-6 rounded-full object-cover object-top bg-surface-raise shrink-0" alt="" />
          : <div className="w-6 h-6 rounded-full bg-surface-raise shrink-0" />}
      <div className="min-w-0">
        <div className="text-sm font-semibold text-ink truncate">{result.type === 'team' ? teamName(result.id) : result.name}</div>
        <div className="text-xs text-ink-dim truncate">{result.type === 'team' ? result.id : [result.position, result.team].filter(Boolean).join(' · ')}</div>
      </div>
    </button>)}
  </>
}
