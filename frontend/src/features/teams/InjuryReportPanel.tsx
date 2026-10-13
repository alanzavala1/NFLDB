import { useQuery } from '@tanstack/react-query'
import { teamInjuriesQueryOptions } from '../../api/teams'
import { QueryLoading, QueryFailure } from '../../components/QueryFeedback'

function injuryToneClasses(status: string | null | undefined): string {
  switch (status) {
    case 'Out':           return 'bg-data-loss/40 border-data-loss/70 text-data-loss'
    case 'Doubtful':      return 'bg-data-loss/40 border-data-loss/70 text-data-loss'
    case 'Questionable':  return 'bg-surface-raise/40 border-data-loss/40 text-data-loss'
    case 'Probable':      return 'bg-data-win/40 border-data-win/70 text-data-win'
    default:              return 'bg-surface-card border-surface-line text-ink-mid'
  }
}

export default function InjuryReportPanel({ team, season }: { team: string; season: number }) {
  const injuriesQuery = useQuery(teamInjuriesQueryOptions(team, season))
  const { data: injuries = [], isPending } = injuriesQuery
  if (isPending) return <QueryLoading>Loading injury report…</QueryLoading>
  if (injuries.length === 0) return (
    <div>
      <QueryFailure resource="injury report" error={injuriesQuery.error} hasData={injuriesQuery.data !== undefined} onRetry={() => void injuriesQuery.refetch()} />
      {!injuriesQuery.error && <p className="text-sm text-ink-dim">No injury report is available for this season.</p>}
    </div>
  )

  // injuries are already ordered server-side by severity
  const headline = `Week ${injuries[0].week} Injury Report`

  return (
    <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden">
      <QueryFailure resource="injury report" error={injuriesQuery.error} hasData onRetry={() => void injuriesQuery.refetch()} />
      <div className="px-4 py-2.5 border-b border-surface-line flex items-center justify-between">
        <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">{headline}</span>
        <span className="text-[10px] font-bold text-ink-dim uppercase tracking-widest">{injuries.length} listed</span>
      </div>
      <ul className="divide-y divide-surface-line/60">
        {injuries.map((inj, i) => (
          <li key={`${inj.gsis_id}-${i}`} className="px-4 py-2.5 flex items-center gap-3 text-sm">
            <span className={`shrink-0 inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${injuryToneClasses(inj.report_status)}`}>
              {inj.report_status ?? '—'}
            </span>
            <span className="shrink-0 text-[11px] text-ink-dim w-9 text-center font-bold">{inj.position ?? ''}</span>
            <span className="flex-1 min-w-0 text-ink truncate">{inj.full_name ?? '—'}</span>
            <span className="text-xs text-ink-dim truncate max-w-[40%]">
              {inj.report_primary_injury ?? '—'}
              {inj.report_secondary_injury && <span className="text-ink-dim"> · {inj.report_secondary_injury}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
