import { useQuery, useQueries } from '@tanstack/react-query'
import { playerQueryOptions } from '../../api/players'
import { playerSplitsQueryOptions, defensiveSplitsQueryOptions } from '../../api/playerSplits'
import { teamSplitsQueryOptions } from '../../api/teams'
import { teamAnalyticsQueryOptions } from '../../api/teamAnalytics'
import type { ComparisonSelection } from './types'
import { CAREER_SEASON } from './constants'

export function useSplitQueries({ mode, playerLens, players, teams, season }: ComparisonSelection) {
  const isDefense = mode === 'players' && playerLens === 'defense'
  const activePlayers = mode === 'players' ? players : []
  const offenseResults = useQueries({ queries: isDefense ? [] : activePlayers.map(player => playerSplitsQueryOptions(player.id)) })
  const defenseResults = useQueries({ queries: isDefense ? activePlayers.map(player => defensiveSplitsQueryOptions(player.id)) : [] })
  const playerResults = isDefense ? defenseResults : offenseResults
  const teamResults = useQueries({ queries: mode === 'teams' ? teams.map(team => teamSplitsQueryOptions(team, season)) : [] })
  const splitResults = mode === 'players' ? playerResults : teamResults
  const playerProfiles = useQueries({ queries: activePlayers.map(player => playerQueryOptions(player.id)) })
  const isCareer = mode === 'players' && season === CAREER_SEASON
  const showDefensiveRanks = mode === 'players' && !isCareer && !isDefense
  const analytics = useQuery(teamAnalyticsQueryOptions(showDefensiveRanks && activePlayers.length > 0 ? season : null))
  return {
    playerResults, teamResults, splitResults, playerProfiles, analytics,
    rankQuery: showDefensiveRanks && activePlayers.length > 0 ? analytics : null
  }
}
