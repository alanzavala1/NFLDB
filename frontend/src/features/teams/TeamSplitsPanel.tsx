import { useQuery } from '@tanstack/react-query'
import { teamSplitsQueryOptions } from '../../api/teams'
import { useState } from 'react'
import { aggregateTeamSplit, teamSplitValueLabel, TEAM_SPLIT_COLS, fmtSign3, TEAM_SPLIT_DIMS } from './splitDefinitions'
import type { TeamSplit } from '../../types'
import type { TeamSplitCol } from './types'
import { QueryLoading, QueryFailure } from '../../components/QueryFeedback'

export default function TeamSplitsPanel({ team, season }: { team: string; season: number }) {
  const splitsQuery = useQuery(teamSplitsQueryOptions(team, season))
  const { data: splits = [], isPending } = splitsQuery
  const [side, setSide] = useState<'offense' | 'defense'>('offense')
  const [dim, setDim] = useState('game_script')

  const rows = splits
    .filter(s => s.side === side && s.split_dim === dim)
    // sort_order is NULL for opponent — fall back to volume (most-faced first)
    .sort((a, b) => ((a.sort_order ?? 9999) - (b.sort_order ?? 9999)) || ((b.plays ?? 0) - (a.plays ?? 0)))
  const totalRow = aggregateTeamSplit(rows)

  // Heat is goodness-aware: for defense, lower EPA/success allowed is better,
  // so the sign flips. Green = better than this unit's own average.
  const heatStyle = (r: TeamSplit, c: TeamSplitCol): React.CSSProperties | undefined => {
    if (!c.heat || !totalRow) return undefined
    const val  = c.heat === 'epa' ? r.epa_play : r.success_pct
    const base = c.heat === 'epa' ? totalRow.epa_play : totalRow.success_pct
    if (val == null || base == null) return undefined
    const good = (side === 'offense' ? 1 : -1) * (val - base)
    const alpha = Math.min(0.3, Math.abs(good) * (c.heat === 'epa' ? 0.7 : 0.022))
    if (alpha < 0.03) return undefined
    return { backgroundColor: `rgba(${good >= 0 ? '16,185,129' : '244,63,94'}, ${alpha.toFixed(3)})` }
  }

  const insight = (() => {
    const eligible = rows.filter(r => (r.plays ?? 0) >= 15 && r.epa_play != null)
    if (eligible.length < 2) return null
    const best = side === 'offense'
      ? eligible.reduce((a, b) => (b.epa_play! > a.epa_play! ? b : a))
      : eligible.reduce((a, b) => (b.epa_play! < a.epa_play! ? b : a))
    return { label: teamSplitValueLabel(dim, best.split_value), epa: best.epa_play! }
  })()

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-left'
  const segWrap = 'inline-flex items-center gap-0.5 bg-surface-card border border-surface-line rounded-lg p-0.5'

  const renderRow = (r: TeamSplit, isTotal: boolean) => (
    <tr key={r.split_value} className={isTotal
      ? 'border-t-2 border-surface-line bg-surface-raise/40'
      : 'border-t border-surface-line/60 hover:bg-surface-raise/30'}>
      <td className={`py-2.5 pl-4 pr-3 whitespace-nowrap ${isTotal
        ? 'text-xs font-bold text-ink-mid uppercase tracking-wider'
        : 'font-semibold text-ink'}`}>
        {isTotal ? 'Total' : teamSplitValueLabel(dim, r.split_value)}
      </td>
      {TEAM_SPLIT_COLS.map(c => {
        const raw = c.get(r)
        const isNull = raw == null
        const str = isNull ? '—' : raw
        const isPos = c.signed && !isNull && str.startsWith('+')
        const isNeg = c.signed && !isNull && str.startsWith('-')
        return (
          <td key={c.label}
            style={isTotal ? undefined : heatStyle(r, c)}
            className={`py-2.5 px-3 whitespace-nowrap tabular-nums ${isTotal ? 'font-semibold' : ''} ${
            isNull ? 'text-ink-dim'
              : isPos ? 'text-data-win font-semibold'
              : isNeg ? 'text-red-300 font-semibold'
              : c.highlight ? 'text-ink font-bold'
              : 'text-ink'}`}>
            {str}
          </td>
        )
      })}
    </tr>
  )

  if (isPending) return <div className="mb-4"><QueryLoading>Loading situational splits…</QueryLoading></div>
  if (splits.length === 0) return (
    <div className="mb-4">
      <QueryFailure resource="situational splits" error={splitsQuery.error} hasData={splitsQuery.data !== undefined} onRetry={() => void splitsQuery.refetch()} />
      {!splitsQuery.error && <p className="text-sm text-ink-dim">No situational splits are available for this season.</p>}
    </div>
  )

  return (
    <div className="mb-4">
      <QueryFailure resource="situational splits" error={splitsQuery.error} hasData onRetry={() => void splitsQuery.refetch()} />
      <div className="flex items-baseline justify-between gap-3 mb-2 px-1">
        <h3 className="text-sm font-bold text-ink uppercase tracking-wider">Situational Splits</h3>
        {insight && (
          <span className="text-xs text-ink-dim">
            {side === 'offense' ? 'Best' : 'Stingiest'}: <span className="text-data-win font-semibold">{insight.label}</span>
            <span className="text-ink-dim"> · {fmtSign3(insight.epa)} EPA</span>
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className={segWrap}>
          {(['offense', 'defense'] as const).map(s => (
            <button key={s} onClick={() => { setSide(s); setDim('game_script') }}
              className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded-md transition-colors ${
                side === s ? 'bg-indigo-600 text-ink' : 'text-ink-mid hover:text-ink'}`}>
              {s}
            </button>
          ))}
        </div>
        <div className={`${segWrap} flex-wrap`}>
          {TEAM_SPLIT_DIMS.map(d => (
            <button key={d.key} onClick={() => setDim(d.key)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                dim === d.key ? 'bg-indigo-600 text-ink' : 'text-ink-mid hover:text-ink'}`}>
              {d.label}
            </button>
          ))}
        </div>
      </div>
      <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-line">
                <th className={`${thBase} text-ink-dim pl-4`}>
                  {TEAM_SPLIT_DIMS.find(d => d.key === dim)?.label}
                </th>
                {TEAM_SPLIT_COLS.map(c => (
                  <th key={c.label} className={`${thBase} text-ink-dim`}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(r => renderRow(r, false))}
              {rows.length > 1 && totalRow && renderRow(totalRow, true)}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-2 px-1">
        <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: 'rgba(16,185,129,0.4)' }} />
        <span className="text-[11px] text-ink-dim">better than this unit's average</span>
        <span className="inline-block w-2.5 h-2.5 rounded-sm ml-2" style={{ backgroundColor: 'rgba(244,63,94,0.4)' }} />
        <span className="text-[11px] text-ink-dim">worse · {side === 'defense' ? 'lower EPA allowed = better' : 'regular season'}</span>
      </div>
    </div>
  )
}
