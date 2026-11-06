import type { TeamProfile } from '../../types'
import { useQuery } from '@tanstack/react-query'
import { teamRosterQueryOptions } from '../../api/teams'
import { useEffect } from 'react'
import { teamLogoUrl, teamName } from '../../utils/teams'
import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import { Link } from 'react-router-dom'

const ROSTER_GROUPS = [
  { label: 'Quarterbacks',   positions: new Set(['QB']) },
  { label: 'Running Backs',  positions: new Set(['RB', 'FB', 'HB']) },
  { label: 'Wide Receivers', positions: new Set(['WR']) },
  { label: 'Tight Ends',     positions: new Set(['TE']) },
  { label: 'Offensive Line', positions: new Set(['C', 'G', 'T', 'OT', 'OG', 'OL', 'RT', 'LT', 'RG', 'LG', 'LS']) },
  { label: 'Defensive Line', positions: new Set(['DE', 'DT', 'NT', 'EDGE', 'DL']) },
  { label: 'Linebackers',    positions: new Set(['LB', 'ILB', 'OLB', 'MLB']) },
  { label: 'Cornerbacks',    positions: new Set(['CB', 'DB']) },
  { label: 'Safeties',       positions: new Set(['S', 'SS', 'FS', 'SAF']) },
  { label: 'Kickers',        positions: new Set(['K']) },
  { label: 'Punters',        positions: new Set(['P']) },
  { label: 'Special Teams',  positions: new Set(['KR', 'PR', 'ST']) },
]

const ROSTER_MAPPED = new Set(ROSTER_GROUPS.flatMap(g => [...g.positions]))

export default function RosterModal({ profile, onClose }: { profile: TeamProfile; onClose: () => void }) {
  const rosterQuery = useQuery(teamRosterQueryOptions(profile.team, profile.season))
  const roster = rosterQuery.data ?? []
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const grouped = ROSTER_GROUPS
    .map(g => ({ label: g.label, players: roster.filter(p => g.positions.has(p.position ?? '')) }))
    .filter(g => g.players.length > 0)
  const other = roster.filter(p => !ROSTER_MAPPED.has(p.position ?? ''))

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
        <span className="text-ink-mid text-sm">{profile.season} Roster</span>
        <button onClick={onClose} className="ml-auto shrink-0 text-sm text-ink-mid hover:text-ink bg-surface-raise hover:bg-surface-raise border border-surface-line rounded-lg px-3 py-1.5 transition-colors">
          Close
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-5xl mx-auto w-full">
        <QueryFailure resource="roster" error={rosterQuery.error} hasData={rosterQuery.data !== undefined} onRetry={() => void rosterQuery.refetch()} />
        {rosterQuery.isPending ? <QueryLoading>Loading roster…</QueryLoading> : !roster.length
          ? !rosterQuery.error && <p className="text-ink-dim">No roster data available for this season.</p>
          : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[...grouped, ...(other.length > 0 ? [{ label: 'Other', players: other }] : [])].map(g => (
                <div key={g.label} className="bg-surface-card border border-surface-line rounded-xl overflow-hidden">
                  <div className="px-4 py-2.5 border-b border-surface-line">
                    <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">{g.label}</span>
                  </div>
                  <div className="divide-y divide-surface-line/60">
                    {g.players.map(p => (
                      <Link key={p.player_id} to={`/players/${p.player_id}`} onClick={onClose}
                        className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-raise/40 transition-colors group">
                        {p.headshot_url
                          ? <img src={p.headshot_url} alt={p.player_name} className="w-8 h-8 rounded-full object-cover shrink-0 bg-surface-raise" />
                          : <div className="w-8 h-8 rounded-full bg-surface-raise shrink-0 flex items-center justify-center text-xs text-ink-dim">{p.player_name[0]}</div>
                        }
                        <div className="min-w-0">
                          <div className="text-sm text-indigo-400 group-hover:underline font-medium truncate">{p.player_name}</div>
                          {p.jersey_number != null && <div className="text-xs text-ink-dim">#{p.jersey_number}</div>}
                        </div>
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )
        }
      </div>
    </div>
  )
}
