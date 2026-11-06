import { useQuery } from '@tanstack/react-query'
import { teamAnalyticsQueryOptions } from '../../api/teamAnalytics'
import { QueryLoading, QueryFailure } from '../../components/QueryFeedback'
import { buildOffenseMetrics, buildDefenseMetrics, buildOverallMetrics } from './analyticsMetrics'
import MetricPanel from './MetricPanel'

export default function TeamAnalytics({ team, season }: { team: string; season: number }) {
  const analyticsQuery = useQuery(teamAnalyticsQueryOptions(season))
  const focal = analyticsQuery.data?.league.find(row => row.team === team)

  if (analyticsQuery.isPending) {
    return (
      <div className="mb-4 bg-surface-card border border-surface-line rounded-xl px-4 py-8 text-center text-ink-dim text-sm">
        <QueryLoading>Loading analytics…</QueryLoading>
      </div>
    )
  }
  if (!focal) {
    return (
      <div className="mb-4 bg-surface-card border border-surface-line rounded-xl px-4 py-6 text-center text-ink-dim text-sm">
        <QueryFailure resource="team analytics" error={analyticsQuery.error} hasData={analyticsQuery.data !== undefined} onRetry={() => void analyticsQuery.refetch()} />
        {analyticsQuery.data && <p>Analytics unavailable for this season.</p>}
      </div>
    )
  }

  const offense = buildOffenseMetrics(focal)
  const defense = buildDefenseMetrics(focal)
  const overall = buildOverallMetrics(focal)

  return (
    <div className="mb-4">
      <QueryFailure resource="team analytics" error={analyticsQuery.error} hasData onRetry={() => void analyticsQuery.refetch()} />
      <div className="flex items-end justify-between mb-2 px-1">
        <div>
          <h3 className="text-sm font-bold text-ink uppercase tracking-wider">Team Analytics</h3>
          <p className="text-xs text-ink-dim mt-0.5">League rank out of 32 · regular season · 1 = best</p>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <MetricPanel title="Offense"          accent="text-ink-dim"  metrics={offense} />
        <MetricPanel title="Defense"          accent="text-data-loss"     metrics={defense} />
        <div className="space-y-4">
          <MetricPanel title="Overall"        accent="text-ink-mid"   metrics={overall} />
          <div className="bg-surface-card border border-surface-line rounded-xl p-4 text-xs text-ink-dim">
            <div className="grid grid-cols-2 gap-y-1.5">
              <span>Record</span><span className="text-right text-ink-mid font-semibold">{focal.wins}-{focal.losses}{focal.ties ? `-${focal.ties}` : ''}</span>
              <span>Games</span><span className="text-right text-ink-mid">{focal.games}</span>
              <span>Points For</span><span className="text-right text-ink-mid">{focal.pf_total}</span>
              <span>Points Against</span><span className="text-right text-ink-mid">{focal.pa_total}</span>
              <span>Off Drives</span><span className="text-right text-ink-mid">{focal.total_drives ?? '—'}</span>
              <span>Def Drives</span><span className="text-right text-ink-mid">{focal.total_drives_allowed ?? '—'}</span>
              <span>Giveaways</span><span className="text-right text-ink-mid">{focal.off_turnovers_total}</span>
              <span>Takeaways</span><span className="text-right text-ink-mid">{focal.def_takeaways_total}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
