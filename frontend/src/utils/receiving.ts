export type ReceivingStats = {
  targets?: number | null
  receptions?: number | null
  rec_yards?: number | null
  rec_tds?: number | null
  air_yards?: number | null
  yac?: number | null
}

/** Recorded production remains displayable independently of target coverage. */
export function hasReceivingProduction(stats: ReceivingStats): boolean {
  return (stats.receptions ?? 0) > 0
    || (Number.isFinite(stats.rec_yards) && (stats.rec_yards ?? 0) !== 0)
    || (stats.rec_tds ?? 0) > 0
}

/** Production qualifies on its own; target-only rows retain the view's minimum. */
export function hasReceivingActivity(stats: ReceivingStats, minimumTargets = 1): boolean {
  return hasReceivingProduction(stats) || (stats.targets ?? 0) >= minimumTargets
}

export function hasUnavailableTargets(rows: ReceivingStats[]): boolean {
  return rows.some(row => row.targets === null && hasReceivingProduction(row))
}

export function hasUnavailableReceivingField(rows: ReceivingStats[], field: 'air_yards' | 'yac'): boolean {
  return rows.some(row => row[field] === null && hasReceivingProduction(row))
}
