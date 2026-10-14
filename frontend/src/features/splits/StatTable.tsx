import { useMemo, useState } from 'react'
import type { SplitTableRow, TableSort, Metric, SplitRow } from './types'
import { bestSet, splitVolume } from './tableRanking'

// A sortable table: rows (entities or split values) × metric columns.
export function StatTable({ firstCol, rows, total, metrics, flip, hasDefRk, defaultSort, naturalSort, onToggleExpand }: {
  firstCol: string
  rows: SplitTableRow[]
  total?: SplitRow | null
  metrics: Metric<SplitRow>[]
  flip: (hib: boolean | undefined) => boolean | undefined
  hasDefRk?: boolean
  defaultSort?: TableSort | null
  naturalSort?: boolean
  onToggleExpand?: (key: string) => void
}) {
  const [sort, setSort] = useState<TableSort | null>(defaultSort ?? null)
  const metricByKey = useMemo(() => Object.fromEntries(metrics.map(m => [m.key, m])), [metrics])

  const sorted = useMemo(() => {
    const arr = [...rows]
    if (sort) {
      const val = (r: SplitTableRow): number | null => sort.key === '__defrk' ? (r.defRk ?? null) : (r.row ? metricByKey[sort.key]?.value(r.row) ?? null : null)
      arr.sort((a, b) => {
        const av = val(a), bv = val(b)
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        return sort.dir === 'asc' ? av - bv : bv - av
      })
    } else if (naturalSort) {
      arr.sort((a, b) => ((a.row?.sort_order ?? 9999) - (b.row?.sort_order ?? 9999)) || (splitVolume(b.row) - splitVolume(a.row)))
    }
    return arr
  }, [rows, sort, naturalSort, metricByKey])

  const colBest = useMemo(() => {
    const m = new Map<string, Set<number>>()
    const visible = sorted.filter(r => !r.sub)
    for (const met of metrics) m.set(met.key, bestSet(visible.map(r => r.row ? met.value(r.row) : null), flip(met.higherIsBetter)))
    return m
  }, [sorted, metrics, flip])

  const clickSort = (key: string, dDir: 'asc' | 'desc' = 'desc') => setSort(s => s && s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: dDir })
  const arrow = (key: string) => sort?.key === key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''
  const visibleRows = sorted.filter(r => !r.sub)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b-2 border-surface-line">
            <th className="py-2 pl-4 pr-3 text-[11px] font-bold text-ink-mid uppercase tracking-wider text-left whitespace-nowrap">{firstCol}</th>
            {hasDefRk && <th onClick={() => clickSort('__defrk', 'asc')} className="py-2 px-3 text-[11px] font-bold text-ink-dim/70 uppercase tracking-wider text-left whitespace-nowrap cursor-pointer hover:text-data-loss select-none">Def Rk{arrow('__defrk')}</th>}
            {metrics.map(m => (
              <th key={m.key} onClick={() => clickSort(m.key)} className="py-2 px-3 text-[11px] font-bold text-ink-dim uppercase tracking-wider text-left whitespace-nowrap cursor-pointer hover:text-ink select-none">{m.label}{arrow(m.key)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(r => (
            <tr key={r.key} className={`border-t border-surface-line/50 hover:bg-surface-raise/30 ${r.sub ? 'bg-surface-bg/40' : ''}`}>
              <td className={`py-2 pr-3 whitespace-nowrap ${r.sub ? 'pl-9 text-ink-mid text-xs' : 'pl-4 font-semibold text-ink'}`}>
                <span className="inline-flex items-center gap-1.5">
                  {onToggleExpand && !r.sub && (
                    <button onClick={() => onToggleExpand(r.key)} className="text-ink-dim hover:text-ink w-3">▸</button>
                  )}
                  {r.label}
                </span>
              </td>
              {hasDefRk && <td className="py-2 px-3 whitespace-nowrap tabular-nums text-ink-mid/80 text-xs">{r.defRk != null ? `#${r.defRk}` : '—'}</td>}
              {metrics.map(m => {
                const v = r.row ? m.value(r.row) : null
                const isBest = !r.sub && colBest.get(m.key)?.has(visibleRows.indexOf(r))
                return (
                  <td key={m.key} className={`py-2 px-3 whitespace-nowrap tabular-nums ${v == null ? 'text-ink-dim' : isBest ? 'text-data-win font-bold bg-data-win/15' : r.sub ? 'text-ink-mid' : 'text-ink'}`}>
                    {v == null ? '—' : m.fmt(v)}
                  </td>
                )
              })}
            </tr>
          ))}
          {total && (
            <tr className="border-t-2 border-surface-line bg-surface-raise/50">
              <td className="py-2 pl-4 pr-3 whitespace-nowrap text-xs font-bold text-ink-mid uppercase tracking-wider">Total</td>
              {hasDefRk && <td />}
              {metrics.map(m => {
                const v = m.value(total)
                return <td key={m.key} className={`py-2 px-3 whitespace-nowrap tabular-nums font-bold ${v == null ? 'text-ink-dim' : 'text-ink'}`}>{v == null ? '—' : m.fmt(v)}</td>
              })}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
