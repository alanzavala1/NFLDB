import type { Game } from '../../types'

const GAME_TYPE_LABELS: Record<string, string> = { WC: 'Wild Card', DIV: 'Divisional', CON: 'Conference', SB: 'Super Bowl' }

export const MICRO = 'text-[10px] font-bold uppercase tracking-[0.14em] text-ink-dim'

export function weekLabel(week: number, gameType?: string | null) {
  if (gameType && GAME_TYPE_LABELS[gameType]) return GAME_TYPE_LABELS[gameType]
  return `Week ${week}`
}

export function shortWeekLabel(week: number, gameType?: string | null) {
  if (gameType === 'SB') return 'SB'
  if (gameType === 'CON') return 'CONF'
  if (gameType === 'DIV') return 'DIV'
  if (gameType === 'WC') return 'WC'
  return `W${week}`
}

function dateFromYmd(gameday: string | null) {
  if (!gameday) return null
  const [year, month, day] = gameday.split('-').map(Number)
  if (!year || !month || !day) return null
  return new Date(year, month - 1, day)
}

function dayOfWeek(gameday: string): number {
  return dateFromYmd(gameday)?.getDay() ?? 0
}

export function dayAbbrev(gameday: string | null) {
  const date = dateFromYmd(gameday)
  return date ? date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase() : 'TBD'
}

export function formatTimeShort(time: string | null) {
  if (!time || time === 'TBD') return 'TBD'
  const [hours, minutes] = time.split(':').map(Number)
  const ampm = hours >= 12 ? 'PM' : 'AM'
  const hour = hours % 12 || 12
  return `${hour}:${String(minutes).padStart(2, '0')} ${ampm}`
}

export function formatDateShort(gameday: string | null) {
  const date = dateFromYmd(gameday)
  return date ? date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : null
}

export function formatMonthDay(gameday: string | null) {
  const date = dateFromYmd(gameday)
  return date ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'TBD'
}

export function isFinished(game: Game) {
  return game.away_score !== null && game.home_score !== null
}

export function primetimeBadge(gameday: string | null, gametime: string | null): string | null {
  if (!gameday) return null
  const dow = dayOfWeek(gameday)
  const hour = gametime ? parseInt(gametime.split(':')[0], 10) : 0
  if (dow === 4) return 'TNF'
  if (dow === 1) return 'MNF'
  if (dow === 0 && hour >= 20) return 'SNF'
  if (dow === 6) return 'SAT'
  return null
}

export function recordText(record?: string | null) {
  return record && record.trim() ? record : '0-0'
}

export function formatSpread(game: Game) {
  if (game.spread_line === null) return null
  if (game.spread_line === 0) return 'PICK'
  const favorite = game.spread_line > 0 ? game.home_team : game.away_team
  return `${favorite} -${Math.abs(game.spread_line)}`
}

export function formatTotalLine(game: Game) {
  return game.total_line === null ? null : `O/U ${game.total_line}`
}

export function formatTotalValue(game: Game) {
  return game.total_line === null ? null : String(game.total_line)
}

export function formatKickoffFact(game: Game) {
  const date = formatDateShort(game.gameday)
  const time = formatTimeShort(game.gametime)
  if (date && time !== 'TBD') return `${date} ${time} ET`
  return date ?? `${time} ET`
}

export function finalLabel(game: Game) {
  return game.overtime === 1 ? 'FINAL OT' : 'FINAL'
}

export function gameWinner(game: Game): string | null {
  if (!isFinished(game)) return null
  if (game.away_score! > game.home_score!) return game.away_team
  if (game.home_score! > game.away_score!) return game.home_team
  return null
}
