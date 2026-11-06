import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchQueryOptions } from '../../api/search'

export function useEntitySearch(text: string, enabled = true) {
  const term = text.trim()
  const [settledTerm, setSettledTerm] = useState('')
  useEffect(() => {
    if (!enabled || !term) return
    const timer = setTimeout(() => setSettledTerm(term), 300)
    return () => clearTimeout(timer)
  }, [term, enabled])
  const ready = enabled && term.length > 0 && settledTerm === term
  // Change keys immediately so old results cannot be selected during the delay.
  const query = useQuery({ ...searchQueryOptions(enabled ? term : ''), enabled: ready })
  return { term, query, ready, waiting: enabled && term.length > 0 && !ready }
}
