import type { PlayerGame, NgsStats, SnapTotals, SituationalStats, KickingStats, PlayerWpa, PlayerAdvStats } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl } from '../../utils/teams'
import { sumGames, detectPos, aggregateSituational } from './stats'
import { QB_COLS, RB_COLS, WR_COLS, DEF_COLS, K_COLS, P_COLS, OL_COLS, type ColKind, type Col } from './careerColumns'

export default function CareerTable({ title, seasons, bySeason, ngs, snapTotals, situational, kicking, wpa, advStats, position, onlyKinds, showGroupHeaders = true }: {
  title?: string
  seasons: number[]
  bySeason: Record<number, PlayerGame[]>
  ngs: Record<number, NgsStats>
  snapTotals: Record<number, SnapTotals>
  situational: Record<number, SituationalStats>
  kicking?: Record<number, KickingStats>
  wpa?: Record<number, PlayerWpa>
  advStats?: Record<number, PlayerAdvStats>
  position?: string | null
  onlyKinds?: ColKind[]
  showGroupHeaders?: boolean
}) {
  const allTotals = sumGames(seasons.flatMap(s => bySeason[s]))
  const pos = detectPos(allTotals, position)
  const allCols = pos === 'QB' ? QB_COLS : pos === 'RB' ? RB_COLS : pos === 'WR' ? WR_COLS : pos === 'K' ? K_COLS : pos === 'P' ? P_COLS : pos === 'OL' ? OL_COLS : DEF_COLS

  const hasNgs  = Object.keys(ngs).length > 0
  const hasSnaps = Object.keys(snapTotals).length > 0
  const hasSit  = Object.keys(situational).length > 0 && pos !== 'DEF'
  const hasWpa  = wpa != null && Object.keys(wpa).length > 0
  const cols = allCols.filter(c =>
    !(onlyKinds && !onlyKinds.includes(c.kind)) &&
    !(c.kind === 'ngs'  && !hasNgs) &&
    !(c.kind === 'snap' && !hasSnaps) &&
    !(c.kind === 'sit'  && !hasSit) &&
    !(c.wpaOnly && !hasWpa)
  )

  // Build consecutive sections for the group header row
  type Sec = { label: string; count: number; kind: ColKind; group?: string }
  const sections: Sec[] = []
  for (const c of cols) {
    const lbl = c.kind === 'trad' ? (c.group ?? '') : c.kind === 'adv' ? 'Advanced' : c.kind === 'ngs' ? 'Next Gen' : c.kind === 'snap' ? 'Snaps' : c.kind === 'sit' ? 'Situational' : ''
    const last = sections[sections.length - 1]
    if (last && last.label === lbl && last.kind === c.kind) last.count++
    else sections.push({ label: lbl, count: 1, kind: c.kind, group: c.group })
  }

  const hasAdv  = advStats != null && Object.keys(advStats).length > 0

  const careerAdvTotals: PlayerAdvStats | undefined = hasAdv ? (() => {
    const vals = seasons.map(s => advStats![s]).filter(Boolean)
    const totalFL = vals.reduce((acc, v) => acc + (v.fumbles_lost ?? 0), 0)
    const totalStuffed = vals.reduce((acc, v) => acc + (v.stuffed ?? 0), 0)
    const totalCarries = vals.reduce((acc, v) => acc + (v.carries_total ?? 0), 0)
    const totalDefTds = vals.reduce((acc, v) => acc + (v.def_tds ?? 0), 0)
    const totalPen = vals.reduce((acc, v) => acc + (v.penalties ?? 0), 0)
    const totalPenYds = vals.reduce((acc, v) => acc + (v.penalty_yards ?? 0), 0)
    const totalFS = vals.reduce((acc, v) => acc + (v.false_starts ?? 0), 0)
    const totalHold = vals.reduce((acc, v) => acc + (v.holding ?? 0), 0)
    const tshVals = vals.map(v => v.target_share).filter((v): v is number => v != null)
    const ayshVals = vals.map(v => v.air_yards_share).filter((v): v is number => v != null)
    return {
      fumbles_lost: totalFL,
      stuffed: totalStuffed,
      carries_total: totalCarries,
      def_tds: totalDefTds,
      penalties: totalPen,
      penalty_yards: totalPenYds,
      false_starts: totalFS,
      holding: totalHold,
      stuff_rate: totalCarries > 0 ? parseFloat((100 * totalStuffed / totalCarries).toFixed(1)) : undefined,
      target_share: tshVals.length > 0 ? parseFloat((tshVals.reduce((a, b) => a + b, 0) / tshVals.length).toFixed(1)) : undefined,
      air_yards_share: ayshVals.length > 0 ? parseFloat((ayshVals.reduce((a, b) => a + b, 0) / ayshVals.length).toFixed(1)) : undefined,
    }
  })() : undefined

  const careerWpaTotals: PlayerWpa | undefined = hasWpa ? {
    pass_wpa: seasons.reduce((acc, s) => acc + (wpa![s]?.pass_wpa ?? 0), 0),
    rush_wpa: seasons.reduce((acc, s) => acc + (wpa![s]?.rush_wpa ?? 0), 0),
    rec_wpa:  seasons.reduce((acc, s) => acc + (wpa![s]?.rec_wpa  ?? 0), 0),
  } : undefined

  const careerSit = hasSit ? aggregateSituational(situational) : undefined

  // Career kicking/punting: sum counts, max the "longest" fields. Net/FG-rate
  // averages are recomputed in the cell against the season-total counts.
  const hasKick = kicking != null && Object.keys(kicking).length > 0
  const careerKick: KickingStats | undefined = hasKick ? (() => {
    const vals = seasons.map(s => kicking![s]).filter(Boolean)
    const sum = (f: (k: KickingStats) => number | null | undefined) =>
      vals.reduce((acc, v) => acc + (f(v) ?? 0), 0)
    const maxOf = (f: (k: KickingStats) => number | null | undefined) => {
      const xs = vals.map(f).filter((x): x is number => x != null)
      return xs.length ? Math.max(...xs) : undefined
    }
    return {
      fg_long:       maxOf(k => k.fg_long),
      fg_0_39_made:  sum(k => k.fg_0_39_made),  fg_0_39_att:  sum(k => k.fg_0_39_att),
      fg_40_49_made: sum(k => k.fg_40_49_made), fg_40_49_att: sum(k => k.fg_40_49_att),
      fg_50_made:    sum(k => k.fg_50_made),    fg_50_att:    sum(k => k.fg_50_att),
      fg_blocked:    sum(k => k.fg_blocked),
      punt_net_yards:  sum(k => k.punt_net_yards),
      punt_inside_20:  sum(k => k.punt_inside_20),
      punt_touchbacks: sum(k => k.punt_touchbacks),
      punt_long:       maxOf(k => k.punt_long),
      punt_blocked:    sum(k => k.punt_blocked),
    }
  })() : undefined

  const careerT = sumGames(seasons.flatMap(s => bySeason[s]))
  const careerGames = seasons.reduce((acc, s) => acc + bySeason[s].length, 0)

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-left'

  if (cols.length === 0) return null

  return (
    <Card title={title} className="mb-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {showGroupHeaders && (
              <tr className="border-b border-surface-line/50">
                <th colSpan={2} />
                {sections.map((s, i) => {
                  if (s.kind === 'trad' && !s.group) return <th key={i} colSpan={s.count} />
                  const cls = 'border-l border-surface-line/40 text-ink-dim'
                  return (
                    <th key={i} colSpan={s.count} className={`py-1 text-center text-[10px] font-semibold uppercase tracking-widest ${cls}`}>
                      {s.label}
                    </th>
                  )
                })}
              </tr>
            )}
            <tr className="border-b border-surface-line">
              <th className={`${thBase} text-ink-dim pl-4`}>Season</th>
              <th className={`${thBase} text-ink-dim`}>Team</th>
              {cols.map((c, i) => {
                const sep = i > 0 && (cols[i - 1].kind !== c.kind || cols[i - 1].group !== c.group)
                return (
                  <th key={c.key} className={`${thBase} ${sep ? 'border-l border-surface-line/40' : ''}
                    text-ink-dim`}>
                    {c.label}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {seasons.map(s => {
              const games = bySeason[s]
              const t = sumGames(games)
              const n = ngs[s] as NgsStats | undefined
              const sn = snapTotals[s] as SnapTotals | undefined
              const sit = situational[s] as SituationalStats | undefined
              const w = wpa?.[s] as PlayerWpa | undefined
              const a = advStats?.[s] as PlayerAdvStats | undefined
              const k = kicking?.[s] as KickingStats | undefined
              const teams = [...new Set(games.map(g => g.team))]
              return (
                <tr key={s} className="border-t border-surface-line/60 hover:bg-surface-raise/30">
                  <td className="py-2.5 pl-4 pr-3 font-bold text-ink whitespace-nowrap">{s}</td>
                  <td className="py-2.5 px-3">
                    <div className="flex items-center gap-1.5">
                      <div className="flex -space-x-1">
                        {teams.map(tm => (
                          <img key={tm} src={teamLogoUrl(tm)} alt={tm} className="w-5 h-5 object-contain ring-1 ring-surface-line rounded-full bg-surface-card" />
                        ))}
                      </div>
                      <span className="text-ink-mid text-xs">{teams.join('/')}</span>
                    </div>
                  </td>
                  {cols.map((c, i) => {
                    const sep = i > 0 && (cols[i - 1].kind !== c.kind || cols[i - 1].group !== c.group)
                    const raw = c.cell(t, games.length, n, sn, sit, w, a, k)
                    const isNull = raw === null || raw === undefined
                    const strVal = isNull ? null : String(raw)
                    const isPos = c.signed && !isNull && strVal!.startsWith('+')
                    const isNeg = c.signed && !isNull && strVal!.startsWith('-')
                    return (
                      <td key={c.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums
                        ${sep ? 'border-l border-surface-line/30' : ''}
                        ${isNull   ? 'text-ink-dim' :
                          isPos    ? 'text-data-win font-semibold' :
                          isNeg    ? 'text-data-loss font-semibold' :
                          c.highlight ? 'text-ink font-bold' :
                          c.kind === 'ngs'  ? 'text-ink' :
                          c.kind === 'adv'  ? 'text-ink-mid/80' :
                          c.kind === 'sit'  ? 'text-ink-mid/80' :
                          'text-ink-mid'}`}>
                        {isNull ? '—' : strVal}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
            {seasons.length > 1 && (
              <tr className="border-t-2 border-surface-line bg-surface-raise/40">
                <td className="py-2.5 pl-4 pr-3 text-xs font-bold text-ink-mid uppercase tracking-wider whitespace-nowrap">Career</td>
                <td className="py-2.5 px-3 text-ink-dim text-xs">{careerGames}G</td>
                {cols.map((c, i) => {
                  const sep = i > 0 && (cols[i - 1].kind !== c.kind || cols[i - 1].group !== c.group)
                  const raw = (c.kind === 'trad' || c.kind === 'adv' || c.kind === 'sit')
                    ? c.cell(careerT, careerGames, undefined, undefined, careerSit, careerWpaTotals, careerAdvTotals, careerKick)
                    : null
                  const isNull = raw === null || raw === undefined
                  const strVal = isNull ? null : String(raw)
                  const isPos = c.signed && !isNull && strVal!.startsWith('+')
                  const isNeg = c.signed && !isNull && strVal!.startsWith('-')
                  return (
                    <td key={c.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums font-semibold
                      ${sep ? 'border-l border-surface-line/30' : ''}
                      ${c.kind === 'ngs' ? 'text-ink-dim' : ''}
                      ${isNull ? 'text-ink-dim' : isPos ? 'text-data-win' : isNeg ? 'text-data-loss' : c.highlight ? 'text-ink' : c.kind === 'adv' ? 'text-ink-mid/80' : c.kind === 'sit' ? 'text-ink-mid/80' : 'text-ink-mid'}`}>
                      {isNull ? '—' : String(raw)}
                    </td>
                  )
                })}
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <TableEraNotes seasons={seasons} cols={cols} />
    </Card>
  )
}

function TableEraNotes({ seasons, cols }: { seasons: number[]; cols: Col[] }) {
  if (seasons.length === 0) return null
  const oldest = Math.min(...seasons)
  const notes: string[] = []

  const hasNgs   = cols.some(c => c.kind === 'ngs')
  const hasAdv   = cols.some(c => c.kind === 'adv' || c.wpaOnly)
  const hasSnap  = cols.some(c => c.kind === 'snap')

  if (hasNgs  && oldest < 2016) notes.push('NGS metrics (CPOE, ADOT, separation, time to throw) only tracked from 2016+')
  if (hasAdv  && oldest < 2006) notes.push('EPA-based metrics start in 2006 when the model became available')
  if (hasSnap && oldest < 2012) notes.push('Snap counts tracked from 2012+')

  if (notes.length === 0) return null

  return (
    <div className="border-t border-surface-line/60 px-4 py-2.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="text-[10px] font-bold text-ink-dim uppercase tracking-widest shrink-0">—</span>
      <span className="text-[11px] text-ink-dim">means data unavailable for that season:</span>
      {notes.map(n => (
        <span key={n} className="text-[11px] text-ink-dim">· {n}</span>
      ))}
    </div>
  )
}
