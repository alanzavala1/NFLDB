import type { TeamLeader } from '../../types'
import type { SortDir } from './types'
import { aggregateTotals } from './stats'
import SortableTable from './SortableTable'
import { PASS_COLS, RUSH_COLS, REC_COLS, SCRIM_COLS, DEF_COLS } from './columns'

export default function StatsSections({ leaders, sorts, onSort, onClose, games }: {
  leaders: TeamLeader[]
  sorts: Record<string, { key: string; dir: SortDir }>
  onSort: (section: string, key: string) => void
  onClose: () => void
  games: number
}) {
  const passers   = leaders.filter(p => p.attempts >= 1).sort((a, b) => b.pass_yards - a.pass_yards)
  const rushers   = leaders.filter(p => p.carries >= 1).sort((a, b) => b.rush_yards - a.rush_yards)
  const receivers = leaders.filter(p => p.targets >= 1).sort((a, b) => b.rec_yards - a.rec_yards)
  const scrimmers = leaders.filter(p => (p.carries + p.receptions) >= 1).sort((a, b) => (b.rush_yards + b.rec_yards) - (a.rush_yards + a.rec_yards))
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
      <SortableTable title="Passing"   section="passing"   players={passers}   cols={PASS_COLS}  sortKey={sorts.passing.key}   sortDir={sorts.passing.dir}   onSort={k => onSort('passing',   k)} onClose={onClose} totals={passT}  games={games} />
      <SortableTable title="Rushing"   section="rushing"   players={rushers}   cols={RUSH_COLS}  sortKey={sorts.rushing.key}   sortDir={sorts.rushing.dir}   onSort={k => onSort('rushing',   k)} onClose={onClose} totals={rushT}  games={games} />
      <SortableTable title="Receiving" section="receiving" players={receivers} cols={REC_COLS}   sortKey={sorts.receiving.key} sortDir={sorts.receiving.dir} onSort={k => onSort('receiving', k)} onClose={onClose} totals={recT}   games={games} />
      <SortableTable title="Scrimmage" section="scrimmage" players={scrimmers} cols={SCRIM_COLS} sortKey={sorts.scrimmage.key} sortDir={sorts.scrimmage.dir} onSort={k => onSort('scrimmage', k)} onClose={onClose} totals={scrimT} games={games} defaultLimit={10} />
      <SortableTable title="Defense"   section="defense"   players={defenders} cols={DEF_COLS}   sortKey={sorts.defense.key}   sortDir={sorts.defense.dir}   onSort={k => onSort('defense',   k)} onClose={onClose} totals={defT}   games={games} defaultLimit={15} />
    </>
  )
}
