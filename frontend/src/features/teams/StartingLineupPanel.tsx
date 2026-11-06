import { useQuery } from '@tanstack/react-query'
import { teamDepthChartQueryOptions } from '../../api/teams'
import { QueryLoading, QueryFailure } from '../../components/QueryFeedback'

function LineupColumn({ label, rows }: { label: string; rows: { depth_position: string | null; full_name: string | null; position: string | null }[] }) {
  return (
    <div className="p-3">
      <div className="text-[10px] font-bold text-ink-dim uppercase tracking-widest mb-2 px-1">{label}</div>
      <ul className="space-y-0.5">
        {rows.map((r, i) => (
          <li key={`${r.depth_position}-${i}`} className="flex items-center gap-2 px-1 py-1 text-sm">
            <span className="shrink-0 text-[10px] font-bold text-ink-dim w-10 uppercase tracking-wider">
              {r.depth_position ?? r.position ?? ''}
            </span>
            <span className="flex-1 min-w-0 text-ink-mid truncate">{r.full_name ?? '—'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function StartingLineupPanel({ team, season }: { team: string; season: number }) {
  const depthQuery = useQuery(teamDepthChartQueryOptions(team, season))
  const { data: depth = [], isPending } = depthQuery
  if (isPending) return <QueryLoading>Loading starting lineup…</QueryLoading>

  const starters = depth.filter(d => d.depth_team === '1')
  const offense = starters.filter(d => d.formation === 'Offense')
  const defense = starters.filter(d => d.formation === 'Defense')

  if (offense.length === 0 && defense.length === 0) return (
    <div>
      <QueryFailure resource="starting lineup" error={depthQuery.error} hasData={depthQuery.data !== undefined} onRetry={() => void depthQuery.refetch()} />
      {!depthQuery.error && <p className="text-sm text-ink-dim">No starting lineup is available for this season.</p>}
    </div>
  )

  const week = depth[0]?.week
  const headline = week ? `Week ${week} Starting Lineup` : 'Starting Lineup'

  return (
    <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden">
      <QueryFailure resource="starting lineup" error={depthQuery.error} hasData onRetry={() => void depthQuery.refetch()} />
      <div className="px-4 py-2.5 border-b border-surface-line flex items-center justify-between">
        <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">{headline}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-surface-line/60">
        {offense.length > 0 && <LineupColumn label="Offense" rows={offense} />}
        {defense.length > 0 && <LineupColumn label="Defense" rows={defense} />}
      </div>
    </div>
  )
}
