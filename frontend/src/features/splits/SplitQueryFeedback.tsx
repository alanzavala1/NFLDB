import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'

// Only the request state needed for feedback, independent of response shape.
export interface SplitQueryState {
  data: unknown
  error: Error | null
  isPending: boolean
  refetch: () => unknown
}

export function SplitQueryFeedback({ entities, splits, profiles, analytics, splitKind }: {
  entities: { key: string; label: string }[]
  splits: SplitQueryState[]
  profiles: SplitQueryState[]
  analytics: SplitQueryState | null
  splitKind: 'offensive' | 'defensive' | 'team'
}) {
  return <>
    {entities.map((entity, index) => {
      const splitQuery = splits[index]
      const profileQuery = profiles[index]
      return <div key={entity.key}>
        {splitQuery && <QueryFailure resource={`${entity.label} ${splitKind} splits`} error={splitQuery.error}
          hasData={splitQuery.data !== undefined} onRetry={() => void splitQuery.refetch()} />}
        {profileQuery && <QueryFailure resource={`${entity.label} player profile`} error={profileQuery.error}
          hasData={profileQuery.data !== undefined} onRetry={() => void profileQuery.refetch()} />}
        {splitQuery?.isPending && <QueryLoading>Loading {entity.label} split statistics…</QueryLoading>}
        {profileQuery?.isPending && <QueryLoading>Loading {entity.label} player profile…</QueryLoading>}
      </div>
    })}
    {analytics && <QueryFailure resource="opponent defensive ranks" error={analytics.error}
      hasData={analytics.data !== undefined} onRetry={() => void analytics.refetch()} />}
    {analytics?.isPending && <QueryLoading>Loading opponent defensive ranks…</QueryLoading>}
  </>
}

export function EmptySplitState({ queries, resource = 'split statistics' }: {
  queries: SplitQueryState[]
  resource?: 'split statistics' | 'game records'
}) {
  if (queries.some(query => query.isPending)) return <QueryLoading>Loading {resource}…</QueryLoading>
  if (queries.some(query => query.error && query.data === undefined)) {
    return <p className="text-ink-dim text-sm">The {resource} are unavailable for this selection.</p>
  }
  return <p className="text-ink-dim text-sm">No {resource} for this selection.</p>
}
