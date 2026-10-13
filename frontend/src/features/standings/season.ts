import type { SeasonStatus } from '../../types'

export function loadedSeasons(seasons: SeasonStatus[]) {
  return seasons.filter(s => s.status === 'loaded').map(s => s.season).sort((a, b) => b - a)
}

// Keep explicit links honest: an unavailable year must not show another year's table.
export function selectedSeason(requested: string | null, available: number[]): number | null {
  if (requested === null) return available[0] ?? null
  if (!/^\d{4}$/.test(requested)) return null
  const year = Number(requested)
  return available.includes(year) ? year : null
}
