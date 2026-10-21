import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import type { PlayerComparable } from '../../types'
import { playerComparablesQueryOptions } from '../../api/players'
import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import { teamLogoUrl } from '../../utils/teams'
import ReceivingDataNote from '../../components/ReceivingDataNote'
import { hasUnavailableTargets } from '../../utils/receiving'

function simColor(s: number) {
  if (s >= 95) return 'text-data-win'
  if (s >= 88) return 'text-green-400'
  if (s >= 80) return 'text-gold'
  return 'text-ink-dim'
}

function simBar(s: number) {
  if (s >= 95) return 'bg-data-win'
  if (s >= 88) return 'bg-green-500'
  if (s >= 80) return 'bg-gold'
  return 'bg-surface-raise'
}

function ComparableCard({ p, pos }: { p: PlayerComparable; pos: string }) {
  const era = p.first_season === p.last_season ? `${p.first_season}` : `${p.first_season}–${p.last_season}`
  let statLine = ''
  if (pos === 'QB') {
    const ypa = p.att > 0 ? (p.pass_yards / p.att).toFixed(1) : '—'
    statLine = `${p.pass_yards.toLocaleString()} YDS · ${p.pass_tds} TD · ${p.ints} INT · ${ypa} Y/A`
  } else if (pos === 'RB') {
    const ypc = p.carries > 0 ? (p.rush_yards / p.carries).toFixed(1) : '—'
    statLine = `${p.rush_yards.toLocaleString()} YDS · ${p.rush_tds} TD · ${ypc} Y/C`
  } else if (pos === 'WR') {
    statLine = `${p.rec_yards.toLocaleString()} YDS · ${p.rec_tds} TD · ${p.targets ?? '—'} TGT`
  } else {
    statLine = `${p.games}G · ${p.first_season}–${p.last_season}`
  }

  return (
    <Link to={`/players/${p.player_id}`} className="block bg-surface-card border border-surface-line rounded-xl p-4 hover:border-surface-line hover:bg-surface-raise/60 transition-all group">
      <div className="flex items-start gap-3 mb-3">
        {p.headshot_url
          ? <img src={p.headshot_url} className="w-12 h-12 rounded-full object-cover object-top bg-surface-raise shrink-0" alt="" />
          : <div className="w-12 h-12 rounded-full bg-surface-raise shrink-0" />
        }
        <div className="min-w-0 flex-1">
          <div className="font-bold text-ink text-sm leading-tight group-hover:text-indigo-400 transition-colors truncate">{p.player_name}</div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-xs text-ink-dim font-medium">{p.position ?? '—'}</span>
            {p.team && (
              <>
                <span className="text-ink-dim">·</span>
                <img src={teamLogoUrl(p.team)} className="w-4 h-4 object-contain opacity-70" alt="" />
                <span className="text-xs text-ink-dim">{p.team}</span>
              </>
            )}
          </div>
          <div className="text-xs text-ink-dim mt-0.5">{era} · {p.games}G</div>
        </div>
      </div>

      <div className="mb-2">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] text-ink-dim uppercase tracking-wider">Similarity</span>
          <span className={`text-sm font-black tabular-nums ${simColor(p.similarity)}`}>{p.similarity}%</span>
        </div>
        <div className="h-1.5 bg-surface-raise rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${simBar(p.similarity)}`} style={{ width: `${p.similarity}%` }} />
        </div>
      </div>

      <div className="text-[11px] text-ink-dim leading-relaxed">{statLine}</div>
    </Link>
  )
}

export default function ComparablesSection({ playerId, pos }: { playerId: string; pos: string }) {
  const comparablesQuery = useQuery(playerComparablesQueryOptions(playerId))
  const { data: comps = [], isPending: loading } = comparablesQuery

  if (loading) return (
    <div className="mt-8">
      <div className="text-xs font-bold text-ink-dim uppercase tracking-widest mb-3">Similar Players</div>
      <QueryLoading>Loading similar players…</QueryLoading>
    </div>
  )
  return (
    <div className="mt-8">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-xs font-bold text-ink-dim uppercase tracking-widest">Similar Players</span>
        <span className="text-xs text-ink-dim">Cosine similarity on career rate stats · same position group</span>
      </div>
      <QueryFailure resource="similar players" error={comparablesQuery.error} hasData={comparablesQuery.data !== undefined} onRetry={() => void comparablesQuery.refetch()} />
      <ReceivingDataNote unavailable={pos === 'WR' && hasUnavailableTargets(comps)} career />
      {!comps.length && !comparablesQuery.error && <p className="text-sm text-ink-dim">No similar players are available.</p>}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {comps.map(p => <ComparableCard key={p.player_id} p={p} pos={pos} />)}
      </div>
    </div>
  )
}
