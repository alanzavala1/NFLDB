import { useCallback, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { SearchResult } from '../../types'
import { observeSearch } from './observeSearch'

export function useExampleSearch(selectionKey: string) {
  const client = useQueryClient()
  const active = useRef<AbortController | null>(null)
  const cancel = useCallback(() => { active.current?.abort() }, [])
  useEffect(() => cancel, [selectionKey, cancel])

  return async function resolvePlayers(names: string[]): Promise<SearchResult[] | null> {
    cancel()
    const request = new AbortController()
    active.current = request
    const results: SearchResult[] = []
    for (const name of names.map(value => value.trim()).filter(Boolean)) {
      try {
        const result = (await observeSearch(client, name, request.signal)).find(item => item.type === 'player')
        if (result) results.push(result)
      } catch { /* Examples keep their best-effort behavior for unavailable names. */ }
      if (request.signal.aborted) return null
    }
    if (active.current === request) active.current = null
    return results
  }
}
