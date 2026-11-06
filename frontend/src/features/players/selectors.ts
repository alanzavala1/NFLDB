import type { PlayerGame, PlayerProfile } from '../../types'
import { sumGames, detectPos } from './stats'

export function latestRegularSeason(games: PlayerGame[]): number | null {
  const seasons = games.filter(g => g.game_type === 'REG').map(g => g.season)
  return seasons.length ? Math.max(...seasons) : null
}

export function selectPlayerCareer(player: PlayerProfile) {
  const regGames     = player.games.filter(g => g.game_type === 'REG')
  const playoffGames = player.games.filter(g => g.game_type !== 'REG')

  const regBySeason = regGames.reduce<Record<number, PlayerGame[]>>((acc, g) => {
    ;(acc[g.season] ??= []).push(g)
    return acc
  }, {})
  const playoffBySeason = playoffGames.reduce<Record<number, PlayerGame[]>>((acc, g) => {
    ;(acc[g.season] ??= []).push(g)
    return acc
  }, {})

  // All games per season for the game log (reg + playoffs together, ordered by week)
  const allBySeason = player.games.reduce<Record<number, PlayerGame[]>>((acc, g) => {
    ;(acc[g.season] ??= []).push(g)
    return acc
  }, {})

  const seasons        = Object.keys(regBySeason).map(Number).sort((a, b) => b - a)
  const playoffSeasons = Object.keys(playoffBySeason).map(Number).sort((a, b) => b - a)
  const allSeasons     = [...new Set([...seasons, ...playoffSeasons])].sort((a, b) => b - a)

  const recentGames = allSeasons.length > 0 ? allBySeason[allSeasons[0]] : []
  const recentTeams = [...new Set(recentGames.map(g => g.team))]

  // Highlights bar and career table use regular season only
  const allTotals   = seasons.length > 0 ? sumGames(seasons.flatMap(s => regBySeason[s])) : sumGames([])
  const careerGames = seasons.reduce((acc, s) => acc + regBySeason[s].length, 0)
  const playerPos   = detectPos(allTotals, player.position)
  const hasAdvanced = ['QB', 'RB', 'WR'].includes(playerPos)

  return {
    playoffGames, regBySeason, playoffBySeason, allBySeason, seasons, playoffSeasons,
    allSeasons, recentTeams, allTotals, careerGames, playerPos, hasAdvanced,
  }
}
