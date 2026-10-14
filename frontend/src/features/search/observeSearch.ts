import { QueryObserver, type QueryClient } from '@tanstack/react-query'
import { searchQueryOptions } from '../../api/search'
import type { SearchResult } from '../../types'

// Examples need a temporary observer too: cancelling one consumer must leave
// a request alive while another search field or example still needs it.
export function observeSearch(client: QueryClient, term: string, signal: AbortSignal): Promise<SearchResult[]> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Search cancelled', 'AbortError')); return }
    const observer = new QueryObserver(client, searchQueryOptions(term))
    const subscription = { stop: () => {} }
    let finished = false
    function finish(error: Error | null, data?: SearchResult[]) {
      if (finished) return
      finished = true
      signal.removeEventListener('abort', abort)
      subscription.stop()
      if (error) reject(error)
      else resolve(data ?? [])
    }
    function abort() { finish(new DOMException('Search cancelled', 'AbortError')) }
    function check() {
      const result = observer.getCurrentResult()
      if (result.isFetching || result.isPending) return
      if (result.isError) finish(result.error)
      else finish(null, result.data)
    }
    signal.addEventListener('abort', abort, { once: true })
    subscription.stop = observer.subscribe(check)
    if (finished) subscription.stop()
    else check()
  })
}
