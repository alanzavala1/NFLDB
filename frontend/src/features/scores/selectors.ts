import type { Game, ScheduleWeek, SeasonStatus } from '../../types'
import { isFinished, primetimeBadge, formatDateShort, formatTimeShort } from './presentation'

const GAME_TYPE_PRIORITY: Record<string, number> = { SB: 4, CON: 3, DIV: 2, WC: 1, REG: 0 }

export function parseNumberParam(value: string | null): number | null {
  if (value === null || value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

// "scheduled" counts here where it doesn't on Leaders or Standings: a season
// whose fixtures are published but whose games haven't been charted yet has
// nothing to rank, but it does have a schedule — and during week one it is
// where the live scores are.

export const SELECTABLE = new Set(['loaded', 'scheduled'])

export function defaultSeason(seasons: SeasonStatus[]): number | null {
  const selectable = seasons.filter(s => SELECTABLE.has(s.status))
  return [...selectable].sort((a, b) => b.season - a.season)[0]?.season ?? null
}

function gameTypePriority(game: Game) {
  return GAME_TYPE_PRIORITY[game.game_type] ?? 0
}

function kickoffKey(game: Game) {
  return `${game.gameday ?? '9999-99-99'} ${game.gametime ?? '99:99'} ${game.game_id}`
}

function spreadCloseness(game: Game) {
  if (game.spread_line === null) return 0
  return Math.max(0, 21 - Math.abs(game.spread_line))
}

export function pickFeaturedGame(games: Game[]): Game | null {
  if (!games.length) return null
  const hasUpcoming = games.some(g => !isFinished(g))
  const pool = hasUpcoming ? games.filter(g => !isFinished(g)) : games
  return [...pool].sort((a, b) => {
    const typeDiff = gameTypePriority(b) - gameTypePriority(a)
    if (typeDiff !== 0) return typeDiff

    if (hasUpcoming) {
      const primeDiff = Number(Boolean(primetimeBadge(b.gameday, b.gametime))) - Number(Boolean(primetimeBadge(a.gameday, a.gametime)))
      if (primeDiff !== 0) return primeDiff
      const divDiff = Number(b.div_game === 1) - Number(a.div_game === 1)
      if (divDiff !== 0) return divDiff
      const spreadDiff = spreadCloseness(b) - spreadCloseness(a)
      if (spreadDiff !== 0) return spreadDiff
      return kickoffKey(a).localeCompare(kickoffKey(b))
    }

    const marginA = Math.abs(a.away_score! - a.home_score!)
    const marginB = Math.abs(b.away_score! - b.home_score!)
    if (marginA !== marginB) return marginA - marginB
    const otDiff = Number(b.overtime === 1) - Number(a.overtime === 1)
    if (otDiff !== 0) return otDiff
    const totalDiff = (b.away_score! + b.home_score!) - (a.away_score! + a.home_score!)
    if (totalDiff !== 0) return totalDiff
    return kickoffKey(b).localeCompare(kickoffKey(a))
  })[0] ?? null
}

export function findCurrentWeek(schedule: ScheduleWeek[]): number | null {
  const inProgress = schedule.find(w =>
    w.games.some(g => isFinished(g)) &&
    w.games.some(g => !isFinished(g))
  )
  if (inProgress) return inProgress.week
  const allComplete = schedule.filter(w => w.games.every(isFinished))
  if (allComplete.length) return allComplete[allComplete.length - 1].week
  const firstUpcoming = schedule.find(w => w.games.every(g => !isFinished(g)))
  return firstUpcoming?.week ?? schedule[0]?.week ?? null
}

export function groupKickoffSlots(games: Game[]) {
  const slots = new Map<string, { label: string; games: Game[]; sort: string }>()
  for (const game of [...games].sort((a, b) => kickoffKey(a).localeCompare(kickoffKey(b)))) {
    const key = `${game.gameday ?? 'TBD'}|${game.gametime ?? 'TBD'}`
    const label = [formatDateShort(game.gameday), game.gametime ? `${formatTimeShort(game.gametime)} ET` : null]
      .filter(Boolean)
      .join(' - ') || 'TBD'
    const current = slots.get(key)
    if (current) current.games.push(game)
    else slots.set(key, { label, games: [game], sort: kickoffKey(game) })
  }
  return [...slots.entries()].map(([key, slot]) => ({ key, ...slot })).sort((a, b) => a.sort.localeCompare(b.sort))
}
