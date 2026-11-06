import type { ReactNode } from 'react'
import type { PlayerSplit } from '../../types'
import type { Metric } from './types'
import type { SplitModel } from './createSplitModel'
import type { createSectionData } from './sectionData'
import { splitVolume } from './tableRanking'
import { aggregatePlayerSplitRows } from './aggregation'
import { splitValueLabel } from './valueLabels'
import { teamLogoUrl } from '../../utils/teams'
import { OVERALL_DIM } from './constants'
import { preparedViewHasGaps } from './preparedCoverage'

export function selectStandouts(model: SplitModel, entitySection: ReturnType<typeof createSectionData>['entitySection']) {
  const { singleEntity, mode, isDefense, playerLens, metrics, splitConfig, games } = model
  if (!singleEntity || mode !== 'players' || isDefense) return null
  const headlineKey = playerLens === 'passing' ? 'ya' : playerLens === 'rushing' ? 'ypc' : 'ypr'
  const unit = playerLens === 'passing' ? 'att' : playerLens === 'rushing' ? 'car' : 'tgt'
  const met = (metrics as Metric<PlayerSplit>[]).find(m => m.key === headlineKey)
  if (!met) return null
  const overall = entitySection(0, model.isPrepared ? 'season' : OVERALL_DIM).total as PlayerSplit | null
  const base = overall ? met.value(overall) : null
  const overallAtt = splitVolume(overall)
  if (base == null || overallAtt <= 0) return null
  const minVol = Math.max(12, overallAtt * 0.1)
  type Cand = { kind: string; label: ReactNode; v: number; delta: number; vol: number }
  const cands: Cand[] = []
  for (const d of splitConfig.dims) {
    if (d.key === 'opponent' || d.key === 'opp_division') continue
    if (model.isPrepared && preparedViewHasGaps(model.preparedSeasons[0] ?? [], d.key)) continue
    for (const [val, row] of entitySection(0, d.key).map) {
      const v = met.value(row as PlayerSplit); const vol = splitVolume(row)
      if (v == null || vol < minVol) continue
      cands.push({ kind: d.label, label: splitValueLabel(d.key, val), v, delta: v - base, vol })
    }
  }
  // Best / worst opponent matchup (needs a few games to be meaningful).
  const byOpp = new Map<string, typeof games>()
  for (const x of games) (byOpp.get(x.g.opponent) ?? byOpp.set(x.g.opponent, []).get(x.g.opponent)!).push(x)
  for (const [opp, grp] of byOpp) {
    if (grp.length < 3) continue
    const agg = aggregatePlayerSplitRows(grp.map(x => x.r))
    const v = agg ? met.value(agg) : null; const vol = splitVolume(agg)
    if (v == null || vol < minVol) continue
    cands.push({ kind: 'Opponent', v, delta: v - base, vol, label: <span className="inline-flex items-center gap-1"><img src={teamLogoUrl(opp)} className="w-4 h-4 object-contain" alt="" />vs {opp}</span> })
  }
  cands.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
  return { met, base, unit, items: cands.slice(0, 6) }
}
