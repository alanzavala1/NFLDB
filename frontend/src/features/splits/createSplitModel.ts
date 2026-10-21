import type { PlayerSplit, TeamSplit, DefensiveSplit } from '../../types'
import type { ComparisonSelection, Metric, SplitRow, PlayerCategory, EntityCard, Situation } from './types'
import type { useSplitQueries } from './useSplitQueries'
import { teamLogoUrl, teamName } from '../../utils/teams'
import { PLAYER_SPLIT_CONFIG, PLAYER_SITUATIONS } from './playerConfig'
import { TEAM_SPLIT_CONFIG, TEAM_SITUATIONS } from './teamConfig'
import { DEFENSE_SPLIT_CONFIG, DEFENSE_SITUATIONS } from './defenseConfig'
import {
  aggregatePlayerSplitRows, aggregateTeamSplitRows, aggregateDefenseSplitRows,
  aggregateDefenseCareerByValue, aggregateCareerByValue, gameToSplitRow
} from './aggregation'
import { CAREER_SEASON, OVERALL_DIM } from './constants'
import { entityColor } from './presets'
import { hasReceivingActivity } from '../../utils/receiving'
import { receivingYardageDifferences, RECEIVING_YARDAGE_NOTE_ID } from './receivingAttribution'

export function createSplitModel(comparison: ComparisonSelection, queries: ReturnType<typeof useSplitQueries>) {
  const { mode, playerLens, teamSide, season, situation, players, teams } = comparison
  const { playerResults, teamResults, playerProfiles, analytics } = queries
  const isDefense = mode === 'players' && playerLens === 'defense'

  const splitConfig = mode === 'teams' ? TEAM_SPLIT_CONFIG[teamSide] : isDefense ? DEFENSE_SPLIT_CONFIG : PLAYER_SPLIT_CONFIG[playerLens as PlayerCategory]

  const yardageDifferences = mode === 'players' && playerLens === 'receiving'
    ? players.flatMap((player, i) => receivingYardageDifferences(player.id, playerProfiles[i]?.data?.games,
      playerResults[i]?.data as PlayerSplit[] | undefined, season)
      .map(difference => ({ ...difference, playerId: player.id, playerName: playerProfiles[i]?.data?.player_name || player.name || player.id })))
    : []
  const baseMetrics = splitConfig.metrics as Metric<SplitRow>[]
  const metrics = baseMetrics.map(metric => ['yds', 'ypr', 'ytgt'].includes(metric.key) && yardageDifferences.length
    ? { ...metric, sourceNoteId: RECEIVING_YARDAGE_NOTE_ID } : metric)

  const metricGroup = mode === 'teams' ? `team_${teamSide}` : playerLens

  const situations: Situation[] = mode === 'teams' ? TEAM_SITUATIONS : isDefense ? DEFENSE_SITUATIONS : PLAYER_SITUATIONS[playerLens as PlayerCategory]

  const isCareer = mode === 'players' && season === CAREER_SEASON

  const flip = (hib: boolean | undefined) => (mode === 'teams' && teamSide === 'defense' && hib !== undefined) ? !hib : hib

  const aggregateRows = (rows: SplitRow[]): SplitRow | null =>
    isDefense ? aggregateDefenseSplitRows(rows as DefensiveSplit[])
      : mode === 'players' ? aggregatePlayerSplitRows(rows as PlayerSplit[])
        : aggregateTeamSplitRows(rows as TeamSplit[])

  const aggregateValues = (rows: SplitRow[]): SplitRow[] =>
    isDefense ? aggregateDefenseCareerByValue(rows as DefensiveSplit[]) : aggregateCareerByValue(rows as PlayerSplit[])

  const matchesDimension = (s: SplitRow, dim: string): boolean =>
    isDefense ? (s as DefensiveSplit).split_dim === dim
      : mode === 'players' ? ((s as PlayerSplit).category === playerLens && (s as PlayerSplit).split_dim === dim)
        : ((s as TeamSplit).side === teamSide && (s as TeamSplit).split_dim === dim)

  const splitRows: SplitRow[][] = mode === 'players' ? players.map((_, i) => (playerResults[i]?.data ?? []) as SplitRow[]) : teams.map((_, i) => (teamResults[i]?.data ?? []) as TeamSplit[])

  const entities: EntityCard[] = mode === 'players'
    ? players.map((p, i) => { const prof = playerProfiles[i]?.data; return { key: p.id, label: p.name || prof?.player_name || p.id, sub: p.sub || (prof ? [prof.position, prof.team].filter(Boolean).join(' · ') : undefined), headshot: p.headshot ?? prof?.headshot_url, color: entityColor(i) } })
    : teams.map((t, i) => ({ key: t, label: teamName(t), sub: t, logo: teamLogoUrl(t), color: entityColor(i) }))

  const entityCount = entities.length

  const focusData = splitRows[0] ?? []

  const playerGames = mode === 'players' && !isDefense
    ? players.map((_, i) => (playerProfiles[i]?.data?.games ?? [])
      .filter(g => g.game_type === 'REG' && (isCareer || g.season === season))
      .map(g => ({ g, r: gameToSplitRow(g, playerLens as PlayerCategory) }))
      .filter(x => playerLens === 'receiving' ? hasReceivingActivity(x.g) : (x.r.att ?? 0) > 0))
    : []

  const games = playerGames[0] ?? []

  const gameMetrics = baseMetrics.filter(m => m.key !== 'succ' && m.key !== 'cpoe' && m.key !== 'conv')

  const singleEntity = entityCount === 1

  const showDefensiveRanks = mode === 'players' && season !== null && !isCareer && !isDefense

  const defensiveRanks = (() => { const m = new Map<string, number>(); for (const t of analytics.data?.league ?? []) if (t.def_epa_play_rank != null) m.set(t.team, t.def_epa_play_rank); return m })()

  function situationRow(data: SplitRow[]): SplitRow | null {
    const dimKey = situation ? situation.dim : OVERALL_DIM
    let sel = data.filter(s => matchesDimension(s, dimKey))
    if (situation) sel = sel.filter(s => s.split_value === situation.value)
    if (mode === 'teams') return situation ? (sel[0] ?? null) : aggregateRows(sel)
    if (isCareer) return aggregateRows(sel)
    sel = sel.filter(s => (s as PlayerSplit).season === season)
    return situation ? (sel[0] ?? null) : aggregateRows(sel)
  }

  const sectionDims = (mode === 'players' && !isDefense) ? [{ key: 'season', label: 'Season' }, ...splitConfig.dims] : splitConfig.dims

  const defaultOpen = isDefense ? ['vs_play', 'down', 'field_zone'] : mode === 'players' ? ['season', 'down', 'game_script', 'opponent'] : ['down', 'game_script', 'field_zone']

  const gameDims = new Set((mode === 'players' && !isDefense) ? ['season', 'opponent'] : [])
  return {
    mode, playerLens, season, splitConfig, metrics, metricGroup, situations, isCareer, isDefense, flip,
    aggregateRows, aggregateValues, matchesDimension, splitRows, entities, entityCount, focusData, playerGames,
    games, gameMetrics, singleEntity, showDefensiveRanks, defensiveRanks, situationRow, sectionDims, defaultOpen, gameDims, yardageDifferences
  }
}

export type SplitModel = ReturnType<typeof createSplitModel>
