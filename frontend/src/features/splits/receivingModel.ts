import type { PlayerReceivingSplits, PlayerSplit, ReceivingSeason } from '../../types'
import { CAREER_SEASON } from './constants'
import { RECEIVING_FIELDS, receivingReasons, unavailableReceivingRow } from './receivingAvailability'

export function selectedReceivingSeasons(data: PlayerReceivingSplits | undefined, season: number | null): ReceivingSeason[] {
  return data?.seasons.filter(item => season === CAREER_SEASON || item.season === season) ?? []
}

export function preparedReceivingRows(data: PlayerReceivingSplits | undefined): PlayerSplit[] {
  return data?.seasons.flatMap(item => item.status === 'prepared' && item.overall
    ? [...item.rows, item.overall]
    : [unavailableReceivingRow(item.season, item.reason ?? 'Receiving splits have not been verified for this season.')]) ?? []
}

/** Absent activity is zero only for supported counts, never unknown metrics.
 * An entirely unverified season therefore contributes NULL to every field.
 * These client-only rows carry availability; they are not extra source credits.
 */
export function includeReceivingSeasons(rows: PlayerSplit[], allRows: PlayerSplit[]): PlayerSplit[] {
  const years = allRows.filter(row => row.split_dim === 'overall')
  const buckets = [...new Map(rows.map(row => [row.split_value, row])).values()]
  return [...rows, ...years.flatMap(year => buckets.filter(bucket => !rows.some(
    row => row.season === year.season && row.split_value === bucket.split_value)).map(bucket => {
    const counts = Object.fromEntries(RECEIVING_FIELDS.map(field => [field, year[field] == null ? null : 0]))
    return { ...year, ...counts, split_dim: bucket.split_dim, split_value: bucket.split_value,
      sort_order: bucket.sort_order, epa: null, success_pct: null, cpoe: null,
      unavailable_metrics: { ...receivingReasons(year),
        epa: receivingReasons(year).epa ?? 'No recorded targets in this row.',
        success_pct: receivingReasons(year).success_pct ?? 'No recorded targets in this row.' },
    }
  }))]
}

export function receivingViewHasGaps(seasons: ReceivingSeason[], dimension: string): boolean {
  return seasons.some(item => {
    const view = item.views[dimension]
    return item.status !== 'prepared' || !view || view.status === 'unavailable'
      || Object.values(view.excluded).some(value => value != null && value !== 0)
  })
}
