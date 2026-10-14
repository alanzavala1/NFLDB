import { queryOptions, type QueryState } from '@tanstack/react-query'
import { fetchLiveScoreboard } from '../../api/liveScores'
import type { Scoreboard } from '../../types'
import { reconcileScoreboard } from './ordering'

const LIVE_SCOREBOARD_KEY = ['live-scoreboard'] as const
type LiveQueryState = Pick<QueryState<Scoreboard, Error>, 'data' | 'status' | 'fetchStatus' | 'dataUpdatedAt' | 'errorUpdatedAt'>

function pollPeriod(state: LiveQueryState): number | false {
  if (state.status === 'error') return 60_000
  return state.data?.poll_after == null ? false : state.data.poll_after * 1000
}

function nextPollDelay(state: LiveQueryState): number | false {
  // No timer while a request is running: the next interval begins on completion.
  if (state.fetchStatus !== 'idle') return false
  const period = pollPeriod(state)
  if (period === false) return false
  const completedAt = state.status === 'error' ? state.errorUpdatedAt : state.dataUpdatedAt
  return Math.max(1, completedAt + period - Date.now())
}

export function liveScoreboardQueryOptions() {
  return queryOptions({
    queryKey: LIVE_SCOREBOARD_KEY,
    queryFn: async ({ signal, client }) => {
      const incoming = await fetchLiveScoreboard(signal)
      return reconcileScoreboard(client.getQueryData<Scoreboard>(LIVE_SCOREBOARD_KEY), incoming)
    },
    staleTime: query => pollPeriod(query.state) || 0,
    refetchInterval: query => nextPollDelay(query.state),
    refetchIntervalInBackground: true,
    refetchOnMount: query => query.state.fetchStatus === 'idle' && query.state.status !== 'error',
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
    retryOnMount: false,
    networkMode: 'always',
  })
}
