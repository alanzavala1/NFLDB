import type { SortDir } from './types'
import type { TeamProfile } from '../../types'
import { useState, useEffect } from 'react'
import { countTeamGames } from './selectors'
import { teamLogoUrl, teamName } from '../../utils/teams'
import StatsSections from './StatsSections'

const DEFAULT_SORTS = {
  passing:   { key: 'yds', dir: 'desc' as SortDir },
  rushing:   { key: 'yds', dir: 'desc' as SortDir },
  receiving: { key: 'yds', dir: 'desc' as SortDir },
  scrimmage: { key: 'scrim', dir: 'desc' as SortDir },
  defense:   { key: 'tot', dir: 'desc' as SortDir },
}

export default function FullStatsModal({ profile, onClose }: { profile: TeamProfile; onClose: () => void }) {
  const hasPlayoffs = profile.playoff_leaders?.length > 0
  const [regSorts, setRegSorts]  = useState({ ...DEFAULT_SORTS })
  const [postSorts, setPostSorts] = useState({ ...DEFAULT_SORTS })
  const regGames = countTeamGames(profile, 'reg')
  const postGames = countTeamGames(profile, 'post')

  function makeSort(setSorts: typeof setRegSorts) {
    return (section: string, key: string) => setSorts(prev => {
      const cur = prev[section as keyof typeof prev]
      return { ...prev, [section]: { key, dir: cur.key === key && cur.dir === 'desc' ? 'asc' : 'desc' } }
    })
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-surface-bg">
      <div className="flex items-center gap-2 px-6 py-4 border-b border-surface-line shrink-0">
        <span className="font-black text-base tracking-tight select-none shrink-0">
          <span className="text-ink">NFL</span><span className="text-ink-mid">DB</span>
        </span>
        <span className="text-ink-dim">/</span>
        <img src={teamLogoUrl(profile.team)} alt={profile.team} className="w-5 h-5 object-contain shrink-0" />
        <span className="text-ink-mid text-sm">{teamName(profile.team)}</span>
        <span className="text-ink-dim">/</span>
        <span className="text-ink-mid text-sm">{profile.season} Stats</span>
        <button onClick={onClose}
          className="ml-auto shrink-0 text-sm text-ink-mid hover:text-ink bg-surface-raise hover:bg-surface-raise border border-surface-line rounded-lg px-3 py-1.5 transition-colors"
        >
          Close
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-6xl mx-auto w-full">
        <div className="text-xs font-bold text-ink-dim uppercase tracking-widest mb-5">Regular Season</div>
        <StatsSections leaders={profile.leaders} sorts={regSorts} onSort={makeSort(setRegSorts)} onClose={onClose} games={regGames} />

        {hasPlayoffs && (
          <>
            <div className="text-xs font-bold text-ink-dim uppercase tracking-widest mb-5 mt-4">Postseason</div>
            <StatsSections leaders={profile.playoff_leaders} sorts={postSorts} onSort={makeSort(setPostSorts)} onClose={onClose} games={postGames} />
          </>
        )}
      </div>
    </div>
  )
}
