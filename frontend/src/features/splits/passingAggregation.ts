import type { PassingAggregation, PassingRow, PlayerSplit } from '../../types'
import { PASSING_FIELDS, passingReasons } from './passingAvailability'

/** Combine sums and their actual populations, preserving unknown components.
 * Rounded averages cannot recover sack EPA or the number of modeled throws.
 */
export function aggregatePassingRows(rows: PlayerSplit[]): PassingRow | null {
  if (!rows.length) return null
  const sum = (field: typeof PASSING_FIELDS[number]) => rows.some(row => row[field] == null)
    ? null : rows.reduce((total, row) => total + row[field]!, 0)
  const component = (field: keyof PassingAggregation) => rows.some(row => (row as Partial<PassingRow>).aggregation?.[field] == null)
    ? null : rows.reduce((total, row) => total + (row as PassingRow).aggregation[field]!, 0)
  const aggregation = { epa_sum: component('epa_sum'), successes: component('successes'),
    cpoe_sum: component('cpoe_sum'), cpoe_count: component('cpoe_count') }
  const att = sum('att')
  const rate = (numerator: number | null, denominator: number | null, scale = 1) =>
    numerator != null && denominator != null && denominator > 0 ? scale * numerator / denominator : null
  const result: PassingRow = {
    ...rows[0], att, cmp: sum('cmp'), yards: sum('yards'), td: sum('td'), interceptions: sum('interceptions'),
    first_downs: sum('first_downs'), air_yards: sum('air_yards'), yac: sum('yac'), aggregation,
    epa: rate(aggregation.epa_sum, att), success_pct: rate(aggregation.successes, att, 100),
    cpoe: rate(aggregation.cpoe_sum, aggregation.cpoe_count), unavailable_metrics: {},
  }
  // Preserve the source's stored precision and explanations for a single row.
  if (rows.length === 1) return { ...result, epa: rows[0].epa, success_pct: rows[0].success_pct,
    cpoe: rows[0].cpoe, unavailable_metrics: { ...passingReasons(rows[0]) } }
  for (const field of PASSING_FIELDS) {
    if (result[field] != null) continue
    const reasons = rows.filter(row => row[field] == null).map(row => passingReasons(row)[field])
      .filter((reason): reason is string => !!reason)
    result.unavailable_metrics[field] = [...new Set(reasons)].join(' ')
      || (field === 'cpoe' && aggregation.cpoe_count === 0 ? 'No modeled CPOE observations in the included rows.'
        : field === 'epa' || field === 'success_pct' || field === 'cpoe'
          ? 'The inputs needed to combine this rate are unavailable, or its denominator is zero.'
          : 'Unavailable for at least one included season or split row.')
  }
  return result
}
