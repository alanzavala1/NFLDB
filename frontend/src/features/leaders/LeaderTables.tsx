import { Link } from 'react-router-dom'
import type { LeagueLeader } from '../../types'
import { teamLogoUrl } from '../../utils/teams'
import type { LeaderCol, PosCol, SortDir } from './columns'
import { RankBadge } from './Podium'

export function LeaderTable({ players, cols, sort, onSort }: {
  players: LeagueLeader[]
  cols: LeaderCol[]
  sort: { key: string; dir: SortDir }
  onSort: (key: string) => void
}) {
  const tradCount = cols.filter(c => c.kind === 'trad').length
  const advCount  = cols.filter(c => c.kind === 'adv').length

  const sorted = [...players].sort((a, b) => {
    const col = cols.find(c => c.key === sort.key)
    if (!col) return 0
    const diff = col.sortVal(b) - col.sortVal(a)
    return sort.dir === 'desc' ? diff : -diff
  })

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-right cursor-pointer select-none hover:text-ink transition-colors'

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-line/50">
            <th colSpan={4} />
            {tradCount > 0 && <th colSpan={tradCount} className="py-1 text-center text-[10px] font-semibold text-ink-dim uppercase tracking-widest border-l border-surface-line/40">Stats</th>}
            {advCount  > 0 && <th colSpan={advCount}  className="py-1 text-center text-[10px] font-semibold text-ink-dim/60 uppercase tracking-widest bg-surface-raise/20 border-l border-surface-line/40">Advanced</th>}
          </tr>
          <tr className="border-b border-surface-line">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-ink-dim text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-ink-dim text-left">Player</th>
            <th className="py-2.5 px-2 text-xs font-semibold text-ink-dim text-left">Pos</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-ink-dim text-left">Team</th>
            {cols.map((c, i) => {
              const active = sort.key === c.key
              const sep = i === 0 || cols[i - 1].kind !== c.kind
              return (
                <th key={c.key} onClick={() => onSort(c.key)}
                  className={`${thBase} ${sep ? 'border-l border-surface-line/40' : ''}
                    ${c.kind === 'adv' ? 'bg-surface-raise/10 text-ink-dim hover:text-ink-mid' : active ? 'text-ink' : 'text-ink-dim'}`}>
                  <span className="flex items-center justify-end gap-1">
                    {c.label}
                    <span className={`text-[10px] transition-opacity ${active ? 'opacity-100' : 'opacity-0'}`}>
                      {sort.dir === 'desc' ? '↓' : '↑'}
                    </span>
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => (
            <tr key={p.player_id} className="border-t border-surface-line/50 hover:bg-surface-raise/30 transition-colors">
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  {p.headshot_url
                    ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-surface-raise" alt="" />
                    : <div className="w-7 h-7 rounded-full bg-surface-raise shrink-0" />
                  }
                  <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{p.player_name}</Link>
                </div>
              </td>
              <td className="py-2.5 px-2 whitespace-nowrap">
                <span className="text-xs text-ink-dim font-medium">{p.position ?? '—'}</span>
              </td>
              <td className="py-2.5 px-3 whitespace-nowrap">
                {p.team
                  ? <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
                      <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                      <span className="text-xs text-ink-mid group-hover:text-ink transition-colors font-medium">{p.team}</span>
                    </Link>
                  : <span className="text-ink-dim text-xs">—</span>
                }
              </td>
              {cols.map((c, i) => {
                const sep = i === 0 || cols[i - 1].kind !== c.kind
                const val = c.render(p)
                const isNull = val === null || val === undefined
                const str = isNull ? null : String(val)
                const isPos = !isNull && str!.startsWith('+')
                const isNeg = !isNull && str!.startsWith('-')
                return (
                  <td key={c.key} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap
                    ${sep ? 'border-l border-surface-line/30' : ''}
                    ${c.kind === 'adv' ? 'bg-surface-raise/10' : ''}
                    ${isNull ? 'text-ink-dim' : isPos ? 'text-data-win font-semibold' : isNeg ? 'text-data-loss font-semibold' : c.highlight ? 'text-ink font-bold' : c.kind === 'adv' ? 'text-ink-mid/80' : c.dim ? 'text-ink-dim' : 'text-ink-mid'}`}>
                    {isNull ? '—' : str}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function PosTable({ players, cols, sort, onSort }: {
  players: LeagueLeader[]
  cols: PosCol[]
  sort: { key: string; dir: SortDir }
  onSort: (key: string) => void
}) {
  const sorted = [...players].sort((a, b) => {
    const col = cols.find(c => c.key === sort.key)
    if (!col) return 0
    const diff = col.sortVal(b) - col.sortVal(a)
    return sort.dir === 'desc' ? diff : -diff
  })

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-right cursor-pointer select-none hover:text-ink transition-colors'

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-line">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-ink-dim text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-ink-dim text-left min-w-[160px]">Player</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-ink-dim text-left">Team</th>
            {cols.map(c => {
              const active = sort.key === c.key
              return (
                <th key={c.key} onClick={() => onSort(c.key)} title={c.desc}
                  className={`${thBase} ${active ? 'text-ink' : c.dim ? 'text-ink-dim' : 'text-ink-dim'}`}>
                  <span className="flex items-center justify-end gap-1">
                    {c.label}
                    <span className={`text-[10px] transition-opacity ${active ? 'opacity-100' : 'opacity-0'}`}>
                      {sort.dir === 'desc' ? '↓' : '↑'}
                    </span>
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => (
            <tr key={p.player_id} className="border-t border-surface-line/50 hover:bg-surface-raise/30 transition-colors">
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  {p.headshot_url
                    ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-surface-raise" alt="" />
                    : <div className="w-7 h-7 rounded-full bg-surface-raise shrink-0" />
                  }
                  <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{p.player_name}</Link>
                </div>
              </td>
              <td className="py-2.5 px-3 whitespace-nowrap">
                {p.team
                  ? <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
                      <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                      <span className="text-xs text-ink-mid group-hover:text-ink transition-colors font-medium">{p.team}</span>
                    </Link>
                  : <span className="text-ink-dim text-xs">—</span>
                }
              </td>
              {cols.map(c => {
                const val = c.render(p)
                const isNull = val === null || val === undefined
                const str = isNull ? null : String(val)
                const isPos = !isNull && str!.startsWith('+')
                const isNeg = !isNull && str!.startsWith('-')
                return (
                  <td key={c.key} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap
                    ${isNull ? 'text-ink-dim' : isPos ? 'text-data-win font-semibold' : isNeg ? 'text-data-loss font-semibold' : c.highlight ? 'text-ink font-bold' : c.dim ? 'text-ink-dim' : 'text-ink-mid'}`}>
                    {isNull ? '—' : str}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
