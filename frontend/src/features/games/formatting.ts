import type { GameDetail } from '../../types'

const WEEK_LABELS: Record<number, string> = { 19: 'Wild Card', 20: 'Divisional', 21: 'Conference', 22: 'Super Bowl' }

export function weekLabel(w: number) { return WEEK_LABELS[w] ?? `Week ${w}` }

export function formatStat(n: number) { return n === 0 ? '—' : n % 1 === 0 ? String(n) : n.toFixed(1) }

export function formatYardsPerAttempt(y: number, a: number) { return a === 0 ? '—' : (y / a).toFixed(1) }

export function formatGameday(s: string | null) {
  if (!s) return 'TBD'
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// ── Win probability chart ─────────────────────────────────────────────────────

export function formatGameClock(rem: number): string {
  if (rem < 0) {
    const elapsedOT = -rem
    const min = Math.floor((600 - elapsedOT) / 60)
    const sec = (600 - elapsedOT) % 60
    return `OT ${Math.max(0, min)}:${Math.max(0, sec).toString().padStart(2, '0')}`
  }
  const qtr = rem > 2700 ? 1 : rem > 1800 ? 2 : rem > 900 ? 3 : 4
  const secInQtr = rem - (qtr === 1 ? 2700 : qtr === 2 ? 1800 : qtr === 3 ? 900 : 0)
  const min = Math.floor(secInQtr / 60)
  const sec = secInQtr % 60
  return `Q${qtr} ${min}:${sec.toString().padStart(2, '0')}`
}

export function initials(name: string) {
  const parts = name.replace(/[^a-zA-Z ]/g, '').split(/\s+/).filter(Boolean)
  return (parts.length > 1 ? `${parts[0][0]}${parts.at(-1)?.[0]}` : name.slice(0, 2)).toUpperCase()
}

export function lastName(name: string | null | undefined) {
  if (!name) return ''
  const parts = name.split(' ').filter(Boolean)
  const suffixes = new Set(['Jr.', 'Sr.', 'II', 'III', 'IV', 'V'])
  const last = parts.at(-1) ?? name
  if (parts.length > 1 && suffixes.has(last)) return `${parts.at(-2)} ${last}`
  return last
}

export function titleCase(value: string | null | undefined) {
  if (!value) return ''
  return value.toLowerCase().replace(/\b[a-z]/g, c => c.toUpperCase())
}

export function ratingClass(r: number | null | undefined) {
  if (r == null) return ''
  if (r < 5) return 'b-bad'
  if (r < 7) return 'b-mid'
  return 'b-good'
}

export function formatSnapPercent(v: number | null | undefined) {
  return v == null ? '-' : `${Math.round(v * 100)}%`
}

function roman(n: number) {
  const vals: [number, string][] = [[100, 'C'], [90, 'XC'], [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']]
  let out = ''
  for (const [value, sym] of vals) {
    while (n >= value) {
      out += sym
      n -= value
    }
  }
  return out
}

export function gameLabel(game: GameDetail) {
  if (game.game_type === 'SB') return `Super Bowl ${roman(game.season - 1965)}`
  if (game.game_type === 'CONF' || game.game_type === 'CON') return 'Conference'
  if (game.game_type === 'DIV') return 'Divisional'
  if (game.game_type === 'WC') return 'Wild Card'
  return `Week ${game.week}`
}

export function roundTitle(game: GameDetail) {
  return game.game_type === 'REG' ? `${game.season} Week ${game.week}` : `${game.season} Postseason`
}

export function roundLabel(gameType: string) {
  return ({ WC: 'WC', DIV: 'DIV', CONF: 'CONF', CON: 'CONF', SB: 'SB', REG: 'WK' } as Record<string, string>)[gameType] ?? gameType
}

export function spreadLabel(game: GameDetail) {
  const spread = game.spread_line
  if (spread == null) return '-'
  if (spread === 0) return 'Pick'
  const favorite = spread < 0 ? game.away_team : game.home_team
  return `${favorite} -${Math.abs(spread)}`
}
