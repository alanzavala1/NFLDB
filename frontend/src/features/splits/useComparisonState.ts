import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import type { SearchResult } from '../../types'
import type { ComparisonMode, PlayerLens, PlayerEntity, TeamSide, Situation, Example } from './types'
import { PLAYER_SITUATIONS } from './playerConfig'
import { TEAM_SITUATIONS } from './teamConfig'
import { DEFENSE_SITUATIONS } from './defenseConfig'
import { CAREER_SEASON } from './constants'

export function useComparisonState() {
  // Initial state is hydrated from the URL so any comparison is shareable.
  const [, setSearchParams] = useSearchParams()
  const [initialParams] = useState(() => new URLSearchParams(window.location.search))
  const initialMode: ComparisonMode = initialParams.get('mode') === 'teams' ? 'teams' : 'players'
  const initialCategory: PlayerLens = (['passing', 'rushing', 'receiving', 'defense'] as string[]).includes(initialParams.get('cat') ?? '') ? initialParams.get('cat') as PlayerLens : 'passing'

  const [mode, setMode] = useState<ComparisonMode>(initialMode)
  const [players, setPlayers] = useState<PlayerEntity[]>(() => {
    const ids = initialParams.get('p'); return ids ? ids.split(',').filter(Boolean).slice(0, 6).map(id => ({ id, name: '' })) : []
  })
  const [teams, setTeams] = useState<string[]>(() => {
    const t = initialParams.get('t'); return t ? t.split(',').filter(Boolean).slice(0, 6) : []
  })
  const [playerLens, setPlayerLens] = useState<PlayerLens>(initialCategory)
  const [teamSide, setTeamSide] = useState<TeamSide>(initialParams.get('side') === 'defense' ? 'defense' : 'offense')
  const [season, setSeason] = useState<number>(() => {
    const s = initialParams.get('season'); const n = s == null ? CAREER_SEASON : Number(s); return Number.isFinite(n) ? n : CAREER_SEASON
  })
  const [situation, setSituation] = useState<Situation | null>(() => {
    const sit = initialParams.get('sit'); if (!sit) return null
    const [dim, value] = sit.split(':')
    const list = initialMode === 'teams' ? TEAM_SITUATIONS : initialCategory === 'defense' ? DEFENSE_SITUATIONS : PLAYER_SITUATIONS[initialCategory]
    return list.find(s => s.dim === dim && s.value === value) ?? null
  })

  // Reflect the live comparison back into the URL (replace, so it doesn't
  // stack history) — the Copy-link button just grabs window.location.href.
  useEffect(() => {
    const p = new URLSearchParams()
    p.set('mode', mode)
    if (mode === 'players') { if (players.length) p.set('p', players.map(x => x.id).join(',')); p.set('cat', playerLens) }
    else { if (teams.length) p.set('t', teams.join(',')); p.set('side', teamSide) }
    p.set('season', String(season))
    if (situation) p.set('sit', `${situation.dim}:${situation.value}`)
    setSearchParams(p, { replace: true })
  }, [mode, players, teams, playerLens, teamSide, season, situation, setSearchParams])

  function addEntity(r: SearchResult) {
    if (r.type === 'team') setTeams(t => t.includes(r.id) ? t : [...t, r.id].slice(0, 6))
    else setPlayers(p => p.some(x => x.id === r.id) ? p : [...p, { id: r.id, name: r.name, headshot: r.headshot_url, sub: [r.position, r.team].filter(Boolean).join(' · ') }].slice(0, 6))
  }

  async function loadExample(ex: Example) {
    setSituation(null)
    if (ex.teams) { setTeams(ex.teams.slice(0, 6)); return }
    if (ex.cat) setPlayerLens(ex.cat)
    for (const name of ex.names ?? []) {
      try {
        const res = await api.search(name)
        const r = res.find(x => x.type === 'player')
        if (r) addEntity(r)
      } catch { /* example is best-effort; search failures just skip */ }
    }
  }

  return {
    mode, setMode, players, setPlayers, teams, setTeams, playerLens, setPlayerLens, teamSide, setTeamSide,
    season, setSeason, situation, setSituation, addEntity, loadExample
  }
}
