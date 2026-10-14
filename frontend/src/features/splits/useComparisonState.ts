import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useExampleSearch } from '../search/useExampleSearch'
import { selectedSeason } from '../../utils/seasons'
import type { SearchResult } from '../../types'
import type { ComparisonMode, PlayerLens, PlayerEntity, TeamSide, Situation, Example } from './types'
import { PLAYER_SITUATIONS } from './playerConfig'
import { TEAM_SITUATIONS } from './teamConfig'
import { DEFENSE_SITUATIONS } from './defenseConfig'
import { CAREER_SEASON } from './constants'

function entityIds(params: URLSearchParams, key: 'p' | 't') {
  return [...new Set((params.get(key) ?? '').split(',').map(id => id.trim()).filter(Boolean))].slice(0, 6)
}

function playerDetails(result: SearchResult): PlayerEntity {
  return { id: result.id, name: result.name, headshot: result.headshot_url, sub: [result.position, result.team].filter(Boolean).join(' · ') }
}

export function useComparisonState(availableYears: number[]) {
  const [searchParams, setSearchParams] = useSearchParams()
  // Search supplies display metadata; selected IDs always come from the URL.
  const [details, setDetails] = useState<Record<string, PlayerEntity>>({})
  const resolveExamplePlayers = useExampleSearch(searchParams.toString())
  const mode: ComparisonMode = searchParams.get('mode') === 'teams' ? 'teams' : 'players'
  const category = searchParams.get('cat')
  const playerLens: PlayerLens = category === 'rushing' || category === 'receiving' || category === 'defense' ? category : 'passing'
  const teamSide: TeamSide = searchParams.get('side') === 'defense' ? 'defense' : 'offense'
  const players = entityIds(searchParams, 'p').map(id => details[id] ?? { id, name: '' })
  const teams = entityIds(searchParams, 't')
  const requestedSeason = searchParams.get('season')
  const season = !availableYears.length ? null
    : mode === 'players' && (requestedSeason === null || requestedSeason === String(CAREER_SEASON)) ? CAREER_SEASON
      : selectedSeason(requestedSeason, availableYears)
  const situations = mode === 'teams' ? TEAM_SITUATIONS : playerLens === 'defense' ? DEFENSE_SITUATIONS : PLAYER_SITUATIONS[playerLens]
  const situation = situations.find(s => `${s.dim}:${s.value}` === searchParams.get('sit')) ?? null

  function updateParams(edit: (next: URLSearchParams) => void) {
    const next = new URLSearchParams(searchParams)
    edit(next)
    if (next.toString() !== searchParams.toString()) setSearchParams(next)
  }

  function setMode(nextMode: ComparisonMode) {
    if (nextMode === mode) return
    updateParams(next => {
      next.set('mode', nextMode)
      next.delete('sit')
      if (nextMode === 'teams' && requestedSeason === String(CAREER_SEASON)) next.delete('season')
    })
  }

  function setPlayerLens(lens: PlayerLens) {
    if (lens === playerLens) return
    updateParams(next => { next.set('cat', lens); next.delete('sit') })
  }

  function setTeamSide(side: TeamSide) {
    if (side === teamSide) return
    updateParams(next => { next.set('side', side); next.delete('sit') })
  }

  function setSeason(year: number) {
    if (!availableYears.includes(year) && !(mode === 'players' && year === CAREER_SEASON)) return
    updateParams(next => next.set('season', String(year)))
  }

  function setSituation(selection: Situation | null) {
    updateParams(next => {
      if (selection) next.set('sit', `${selection.dim}:${selection.value}`)
      else next.delete('sit')
    })
  }

  function removeEntity(id: string) {
    updateParams(next => {
      const key = mode === 'players' ? 'p' : 't'
      const remaining = entityIds(next, key).filter(value => value !== id)
      if (remaining.length) next.set(key, remaining.join(','))
      else next.delete(key)
    })
  }

  function addEntity(result: SearchResult) {
    if (result.type === 'player') setDetails(previous => ({ ...previous, [result.id]: playerDetails(result) }))
    updateParams(next => {
      const key = result.type === 'team' ? 't' : 'p'
      next.set(key, [...new Set([...entityIds(next, key), result.id])].slice(0, 6).join(','))
    })
  }

  async function loadExample(example: Example) {
    if (example.teams) {
      updateParams(next => { next.set('t', [...new Set(example.teams)].slice(0, 6).join(',')); next.delete('sit') })
      return
    }
    const results = await resolveExamplePlayers(example.names ?? [])
    if (results === null) return
    setDetails(previous => ({ ...previous, ...Object.fromEntries(results.map(result => [result.id, playerDetails(result)])) }))
    updateParams(next => {
      next.delete('sit')
      if (example.cat) next.set('cat', example.cat)
      const ids = [...new Set([...entityIds(next, 'p'), ...results.map(result => result.id)])].slice(0, 6)
      if (ids.length) next.set('p', ids.join(','))
    })
  }

  return {
    mode, setMode, players, teams, playerLens, setPlayerLens, teamSide, setTeamSide,
    season, setSeason, situation, setSituation, availableYears, removeEntity, addEntity, loadExample,
  }
}
