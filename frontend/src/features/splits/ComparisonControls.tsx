import { useState } from 'react'
import Card from '../../components/Card'
import { CURRENT_NFL_SEASON } from '../../api'
import type { useComparisonState } from './useComparisonState'
import type { EntityCard, ComparisonMode, PlayerLens, PlayerCategory, TeamSide } from './types'
import { PLAYER_SPLIT_CONFIG } from './playerConfig'
import { TEAM_SPLIT_CONFIG } from './teamConfig'
import { CAREER_SEASON } from './constants'
import { SEASONS } from './presets'
import { SegmentControl } from './Controls'
import { AddEntity } from './AddEntity'
import { MatchupHeader } from './MatchupHeader'

const selectCls = 'min-h-10 bg-surface-card border border-surface-line text-ink text-xs rounded-lg px-2.5 py-2 focus-visible:outline-2 focus-visible:outline-indigo-400 focus-visible:outline-offset-2'

export function ComparisonControls({ comparison, entities }: {
  comparison: ReturnType<typeof useComparisonState>; entities: EntityCard[]
}) {
  const { mode, setMode, playerLens, setPlayerLens, teamSide, setTeamSide, season, setSeason, setSituation,
    setPlayers, setTeams, addEntity } = comparison
  const entityCount = entities.length
  const [copied, setCopied] = useState(false)
  return (<Card title="Splits" className="mb-5" allowOverflow action={entityCount > 0 ? (
    <button onClick={() => { navigator.clipboard?.writeText(window.location.href); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
      className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-mid rounded-lg border border-surface-line px-3 py-1.5 hover:border-indigo-500/60 hover:text-ink transition-colors">
      {copied ? '✓ Copied' : 'Copy link'}
    </button>
  ) : undefined}>
    <div className="border-t border-surface-line px-4 py-4 space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_auto_auto]">
        <div className="min-w-0 space-y-2">
          <p className="text-[11px] font-bold text-ink-dim uppercase tracking-wider">Compare</p>
          <div className="flex flex-wrap items-center gap-2">
            <SegmentControl<ComparisonMode> value={mode} options={[{ value: 'players', label: 'Players' }, { value: 'teams', label: 'Teams' }]}
              onChange={m => { setMode(m); setSituation(null); if (m === 'teams' && season === CAREER_SEASON) setSeason(CURRENT_NFL_SEASON) }} />
            <AddEntity mode={mode} onAdd={addEntity} />
          </div>
        </div>
        {entityCount > 0 && <>
          <div className="min-w-0 space-y-2">
            <p className="text-[11px] font-bold text-ink-dim uppercase tracking-wider">Stat category</p>
            {mode === 'players'
              ? <SegmentControl<PlayerLens> value={playerLens} options={[...(Object.keys(PLAYER_SPLIT_CONFIG) as PlayerCategory[]).map(c => ({ value: c as PlayerLens, label: PLAYER_SPLIT_CONFIG[c].label })), { value: 'defense' as PlayerLens, label: 'Defense' }]} onChange={c => { setPlayerLens(c); setSituation(null) }} />
              : <SegmentControl<TeamSide> value={teamSide} options={(Object.keys(TEAM_SPLIT_CONFIG) as TeamSide[]).map(s => ({ value: s, label: TEAM_SPLIT_CONFIG[s].label }))} onChange={s => { setTeamSide(s); setSituation(null) }} />}
          </div>
          <label className="flex flex-col items-start gap-2">
            <span className="text-[11px] font-bold text-ink-dim uppercase tracking-wider">Season</span>
            <select value={season} onChange={e => setSeason(Number(e.target.value))} className={selectCls}>
              {mode === 'players' && <option value={CAREER_SEASON}>Career</option>}
              {SEASONS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </>}
      </div>
      {entityCount > 0 && <MatchupHeader entities={entities} onRemove={k => mode === 'players' ? setPlayers(xs => xs.filter(x => x.id !== k)) : setTeams(xs => xs.filter(x => x !== k))} />}
    </div>
    {entityCount === 0 && (
      <p className="border-t border-surface-line px-4 py-2.5 text-xs text-ink-dim">
        Compare head-to-head, then explore every split at once — by season (down to each game), down, game script, opponent and more. Every view has a shareable link.
      </p>
    )}
  </Card>)
}
