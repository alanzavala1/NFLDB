import type { PassingRow, PlayerPassingSplits, PlayerSplit } from '../../types'
import { unavailablePassingRow, PASSING_FIELDS } from './passingAvailability'

export function preparedPassingRows(data: PlayerPassingSplits | undefined): PassingRow[] {
  return data?.seasons.flatMap(item => item.status === 'prepared' && item.overall
    ? [...item.rows, item.overall]
    : [unavailablePassingRow(item.season, item.reason ?? 'Passing summary inputs have not been prepared for this season.')]) ?? []
}

/** An absent bucket contributes zero classified activity only for known fields.
 * Missing preparation must remain unknown in combined career rows.
 */
export function includePassingSeasons(rows: PlayerSplit[], allRows: PlayerSplit[]): PlayerSplit[] {
  const years = allRows.filter(row => row.split_dim === 'overall') as PassingRow[]
  const buckets = [...new Map(rows.map(row => [row.split_value, row])).values()]
  return [...rows, ...years.flatMap(year => buckets.filter(bucket => !rows.some(row =>
    row.season === year.season && row.split_value === bucket.split_value)).map(bucket => ({
    ...year, ...Object.fromEntries(PASSING_FIELDS.map(field => [field, year[field] == null ? null : 0])),
    split_dim: bucket.split_dim, split_value: bucket.split_value, sort_order: bucket.sort_order,
    epa: null, success_pct: null, cpoe: null,
    aggregation: Object.fromEntries(Object.entries(year.aggregation).map(([field, value]) => [field, value == null ? null : 0])),
  })))]
}
