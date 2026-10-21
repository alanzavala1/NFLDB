import { Fragment } from 'react'
import { Link } from 'react-router-dom'
import type { GroupedSectionData, EntityCard, Metric, SplitRow, GameRecordLite } from './types'
import { bestSet } from './tableRanking'

// Side-by-side: rows = split values, columns grouped by entity (each entity's
// metrics). Sticky label column; best per metric across entities tinted.
export function GroupedTable({ label, entities, metrics, keys, keyLabel, sections, defRkFor, expandable, expandShowSeason, expandedKeys, onToggleExpand, flip, sourceNoteEntityKeys }: {
  label: string
  entities: EntityCard[]
  metrics: Metric<SplitRow>[]
  keys: string[]
  keyLabel: (k: string) => React.ReactNode
  sections: GroupedSectionData[]
  defRkFor?: (k: string) => number | null | undefined
  expandable?: boolean
  expandShowSeason?: boolean
  expandedKeys: Set<string>
  onToggleExpand?: (k: string) => void
  flip: (hib: boolean | undefined) => boolean | undefined
  sourceNoteEntityKeys?: Set<string>
}) {
  const sticky = 'sticky left-0 z-10 bg-surface-card'
  return (
    <div className="overflow-x-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-indigo-400" tabIndex={0} role="region" aria-label={`${label} comparison statistics, scroll for more columns`}>
      <table className="min-w-full text-sm border-separate" style={{ borderSpacing: 0 }}>
        <thead>
          <tr>
            <th rowSpan={2} className={`${sticky} py-2 pl-4 pr-3 text-[11px] font-bold text-ink-mid uppercase tracking-wider text-left whitespace-nowrap border-b-2 border-surface-line`}>{label}</th>
            {entities.map(e => (
              <th key={e.key} colSpan={metrics.length} className="py-1.5 px-3 text-left whitespace-nowrap border-b border-l border-surface-line" style={{ color: `rgb(${e.color})` }}>
                <span className="inline-flex items-center gap-1.5 text-xs font-bold">
                  {e.headshot ? <img src={e.headshot} className="w-5 h-5 rounded-full object-cover object-top bg-surface-raise" alt="" /> : e.logo ? <img src={e.logo} className="w-5 h-5 object-contain" alt="" /> : null}
                  {e.label}
                </span>
              </th>
            ))}
          </tr>
          <tr>
            {entities.map(e => metrics.map((m, mi) => (
              <th key={e.key + m.key} aria-describedby={sourceNoteEntityKeys?.has(e.key) ? m.sourceNoteId : undefined} className={`py-1.5 px-3 text-[10px] font-semibold text-ink-dim uppercase tracking-wider text-right whitespace-nowrap border-b-2 border-surface-line ${mi === 0 ? 'border-l border-surface-line' : ''}`}>{m.label}{m.sourceNoteId && sourceNoteEntityKeys?.has(e.key) && <sup aria-hidden="true">†</sup>}</th>
            )))}
          </tr>
        </thead>
        <tbody>
          {keys.map(k => {
            const dr = defRkFor?.(k)
            const bestByMetric = metrics.map(m => bestSet(sections.map(s => { const r = s.map.get(k); return r ? m.value(r) : null }), flip(m.higherIsBetter)))
            return (
              <Fragment key={k}>
                <tr className="hover:bg-surface-raise/20">
                  <td className={`${sticky} py-2 pl-4 pr-3 whitespace-nowrap font-semibold text-ink border-t border-surface-line/50`}>
                    <span className="inline-flex items-center gap-1.5">
                      {expandable && onToggleExpand && <button aria-expanded={expandedKeys.has(k)} onClick={() => onToggleExpand(k)} className="text-ink-dim hover:text-ink w-8 h-8 rounded focus-visible:outline-2 focus-visible:outline-indigo-400">{expandedKeys.has(k) ? '▾' : '▸'}</button>}
                      {keyLabel(k)}
                      {dr != null && <span className="text-ink-dim/70 text-[10px] font-bold">#{dr}</span>}
                    </span>
                  </td>
                  {sections.map((s, si) => {
                    const r = s.map.get(k)
                    return metrics.map((m, mi) => {
                      const v = r ? m.value(r) : null
                      return <td key={si + m.key} className={`py-2 px-3 text-right whitespace-nowrap tabular-nums border-t border-surface-line/50 ${mi === 0 ? 'border-l border-surface-line/50' : ''} ${v == null ? 'text-ink-dim' : bestByMetric[mi].has(si) ? 'text-data-win font-bold bg-data-win/15' : 'text-ink'}`}>{v == null ? '—' : m.fmt(v)}</td>
                    })
                  })}
                </tr>
                {expandable && expandedKeys.has(k) && (() => {
                  // One row per game, aligned across entities by season+week so the
                  // same game lines up; each entity's stats fill its own columns
                  // (with a link to the game page). Season rows hide the year.
                  const rowMaps = sections.map(s => {
                    const mm = new Map<number, { g: GameRecordLite; r: SplitRow }>()
                    for (const x of (s.groups?.get(k) ?? [])) mm.set(x.g.season * 100 + x.g.week, x)
                    return mm
                  })
                  const gks = [...new Set(rowMaps.flatMap(mm => [...mm.keys()]))].sort((a, b) => a - b)
                  return gks.map(gk => (
                    <tr key={`g-${gk}`} className="bg-surface-bg/40">
                      <td className={`${sticky} bg-surface-bg py-1.5 pl-9 pr-3 whitespace-nowrap text-xs text-ink-dim border-t border-surface-line/40`}>{expandShowSeason ? `${Math.floor(gk / 100)} Wk ${gk % 100}` : `Wk ${gk % 100}`}</td>
                      {sections.map((_, si) => {
                        const x = rowMaps[si].get(gk)
                        return metrics.map((m, mi) => {
                          const v = x ? m.value(x.r) : null
                          return (
                            <td key={si + m.key} className={`py-1.5 px-3 text-right whitespace-nowrap tabular-nums text-xs border-t border-surface-line/40 ${mi === 0 ? 'border-l border-surface-line/50' : ''} ${v == null ? 'text-ink-dim' : 'text-ink-mid'}`}>
                              {mi === 0 && x ? (
                                <div className="flex flex-col leading-tight">
                                  <span>{v == null ? '—' : m.fmt(v)}</span>
                                  <Link to={`/games/${x.g.game_id}`} className="text-[10px] text-indigo-400/70 hover:text-indigo-300">{x.g.location === 'home' ? 'vs ' : '@ '}{x.g.opponent}</Link>
                                </div>
                              ) : (v == null ? '' : m.fmt(v))}
                            </td>
                          )
                        })
                      })}
                    </tr>
                  ))
                })()}
              </Fragment>
            )
          })}
          <tr>
            <td className={`${sticky} bg-surface-raise py-2 pl-4 pr-3 whitespace-nowrap text-xs font-bold text-ink-mid uppercase tracking-wider border-t-2 border-surface-line`}>Total</td>
            {sections.map((s, si) => metrics.map((m, mi) => {
              const v = s.total ? m.value(s.total) : null
              return <td key={si + m.key} className={`py-2 px-3 text-right whitespace-nowrap tabular-nums font-bold bg-surface-raise/40 border-t-2 border-surface-line ${mi === 0 ? 'border-l border-surface-line/50' : ''} ${v == null ? 'text-ink-dim' : 'text-ink'}`}>{v == null ? '—' : m.fmt(v)}</td>
            }))}
          </tr>
        </tbody>
      </table>
    </div>
  )
}
