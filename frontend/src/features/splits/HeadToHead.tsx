import Card from '../../components/Card'
import type { SplitTableRow } from './types'
import type { SplitModel } from './createSplitModel'
import type { useComparisonState } from './useComparisonState'
import type { SplitQueryState } from './SplitQueryFeedback'
import { EmptySplitState } from './SplitQueryFeedback'
import { FilterChip } from './Controls'
import { StatTable } from './StatTable'

export function HeadToHead({ model, comparison, splitResults }: {
  model: SplitModel; comparison: ReturnType<typeof useComparisonState>; splitResults: SplitQueryState[]
}) {
  const { mode, situation, setSituation } = comparison
  const { entities, splitRows, situations, situationRow, metrics, flip } = model
  const summaryRows: SplitTableRow[] = entities.map((meta, i) => ({
    key: meta.key,
    label: <span className="inline-flex items-center gap-2"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: `rgb(${meta.color})` }} />{meta.headshot ? <img src={meta.headshot} className="w-6 h-6 rounded-full object-cover object-top bg-surface-raise" alt="" /> : meta.logo ? <img src={meta.logo} className="w-6 h-6 object-contain" alt="" /> : null}{meta.label}</span>,
    row: situationRow(splitRows[i]),
  }))
  return (<Card title="Head-to-head" className="mb-6">
    <div className="flex flex-wrap items-center gap-1.5 border-t border-surface-line px-4 py-3">
      <span className="text-[11px] font-bold text-ink-dim uppercase tracking-wider mr-1">Compare on</span>
      <FilterChip active={!situation} onClick={() => setSituation(null)}>Overall</FilterChip>
      {situations.map(s => <FilterChip key={s.label} active={situation?.label === s.label} onClick={() => setSituation(s)}>{s.label}</FilterChip>)}
    </div>
    {summaryRows.every(r => r.row == null)
      ? <div className="py-8 text-center border-t border-surface-line"><EmptySplitState queries={splitResults} /></div>
      : <div className="border-t border-surface-line"><StatTable firstCol={mode === 'players' ? 'Player' : 'Team'} rows={summaryRows} metrics={metrics} flip={flip} /></div>}
  </Card>)
}
