import { useId } from 'react'
import type { Metric, SplitRow } from './types'

function UnavailableStat({ label, reason }: { label: string; reason: string }) {
  const id = useId()
  return <>
    <button type="button" popoverTarget={id} title={reason} aria-label={`${label} unavailable. Show explanation`}
      className="inline-flex min-h-8 min-w-9 items-center justify-end gap-1 rounded text-ink-dim hover:text-ink focus-visible:outline-2 focus-visible:outline-indigo-400">
      — <span aria-hidden="true" className="text-[10px]">ⓘ</span>
    </button>
    <div id={id} popover="auto" role="dialog" aria-label={`${label} availability`}
      className="fixed inset-0 m-auto max-h-[80vh] w-[min(24rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-surface-line bg-surface-card p-4 text-left text-sm font-normal whitespace-normal text-ink shadow-xl backdrop:bg-black/30">
      <p className="font-semibold">{label} unavailable</p>
      <p className="mt-2 leading-relaxed text-ink-mid">{reason}</p>
      <button type="button" popoverTarget={id} popoverTargetAction="hide" className="mt-3 min-h-10 rounded px-3 text-indigo-300 hover:bg-surface-raise focus-visible:outline-2 focus-visible:outline-indigo-400">Close</button>
    </div>
  </>
}

export function MetricValue({ metric, row, value }: { metric: Metric<SplitRow>; row: SplitRow | null | undefined; value: number | null }) {
  if (value != null) return metric.fmt(value)
  if (row && metric.unavailableReason) return <UnavailableStat label={metric.label} reason={metric.unavailableReason(row)} />
  return '—'
}
