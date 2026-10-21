import type { PlayerChart } from '../../types'

export const STAT_LABELS: Record<string, string> = {
  attempts: 'Attempts',
  completions: 'Completions',
  pass_yards: 'Passing yards',
  pass_tds: 'Passing TD',
  interceptions_thrown: 'Interceptions',
  targets: 'Targets',
  receptions: 'Receptions',
  rec_yards: 'Receiving yards',
  rec_tds: 'Receiving TD',
  carries: 'Carries',
  rush_yards: 'Rushing yards',
  rush_tds: 'Rushing TD',
  sacks: 'Sacks',
  tackles: 'Tackles',
  def_interceptions: 'Interceptions',
  pass_epa: 'Passing EPA',
  rec_epa: 'Receiving EPA',
  rush_epa: 'Rushing EPA',
}

export const ROLE_STAT_KEYS: Record<string, string[]> = {
  passer: ['attempts', 'completions', 'pass_yards', 'pass_tds', 'interceptions_thrown', 'pass_epa'],
  receiver: ['targets', 'receptions', 'rec_yards', 'rec_tds', 'rec_epa'],
  rusher: ['carries', 'rush_yards', 'rush_tds', 'rush_epa'],
  defender: ['sacks', 'tackles', 'def_interceptions'],
}

// A player's game is often bigger than his primary role — a back who feasts
// as a receiver, a receiver who takes jet sweeps. Show the secondary stat
// family whenever it has volume, so the rating is explainable from the popup.
export const SECONDARY_FAMILY: Record<string, { gate: 'receiving' | 'carries'; title: string; keys: string[] }[]> = {
  rusher: [{ gate: 'receiving', title: 'Receiving', keys: ROLE_STAT_KEYS.receiver }],
  receiver: [{ gate: 'carries', title: 'Rushing', keys: ROLE_STAT_KEYS.rusher }],
  passer: [{ gate: 'carries', title: 'Rushing', keys: ROLE_STAT_KEYS.rusher }],
}

export function fallbackRole(position: string | null | undefined) {
  const pos = (position ?? '').toUpperCase()
  if (['DT', 'DE', 'DL', 'NT', 'EDGE', 'CB', 'DB', 'NB', 'LB', 'ILB', 'OLB', 'MLB', 'FS', 'SS', 'S'].includes(pos)) return 'defender'
  if (pos === 'QB') return 'passer'
  if (['WR', 'TE'].includes(pos)) return 'receiver'
  if (['RB', 'FB', 'HB'].includes(pos)) return 'rusher'
  return 'player'
}

export function formatStatValue(key: string, value: unknown) {
  const num = Number(value)
  if (key.endsWith('_epa') && Number.isFinite(num)) return `${num >= 0 ? '+' : ''}${num.toFixed(1)}`
  return String(value)
}

export function statColor(key: string, value: unknown) {
  if (!key.endsWith('_epa')) return undefined
  return Number(value) >= 0 ? 'var(--win)' : 'var(--rate-bad)'
}

export function avgDepthOfTarget(events: PlayerChart['events']) {
  const depths = events.filter(e => e.air_yards != null).map(e => e.air_yards as number)
  if (!depths.length) return null
  return depths.reduce((s, v) => s + v, 0) / depths.length
}

export function zoneShade(att: number) {
  if (att <= 0) return 'z0'
  if (att === 1) return 'z1'
  if (att <= 3) return 'z2'
  return 'z3'
}
