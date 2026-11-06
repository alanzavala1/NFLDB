import type { TeamGame, TeamProfile } from '../../types'

const GAME_TYPE_LABELS: Record<string, string> = { WC: 'Wild Card', DIV: 'Divisional', CON: 'Conference', SB: 'Super Bowl' }

export function weekLabel(week: number, gameType?: string | null) {
  if (gameType && GAME_TYPE_LABELS[gameType]) return GAME_TYPE_LABELS[gameType]
  return `Wk ${week}`
}

export function gameResult(g: TeamGame, team: string): 'W' | 'L' | 'T' | null {
  const isAway = g.away_team === team
  const ts = isAway ? g.away_score : g.home_score
  const os = isAway ? g.home_score : g.away_score
  if (ts === null || os === null) return null
  return ts > os ? 'W' : ts < os ? 'L' : 'T'
}

export function computeRecord(games: TeamGame[], team: string) {
  let w = 0, l = 0, t = 0
  for (const g of games) {
    const r = gameResult(g, team)
    if (r === 'W') w++; else if (r === 'L') l++; else if (r === 'T') t++
  }
  return { w, l, t, label: t > 0 ? `${w}-${l}-${t}` : `${w}-${l}` }
}

export function countTeamGames(profile: TeamProfile, type: 'reg' | 'post'): number {
  return profile.games.filter(g => {
    const gt = g.game_type
    const isReg = !gt || gt === 'REG'
    const matchType = type === 'reg' ? isReg : !isReg
    if (!matchType) return false
    const ts = g.away_team === profile.team ? g.away_score : g.home_score
    const os = g.away_team === profile.team ? g.home_score : g.away_score
    return ts !== null && os !== null
  }).length
}
