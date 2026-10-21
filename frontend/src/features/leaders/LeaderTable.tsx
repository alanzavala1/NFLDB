import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  createSortedRowModel, rowSortingFeature, sortFn_basic, tableFeatures, useTable,
  type ColumnDef, type OnChangeFn, type SortingState,
} from '@tanstack/react-table'
import type { LeagueLeader } from '../../types'
import { teamLogoUrl } from '../../utils/teams'
import type { LeaderCol, PosCol } from './columns'
import { RankBadge } from './Podium'

type StatColumn = LeaderCol | PosCol

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
})

function columnKind(column: StatColumn) {
  return 'kind' in column ? column.kind : null
}

function StatValue({ player, column }: { player: LeagueLeader; column: StatColumn }) {
  const value = column.render(player)
  const text = value === null || value === undefined ? null : String(value)
  const tone = text === null ? 'text-ink-dim'
    : text.startsWith('+') ? 'text-data-win font-semibold'
    : text.startsWith('-') ? 'text-data-loss font-semibold'
    : column.highlight ? 'text-ink font-bold'
    : columnKind(column) === 'adv' ? 'text-ink-mid/80'
    : column.dim ? 'text-ink-dim' : 'text-ink-mid'
  return <span className={tone}>{text ?? '—'}</span>
}

export function LeaderTable({ players, cols, sorting, onSortingChange, view }: {
  players: LeagueLeader[]
  cols: StatColumn[]
  sorting: SortingState
  onSortingChange: OnChangeFn<SortingState>
  view: 'stats' | 'positions'
}) {
  const columns = useMemo<ColumnDef<typeof features, LeagueLeader>[]>(() => cols.map(column => ({
    id: column.key,
    header: column.label,
    accessorFn: player => column.sortVal(player) ?? undefined,
    sortUndefined: 'last',
    enableSorting: players.some(player => column.sortVal(player) != null),
    sortFn: sortFn_basic,
    cell: ({ row }) => <StatValue player={row.original} column={column} />,
  })), [cols, players])
  const table = useTable({
    features,
    data: players,
    columns,
    getRowId: player => player.player_id,
    state: { sorting },
    onSortingChange,
    sortDescFirst: true,
    enableSortingRemoval: false,
    enableMultiSort: false,
  })
  const showPosition = view === 'stats'
  const traditional = cols.filter(column => columnKind(column) === 'trad').length
  const advanced = cols.filter(column => columnKind(column) === 'adv').length
  const startsGroup = (index: number) => showPosition && (index === 0 || columnKind(cols[index - 1]) !== columnKind(cols[index]))

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          {showPosition && <tr className="border-b border-surface-line/50">
            <th colSpan={4} />
            {traditional > 0 && <th colSpan={traditional} className="py-1 text-center text-[10px] font-semibold text-ink-dim uppercase tracking-widest border-l border-surface-line/40">Stats</th>}
            {advanced > 0 && <th colSpan={advanced} className="py-1 text-center text-[10px] font-semibold text-ink-dim/60 uppercase tracking-widest bg-surface-raise/20 border-l border-surface-line/40">Advanced</th>}
          </tr>}
          <tr className="border-b border-surface-line">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-ink-dim text-right w-8">#</th>
            <th className={`py-2.5 pl-2 pr-3 text-xs font-semibold text-ink-dim text-left ${showPosition ? '' : 'min-w-[160px]'}`}>Player</th>
            {showPosition && <th className="py-2.5 px-2 text-xs font-semibold text-ink-dim text-left">Pos</th>}
            <th className="py-2.5 px-3 text-xs font-semibold text-ink-dim text-left">Team</th>
            {table.getFlatHeaders().map((header, index) => {
              const column = cols[index]
              const direction = header.column.getIsSorted()
              const isAdvanced = columnKind(column) === 'adv'
              return (
                <th key={header.id} title={'desc' in column ? column.desc : undefined}
                  aria-sort={direction === 'desc' ? 'descending' : direction === 'asc' ? 'ascending' : 'none'}
                  className={`py-2 px-3 text-xs font-medium whitespace-nowrap text-right select-none hover:text-ink transition-colors
                    ${startsGroup(index) ? 'border-l border-surface-line/40' : ''}
                    ${isAdvanced ? 'bg-surface-raise/10 text-ink-dim hover:text-ink-mid' : direction ? 'text-ink' : 'text-ink-dim'}`}>
                  <button type="button" disabled={!header.column.getCanSort()} onClick={header.column.getToggleSortingHandler()}
                    className="flex w-full items-center justify-end gap-1 cursor-pointer">
                    <table.FlexRender header={header} />
                    <span aria-hidden="true" className={`text-[10px] transition-opacity ${direction ? 'opacity-100' : 'opacity-0'}`}>
                      {direction === 'asc' ? '↑' : '↓'}
                    </span>
                  </button>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, index) => {
            const player = row.original
            return (
              <tr key={row.id} className="border-t border-surface-line/50 hover:bg-surface-raise/30 transition-colors">
                <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={index + 1} /></td>
                <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    {player.headshot_url
                      ? <img src={player.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-surface-raise" alt="" />
                      : <div className="w-7 h-7 rounded-full bg-surface-raise shrink-0" />}
                    <Link to={`/players/${player.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{player.player_name}</Link>
                  </div>
                </td>
                {showPosition && <td className="py-2.5 px-2 whitespace-nowrap"><span className="text-xs text-ink-dim font-medium">{player.position ?? '—'}</span></td>}
                <td className="py-2.5 px-3 whitespace-nowrap">
                  {player.team
                    ? <Link to={`/teams/${player.team}`} className="flex items-center gap-1.5 group w-fit">
                        <img src={teamLogoUrl(player.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                        <span className="text-xs text-ink-mid group-hover:text-ink transition-colors font-medium">{player.team}</span>
                      </Link>
                    : <span className="text-ink-dim text-xs">—</span>}
                </td>
                {row.getAllCells().map((cell, columnIndex) => (
                  <td key={cell.id} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap
                    ${startsGroup(columnIndex) ? 'border-l border-surface-line/30' : ''}
                    ${columnKind(cols[columnIndex]) === 'adv' ? 'bg-surface-raise/10' : ''}`}>
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
