import type { MetricSpec } from './types'

function rankClasses(rank: number): string {
  if (rank <= 6)  return 'text-green-300 bg-green-950/60 border-green-800/60'
  if (rank <= 13) return 'text-data-win bg-data-win/40 border-data-win/40'
  if (rank <= 19) return 'text-ink-mid bg-surface-raise/60 border-surface-line/50'
  if (rank <= 26) return 'text-data-loss bg-data-loss/40 border-data-loss/40'
  return 'text-red-300 bg-red-950/60 border-red-800/60'
}

function RankBadge({ rank }: { rank: number | null | undefined }) {
  if (rank == null) return <span className="text-ink-dim text-xs">—</span>
  return (
    <span className={`inline-block text-xs font-bold tabular-nums rounded px-1.5 py-0.5 border ${rankClasses(rank)}`}>
      #{rank}
    </span>
  )
}

function MetricRow({ m }: { m: MetricSpec }) {
  const hasValue = m.value != null && Number.isFinite(m.value as number)
  return (
    <tr className="border-t border-surface-line/60 hover:bg-surface-raise/30 transition-colors">
      <td className="py-1.5 pl-4 pr-2 text-ink-mid text-xs whitespace-nowrap" title={m.hint}>{m.label}</td>
      <td className="py-1.5 px-2 text-right tabular-nums text-ink text-sm font-semibold whitespace-nowrap">
        {hasValue ? m.fmt(m.value as number) : <span className="text-ink-dim">—</span>}
      </td>
      <td className="py-1.5 pr-4 pl-2 text-right whitespace-nowrap">
        <RankBadge rank={m.rank} />
      </td>
    </tr>
  )
}

export default function MetricPanel({ title, accent, metrics }: { title: string; accent: string; metrics: MetricSpec[] }) {
  return (
    <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-surface-line flex items-center gap-2">
        <span className={`text-xs font-bold uppercase tracking-wider ${accent}`}>{title}</span>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {metrics.map(m => <MetricRow key={m.key} m={m} />)}
        </tbody>
      </table>
    </div>
  )
}
