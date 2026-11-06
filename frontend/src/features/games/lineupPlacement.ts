import type { LineupPlayer } from '../../types'

type Unit = 'offense' | 'defense'

export type Placed = LineupPlayer & { x: number; y: number; ol?: boolean }

function spreadX(count: number, lo: number, hi: number): number[] {
  if (count <= 1) return [(lo + hi) / 2]
  return Array.from({ length: count }, (_, i) => lo + (i * (hi - lo)) / (count - 1))
}

function isOL(p: LineupPlayer) {
  return ['OL', 'G', 'T', 'C', 'LT', 'LG', 'RG', 'RT'].includes((p.position ?? '').toUpperCase())
}

function posKey(p: LineupPlayer) {
  const pos = (p.position ?? '').toUpperCase()
  if (['WR'].includes(pos)) return 'wr'
  if (['TE'].includes(pos)) return 'te'
  if (['QB'].includes(pos)) return 'qb'
  if (['RB', 'FB', 'HB'].includes(pos)) return 'rb'
  if (['DT', 'DE', 'DL', 'NT', 'EDGE'].includes(pos)) return 'dl'
  if (['CB', 'DB', 'NB'].includes(pos)) return 'cb'
  if (['LB', 'ILB', 'OLB', 'MLB'].includes(pos)) return 'lb'
  if (['FS', 'SS', 'S'].includes(pos)) return 's'
  if (isOL(p)) return 'ol'
  return 'other'
}

export function placePlayers(players: LineupPlayer[], unit: Unit): Placed[] {
  // Separate position rows keep labels and touch targets clear on small screens.
  // Keep empty rows so sparse data doesn't move a QB or safety to the line.
  const order = unit === 'offense' ? ['wr', 'te', 'ol', 'qb', 'rb'] : ['dl', 'cb', 'lb', 's']
  const groups = new Map<string, LineupPlayer[]>()
  for (const p of players) {
    const key = posKey(p)
    const k = unit === 'offense' ? key : order.includes(key) ? key : 'lb'
    groups.set(k, [...(groups.get(k) ?? []), p])
  }
  if (unit === 'offense') order.push(...[...groups.keys()].filter(key => !order.includes(key)))
  const rows: { key: string; players: LineupPlayer[] }[] = []
  for (const key of order) {
    const group = groups.get(key) ?? []
    for (let start = 0; start < Math.max(1, group.length); start += 5) {
      rows.push({ key, players: group.slice(start, start + 5) })
    }
  }
  return rows.flatMap((row, index) => {
    const xs = spreadX(row.players.length, 10, 90)
    const y = 56 + index * 32 / (rows.length - 1)
    return row.players.map((p, i) => ({ ...p, x: xs[i], y, ol: unit === 'offense' && row.key === 'ol' }))
  })
}

export function fieldMinHeight(offense: Placed[], defense: Placed[]): number {
  let height = 750
  for (const unit of [offense, defense]) {
    const ys = [...new Set(unit.map(p => p.y))].sort((a, b) => a - b)
    for (let i = 1; i < ys.length; i++) {
      // Each occupied row needs 56px for its targets, names and focus outlines.
      height = Math.max(height, Math.ceil(5600 / (ys[i] - ys[i - 1])))
    }
  }
  return height
}

// Why a player carries no rating. Two causes look identical on the field but
// are different facts: nothing countable happened to him at all, or something
// did and there was too little of it to sit on a percentile curve. Linemen are
// excluded — they intentionally carry no individual grade, only the unit one.
export function ungradedReason(p: LineupPlayer): string | null {
  if (p.rating != null || isOL(p)) return null
  const snaps = p.snaps ?? 0
  const n = p.plays_counted ?? 0
  if (n > 0) return `${snaps} snaps, ${n} graded play${n === 1 ? '' : 's'}, too few to rate`
  return `${snaps} snaps, no graded plays`
}
