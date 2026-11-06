import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import type { SplitQueryState } from './SplitQueryFeedback'
import type { ComparisonMode } from './types'

export function SeasonSelectionFeedback({ query, availableYears, season, mode }: {
  query: SplitQueryState; availableYears: number[]; season: number | null; mode: ComparisonMode
}) {
  return <>
    <QueryFailure resource="available seasons" error={query.error} hasData={query.data !== undefined} onRetry={() => void query.refetch()} />
    {query.isPending ? <QueryLoading>Loading available seasons…</QueryLoading>
      : query.data === undefined ? null
        : !availableYears.length ? <p className="text-sm text-ink-dim">No published seasons are available for comparisons.</p>
          : season === null ? <p role="alert" className="text-sm text-ink-dim">That season is unavailable. Choose a published season{mode === 'players' ? ' or Career' : ''} above.</p>
            : null}
  </>
}
