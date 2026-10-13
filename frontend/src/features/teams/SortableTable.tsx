import type { SummaryBox, SectionKind, TCol, SortDir, SectionTotals } from './types'
import type { TeamLeader } from '../../types'
import { useState } from 'react'
import { buildSummary } from './stats'
import { Link } from 'react-router-dom'

function SectionStrip({ items }: { items: SummaryBox[] }) {
  return (
    <div className="px-4 py-3 bg-surface-bg/40 border-b border-surface-line/80">
      <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
        {items.map(b => (
          <div key={b.label} className="text-center">
            <div className="text-base font-bold text-ink tabular-nums leading-tight">{b.value}</div>
            <div className="text-[10px] text-ink-dim uppercase tracking-wider mt-0.5">{b.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function SortableTable({ title, section, players, cols, sortKey, sortDir, onSort, onClose, defaultLimit, totals, games }: {
  title: string; section: SectionKind; players: TeamLeader[]; cols: TCol[]
  sortKey: string; sortDir: SortDir; onSort: (k: string) => void; onClose: () => void
  defaultLimit?: number
  totals: SectionTotals
  games: number
}) {
  const [expanded, setExpanded] = useState(false)
  if (!players.length) return null
  const tradCount = cols.filter(c => c.kind === 'trad').length
  const advCount  = cols.filter(c => c.kind === 'adv').length
  const sorted = [...players].sort((a, b) => {
    const col = cols.find(c => c.key === sortKey)
    if (!col) return 0
    const diff = col.sortVal(b) - col.sortVal(a)
    return sortDir === 'desc' ? diff : -diff
  })
  const visible = defaultLimit && !expanded ? sorted.slice(0, defaultLimit) : sorted
  const hiddenCount = sorted.length - (defaultLimit ?? sorted.length)
  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-right cursor-pointer select-none hover:text-ink transition-colors'
  return (
    <div className="mb-6 bg-surface-card border border-surface-line rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-surface-line flex items-center justify-between">
        <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">{title}</span>
        <span className="text-[10px] text-ink-dim uppercase tracking-wider">Team Totals</span>
      </div>
      <SectionStrip items={buildSummary(section, totals, games)} />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-line/50">
              <th colSpan={3} />
              {tradCount > 0 && <th colSpan={tradCount} className="py-1 text-center text-[10px] font-semibold text-ink-dim uppercase tracking-widest border-l border-surface-line/40">Stats</th>}
              {advCount  > 0 && <th colSpan={advCount}  className="py-1 text-center text-[10px] font-semibold text-ink-dim/60 uppercase tracking-widest bg-surface-raise/20 border-l border-surface-line/40">Advanced</th>}
            </tr>
            <tr className="border-b border-surface-line bg-surface-raise/60">
              <th className="py-2 pl-4 pr-2 text-xs font-medium text-ink-dim text-left whitespace-nowrap">Player</th>
              <th className="py-2 px-2 text-xs font-medium text-ink-dim text-left whitespace-nowrap">Pos</th>
              <th className="py-2 px-3 text-xs font-medium text-ink-dim text-right whitespace-nowrap">G</th>
              {cols.map((c, i) => {
                const active = sortKey === c.key
                const sep = i === 0 || cols[i - 1].kind !== c.kind
                return (
                  <th key={c.key} onClick={() => onSort(c.key)}
                    className={`${thBase} ${sep ? 'border-l border-surface-line/40' : ''}
                      ${c.kind === 'adv' ? 'bg-surface-raise/10 text-ink-dim hover:text-ink-mid' : active ? 'text-ink' : 'text-ink-dim'}`}>
                    <span className="flex items-center justify-end gap-1">
                      {c.label}
                      <span className={`text-[10px] ${active ? 'opacity-100' : 'opacity-0'}`}>{sortDir === 'desc' ? '↓' : '↑'}</span>
                    </span>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map(p => (
              <tr key={p.player_id} className="border-t border-surface-line/60 hover:bg-surface-raise/30">
                <td className="py-2 pl-4 pr-2 whitespace-nowrap">
                  <Link to={`/players/${p.player_id}`} onClick={onClose} className="text-indigo-400 hover:underline font-medium text-sm">{p.player_name}</Link>
                </td>
                <td className="py-2 px-2 text-xs text-ink-dim whitespace-nowrap">{p.position ?? '—'}</td>
                <td className="py-2 px-3 text-right tabular-nums text-ink-dim text-sm">{p.games_played}</td>
                {cols.map((c, i) => {
                  const sep = i === 0 || cols[i - 1].kind !== c.kind
                  const val = c.render(p, totals)
                  const isNull = val === null || val === undefined
                  const str = isNull ? null : String(val)
                  const isPos = !isNull && str!.startsWith('+')
                  const isNeg = !isNull && str!.startsWith('-')
                  const shareVal = c.share ? c.share(p, totals) : 0
                  return (
                    <td key={c.key} className={`relative py-2 px-3 text-right tabular-nums text-sm whitespace-nowrap
                      ${sep ? 'border-l border-surface-line/30' : ''}
                      ${c.kind === 'adv' ? 'bg-surface-raise/10' : ''}
                      ${isNull ? 'text-ink-dim' : isPos ? 'text-data-win font-semibold' : isNeg ? 'text-data-loss font-semibold' : c.highlight ? 'text-ink font-bold' : c.kind === 'adv' ? 'text-ink-mid/80' : c.dim ? 'text-ink-dim' : 'text-ink-mid'}`}>
                      {c.share && shareVal > 0 && !isNull && (
                        <div className="pointer-events-none absolute inset-y-0 left-0 bg-data-win/15" style={{ width: `${Math.min(100, shareVal * 100)}%` }} />
                      )}
                      <span className="relative">{isNull ? '—' : str}</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-surface-line/80 bg-surface-raise/40">
              <td className="py-2.5 pl-4 pr-2 text-[11px] font-bold text-ink-mid uppercase tracking-wider">Team</td>
              <td />
              <td className="py-2.5 px-3 text-right tabular-nums text-ink-mid text-sm font-semibold">{games > 0 ? games : '—'}</td>
              {cols.map((c, i) => {
                const sep = i === 0 || cols[i - 1].kind !== c.kind
                const val = c.total ? c.total(totals, games) : null
                const isNull = val === null || val === undefined
                const str = isNull ? null : String(val)
                const isPos = !isNull && str!.startsWith('+')
                const isNeg = !isNull && str!.startsWith('-')
                return (
                  <td key={c.key} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap font-bold
                    ${sep ? 'border-l border-surface-line/30' : ''}
                    ${c.kind === 'adv' ? 'bg-surface-raise/10' : ''}
                    ${isNull ? 'text-ink-dim' : isPos ? 'text-data-win' : isNeg ? 'text-red-300' : c.kind === 'adv' ? 'text-ink-mid/90' : 'text-ink'}`}>
                    <span className="relative">{isNull ? '—' : str}</span>
                  </td>
                )
              })}
            </tr>
            {defaultLimit && hiddenCount > 0 && (
              <tr className="border-t border-surface-line/60">
                <td colSpan={3 + cols.length} className="py-0">
                  <button
                    onClick={() => setExpanded(e => !e)}
                    className="w-full py-2 text-xs text-ink-dim hover:text-ink-mid transition-colors flex items-center justify-center gap-1"
                  >
                    {expanded ? <>show less <span className="text-[10px]">↑</span></> : <>{hiddenCount} more <span className="text-[10px]">↓</span></>}
                  </button>
                </td>
              </tr>
            )}
          </tfoot>
        </table>
      </div>
    </div>
  )
}
