type CoverageSeason = { status: string; views: Record<string, { status: string; excluded: object }> }

export function preparedViewHasGaps(seasons: CoverageSeason[], dimension: string): boolean {
  return seasons.some(item => {
    const view = item.views[dimension]
    return item.status !== 'prepared' || !view || view.status === 'unavailable'
      || Object.values(view.excluded).some(value => value != null && value !== 0)
  })
}
