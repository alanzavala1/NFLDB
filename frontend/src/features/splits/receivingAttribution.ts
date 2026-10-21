import type { PlayerGame, PlayerSplit } from '../../types'
import { CAREER_SEASON, OVERALL_DIM } from './constants'

// Reviewed in api/experiments/receiving_credits.py and its real-play fixtures.
// This explains matching observations; it never replaces a returned stat value.
const GIBBS_LATERALS = [
  { gameId: '2024_03_DET_ARI', label: 'Week 3 at Arizona', yards: 20 },
  { gameId: '2024_15_BUF_DET', label: 'Week 15 vs Buffalo', yards: 21 },
]

export type ReceivingYardageDifference = {
  season: number
  weeklyYards: number
  splitYards: number
  difference: number
  reviewedPlays: typeof GIBBS_LATERALS | null
}

/** Compare one season at a time, using Down once rather than summing dimensions. */
export function receivingYardageDifferences(
  playerId: string, games: readonly PlayerGame[] | undefined, splits: readonly PlayerSplit[] | undefined, season: number | null,
): ReceivingYardageDifference[] {
  if (!games || !splits || season === null) return []
  const selected = games.filter(g => g.game_type === 'REG' && (season === CAREER_SEASON || g.season === season))
  const seasons = [...new Set(selected.map(g => g.season))].sort((a, b) => b - a)
  return seasons.flatMap(year => {
    const weekly = selected.filter(g => g.season === year)
    const down = splits.filter(s => s.category === 'receiving' && s.season === year && s.split_dim === OVERALL_DIM)
    // Missing/invalid input is not a measured zero or an identified attribution cause.
    if (!down.length || weekly.some(g => !Number.isFinite(g.rec_yards)) || down.some(s => !Number.isFinite(s.yards))) return []
    const weeklyYards = weekly.reduce((sum, g) => sum + g.rec_yards, 0)
    const splitYards = down.reduce((sum, s) => sum + s.yards!, 0)
    const difference = weeklyYards - splitYards
    if (difference === 0) return []
    const reviewedPlays = playerId === '00-0039139' && year === 2024 && weeklyYards === 517 && splitYards === 476
      ? GIBBS_LATERALS : null
    return [{ season: year, weeklyYards, splitYards, difference, reviewedPlays }]
  })
}

export const RECEIVING_YARDAGE_NOTE_ID = 'receiving-yardage-sources'
