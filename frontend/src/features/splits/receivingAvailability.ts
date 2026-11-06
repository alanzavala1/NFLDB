import type { PlayerSplit, ReceivingRow } from '../../types'

type ReceivingField = 'att' | 'cmp' | 'yards' | 'td' | 'yac' | 'air_yards' | 'first_downs' | 'epa' | 'success_pct'
export const RECEIVING_FIELDS = ['att', 'cmp', 'yards', 'td', 'interceptions', 'air_yards', 'yac',
  'first_downs', 'epa', 'success_pct', 'cpoe'] as const

const FIELDS: Record<string, ReceivingField[]> = {
  tgt: ['att'], rec: ['cmp'], yds: ['yards'], td: ['td'], cth: ['cmp', 'att'],
  ypr: ['yards', 'cmp'], ytgt: ['yards', 'att'], adot: ['air_yards', 'att'],
  yac: ['yac'], epa: ['epa'], succ: ['success_pct'], conv: ['first_downs', 'att'], tdpct: ['td', 'att'],
}

export function receivingReasons(row: PlayerSplit): Record<string, string> {
  return (row as Partial<ReceivingRow>).unavailable_metrics ?? {}
}

export function receivingMetricReason(row: PlayerSplit, metric: string): string {
  const fields = FIELDS[metric] ?? []
  const reasons = receivingReasons(row)
  return [...new Set(fields.filter(field => row[field] == null)
    .map(field => reasons[field] ?? 'Unavailable for at least one included season or split row.'))].join(' ')
    || 'This rate requires a positive, known denominator.'
}

export function unavailableReceivingRow(season: number, reason: string): ReceivingRow {
  return {
    season, category: 'receiving', split_dim: 'overall', split_value: 'all', sort_order: 1,
    att: null, cmp: null, yards: null, td: null, interceptions: null, air_yards: null,
    yac: null, first_downs: null, epa: null, success_pct: null, cpoe: null,
    unavailable_metrics: Object.fromEntries(RECEIVING_FIELDS.map(field => [field, reason])),
  }
}
