import type { LineupPlayer } from '../../types'

type Unit = 'offense' | 'defense'

export type Placed = LineupPlayer & { x: number; y: number; ol?: boolean }

const OFF_COORDS = {
  wr: [[8, 57], [92, 57], [22, 59.5], [78, 59.5], [32, 61.5]],
  te: [[83, 60.5], [17, 60.5]],
  ol: [[30, 62.5], [40, 66], [50, 62.5], [60, 66], [70, 62.5]],
  qb: [[50, 75]],
  rb: [[50, 85], [40, 83]],
}

// Defensive rows are count-aware: each row spreads its actual players evenly
// so any package (4-3, nickel, dime…) lays out without nodes clashing.
const DEF_ROWS: Record<string, { y: number; lo: number; hi: number }> = {
  dl: { y: 56, lo: 28, hi: 72 },
  lb: { y: 66, lo: 30, hi: 70 },
  s: { y: 78, lo: 34, hi: 66 },
}

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
  return 'lb'
}

export function placePlayers(players: LineupPlayer[], unit: Unit): Placed[] {
  if (unit === 'defense') return placeDefense(players)
  const buckets = new Map<string, number>()
  const ordered = [...players].sort((a, b) => {
    const order = ['wr', 'te', 'ol', 'qb', 'rb']
    return order.indexOf(posKey(a)) - order.indexOf(posKey(b))
  })
  return ordered.map((p) => {
    const key = posKey(p)
    const idx = buckets.get(key) ?? 0
    buckets.set(key, idx + 1)
    const coords = OFF_COORDS[key as keyof typeof OFF_COORDS] ?? [[50, 68]]
    let [x, y] = coords[Math.min(idx, coords.length - 1)]
    // A group can exceed its template slots (e.g. a 6-OL jumbo set); fan
    // extras horizontally off the last slot so nodes never stack.
    const overflow = idx - (coords.length - 1)
    if (overflow > 0) {
      const step = Math.ceil(overflow / 2) * 14 * (overflow % 2 === 1 ? 1 : -1)
      x = Math.min(93, Math.max(7, x + step))
      y += 3.5
    }
    return { ...p, x, y, ol: key === 'ol' }
  })
}

function placeDefense(players: LineupPlayer[]): Placed[] {
  const groups = new Map<string, LineupPlayer[]>()
  for (const p of players) {
    const key = posKey(p)
    const k = key === 'dl' || key === 'lb' || key === 's' ? key : 'cb'
    groups.set(k, [...(groups.get(k) ?? []), p])
  }
  const placed: Placed[] = []
  for (const key of ['dl', 'lb', 's'] as const) {
    const row = groups.get(key) ?? []
    const xs = spreadX(row.length, DEF_ROWS[key].lo, DEF_ROWS[key].hi)
    row.forEach((p, i) => placed.push({ ...p, x: xs[i], y: DEF_ROWS[key].y }))
  }
  // Corners hold the edges; extra DBs slot inside on their own row.
  const cbs = groups.get('cb') ?? []
  const edges = [[8, 58.5], [92, 58.5]]
  const slots = spreadX(Math.max(cbs.length - 2, 0), 20, 80)
  cbs.forEach((p, i) => {
    if (i < 2 && cbs.length >= 2) placed.push({ ...p, x: edges[i][0], y: edges[i][1] })
    else placed.push({ ...p, x: slots[Math.max(i - 2, 0)] ?? 50, y: 62 })
  })
  return placed
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
