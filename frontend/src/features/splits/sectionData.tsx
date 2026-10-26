import { Link } from 'react-router-dom'
import type { PlayerSplit } from '../../types'
import type { SplitTableRow, SplitRow } from './types'
import type { SplitModel } from './createSplitModel'
import { teamLogoUrl } from '../../utils/teams'
import { aggregatePlayerSplitRows } from './aggregation'
import { splitValueLabel } from './valueLabels'
import { includeReceivingSeasons } from './receivingModel'

export function createSectionData(model: SplitModel, expandedKeys: Set<string>) {
  const { gameDims, games, showDefensiveRanks, defensiveRanks, focusData, matchesDimension, mode, isCareer, aggregateValues,
    season, aggregateRows, playerGames, splitRows, isReceiving } = model
  function preparedRows(data: SplitRow[], dim: string): SplitRow[] {
    if (isReceiving && dim === 'season') return data.filter(row => matchesDimension(row, 'overall')
      && (isCareer || (row as PlayerSplit).season === season))
      .map(row => ({ ...row, split_dim: 'season', split_value: String((row as PlayerSplit).season), sort_order: -(row as PlayerSplit).season }))
    let rows = data.filter(row => matchesDimension(row, dim))
    if (mode === 'players') {
      if (isCareer) rows = aggregateValues(isReceiving ? includeReceivingSeasons(rows as PlayerSplit[], data as PlayerSplit[]) : rows)
      else rows = rows.filter(row => (row as PlayerSplit).season === season)
    }
    return rows
  }
  function sectionData(dim: string): { rows: SplitTableRow[]; total: SplitRow | null } {
    if (gameDims.has(dim)) {
      const groups = new Map<string, typeof games>()
      for (const x of games) {
        const k = dim === 'season' ? String(x.g.season) : x.g.opponent
          ; (groups.get(k) ?? groups.set(k, []).get(k)!).push(x)
      }
      const keys = [...groups.keys()]
      if (dim === 'season') keys.sort((a, b) => Number(b) - Number(a))
      else keys.sort((a, b) => (groups.get(b)!.length - groups.get(a)!.length) || a.localeCompare(b))
      const out: SplitTableRow[] = []
      for (const k of keys) {
        const grp = groups.get(k)!
        const pkey = `${dim}:${k}`
        const gp = <span className="text-ink-dim text-[11px] font-normal ml-1.5">· {grp.length} G</span>
        out.push({
          key: pkey, row: aggregatePlayerSplitRows(grp.map(x => x.r)),
          defRk: dim === 'opponent' && showDefensiveRanks ? (defensiveRanks.get(k) ?? null) : undefined,
          label: dim === 'season'
            ? <span className="font-bold">{k}{gp}</span>
            : <span className="inline-flex items-center gap-1.5"><img src={teamLogoUrl(k)} className="w-5 h-5 object-contain" alt="" />{k}{gp}</span>,
        })
        if (expandedKeys.has(pkey)) {
          for (const { g, r } of [...grp].sort((a, b) => a.g.season - b.g.season || a.g.week - b.g.week)) {
            out.push({
              key: `g:${g.game_id}`, sub: true, row: r,
              label: <Link to={`/games/${g.game_id}`} className="text-indigo-300 hover:text-indigo-200">{g.season} Wk {g.week} {g.location === 'home' ? 'vs' : '@'} {g.opponent} →</Link>,
            })
          }
        }
      }
      return { rows: out, total: aggregatePlayerSplitRows(games.map(x => x.r)) }
    }

    const rows = preparedRows(focusData, dim)
    const trows: SplitTableRow[] = rows.map(r => ({ key: r.split_value, label: dim === 'season' ? r.split_value : splitValueLabel(dim, r.split_value), row: r }))
    return { rows: trows, total: aggregateRows(rows) }
  }
  type EntitySec = { map: Map<string, SplitRow>; total: SplitRow | null; groups?: Map<string, typeof games> }
  function entitySection(idx: number, dim: string): EntitySec {
    if (gameDims.has(dim)) {
      const gs = playerGames[idx] ?? []
      const groups = new Map<string, typeof games>()
      for (const x of gs) {
        const k = dim === 'season' ? String(x.g.season) : x.g.opponent
          ; (groups.get(k) ?? groups.set(k, []).get(k)!).push(x)
      }
      const map = new Map<string, SplitRow>()
      for (const [k, grp] of groups) { const agg = aggregatePlayerSplitRows(grp.map(x => x.r)); if (agg) map.set(k, agg) }
      return { map, total: aggregatePlayerSplitRows(gs.map(x => x.r)), groups }
    }
    const rows = preparedRows(splitRows[idx] ?? [], dim)
    const map = new Map<string, SplitRow>(rows.map(r => [r.split_value, r]))
    return { map, total: aggregateRows(rows) }
  }
  return { sectionData, entitySection }
}
