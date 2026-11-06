import type { TeamLeader } from '../../types'
import { hasReceivingActivity, hasReceivingProduction } from '../../utils/receiving'
import type { SortingState, Updater } from '@tanstack/react-table'
import type { SectionKind, SectionSorting } from './types'
import { aggregateTotals } from './stats'
import SortableTable from './SortableTable'
import { PASS_COLS, RUSH_COLS, REC_COLS, SCRIM_COLS, DEF_COLS } from './columns'

export default function StatsSections({ leaders, sorting, onSortingChange, onClose, games }: {
  leaders: TeamLeader[]
  sorting: SectionSorting
  onSortingChange: (section: SectionKind, updater: Updater<SortingState>) => void
  onClose: () => void
  games: number
}) {
  // Preserve each section's established tie order before interactive sorting.
  const passers   = leaders.filter(p => p.attempts >= 1).sort((a, b) => b.pass_yards - a.pass_yards)
  const rushers   = leaders.filter(p => p.carries >= 1).sort((a, b) => b.rush_yards - a.rush_yards)
  const receivers = leaders.filter(p => hasReceivingActivity(p)).sort((a, b) => b.rec_yards - a.rec_yards)
  const scrimmers = leaders.filter(p => p.carries >= 1 || hasReceivingProduction(p)).sort((a, b) => (b.rush_yards + b.rec_yards) - (a.rush_yards + a.rec_yards))
  const defenders = leaders
    .filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
    .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles))
  const passT = aggregateTotals(passers)
  const rushT = aggregateTotals(rushers)
  const recT  = aggregateTotals(receivers)
  const scrimT = aggregateTotals(scrimmers)
  const defT  = aggregateTotals(defenders)
  return (
    <>
      <SortableTable title="Passing" section="passing" players={passers} cols={PASS_COLS} sorting={sorting.passing} onSortingChange={updater => onSortingChange('passing', updater)} onClose={onClose} totals={passT} games={games} />
      <SortableTable title="Rushing" section="rushing" players={rushers} cols={RUSH_COLS} sorting={sorting.rushing} onSortingChange={updater => onSortingChange('rushing', updater)} onClose={onClose} totals={rushT} games={games} />
      <SortableTable title="Receiving" section="receiving" players={receivers} cols={REC_COLS} sorting={sorting.receiving} onSortingChange={updater => onSortingChange('receiving', updater)} onClose={onClose} totals={recT} games={games} />
      <SortableTable title="Scrimmage" section="scrimmage" players={scrimmers} cols={SCRIM_COLS} sorting={sorting.scrimmage} onSortingChange={updater => onSortingChange('scrimmage', updater)} onClose={onClose} totals={scrimT} games={games} defaultLimit={10} />
      <SortableTable title="Defense" section="defense" players={defenders} cols={DEF_COLS} sorting={sorting.defense} onSortingChange={updater => onSortingChange('defense', updater)} onClose={onClose} totals={defT} games={games} defaultLimit={15} />
    </>
  )
}
