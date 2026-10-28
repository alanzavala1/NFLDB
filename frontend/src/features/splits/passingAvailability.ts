import type { PassingRow, PlayerSplit } from '../../types'

export const PASSING_FIELDS = ['att', 'cmp', 'yards', 'td', 'interceptions', 'air_yards', 'yac',
  'first_downs', 'epa', 'success_pct', 'cpoe'] as const

export function passingReasons(row: PlayerSplit): Record<string, string> {
  return (row as Partial<PassingRow>).unavailable_metrics ?? {}
}

const fields: Record<string, (typeof PASSING_FIELDS[number])[]> = {
  att: ['att'], cmp: ['cmp'], yds: ['yards'], td: ['td'], int: ['interceptions'],
  cmpp: ['cmp', 'att'], ya: ['yards', 'att'], rate: ['cmp', 'att', 'yards', 'td', 'interceptions'],
  adot: ['air_yards', 'att'], yac: ['yac', 'cmp'], epa: ['epa'], succ: ['success_pct'],
  cpoe: ['cpoe'], conv: ['first_downs', 'att'], tdpct: ['td', 'att'],
}

export function passingMetricReason(row: PlayerSplit, metric: string): string {
  const reason = [...new Set((fields[metric] ?? []).filter(field => row[field] == null)
    .map(field => passingReasons(row)[field] ?? 'Unavailable for at least one included season or split row.'))].join(' ')
    || 'This rate requires a positive, known denominator.'
  return reason
    .replaceAll('Detailed passing credits and PBP player contributions disagree',
      'Passing credits in the official stats disagree with the play-by-play for at least one play in this row. Verified counts are still shown.')
    .replaceAll('No modeled CPOE observations', 'The model did not evaluate any throws in this row.')
    .replaceAll('Incomplete modeled QB EPA coverage', 'Some plays lack the inputs needed to calculate EPA. Verified counts are still shown.')
}

export function unavailablePassingRow(season: number, reason: string): PassingRow {
  return {
    season, category: 'passing', split_dim: 'overall', split_value: 'all', sort_order: 1,
    att: null, cmp: null, yards: null, td: null, interceptions: null, air_yards: null, yac: null,
    first_downs: null, epa: null, success_pct: null, cpoe: null,
    unavailable_metrics: Object.fromEntries(PASSING_FIELDS.map(field => [field, reason])),
    aggregation: { epa_sum: null, successes: null, cpoe_sum: null, cpoe_count: null },
  }
}
