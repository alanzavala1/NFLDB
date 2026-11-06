import type { SplitRow } from './types'
import type { PlayerSplit, TeamSplit } from '../../types'

export function bestSet(values: (number | null)[], higherIsBetter: boolean | undefined): Set<number> {
  if (higherIsBetter === undefined) return new Set()
  const present = values.map((v, i) => [v, i] as const).filter(([v]) => v != null) as [number, number][]
  if (present.length < 2) return new Set()
  const best = present.reduce((m, [v]) => higherIsBetter ? Math.max(m, v) : Math.min(m, v), present[0][0])
  if (present.every(([v]) => v === best)) return new Set()
  return new Set(present.filter(([v]) => v === best).map(([, i]) => i))
}

export const splitVolume = (r: SplitRow | null) => ((r as PlayerSplit)?.att ?? (r as TeamSplit)?.plays) ?? 0
