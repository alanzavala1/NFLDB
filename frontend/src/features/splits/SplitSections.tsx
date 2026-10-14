import { teamLogoUrl } from '../../utils/teams'
import Card from '../../components/Card'
import type { SplitModel } from './createSplitModel'
import type { createSectionData } from './sectionData'
import type { useSplitDisplay } from './useSplitDisplay'
import type { useSplitQueries } from './useSplitQueries'
import { KEY_METRICS, GAME_METRICS } from './presets'
import { splitValueLabel } from './valueLabels'
import { splitVolume } from './tableRanking'
import { SegmentControl, FilterChip } from './Controls'
import { Section } from './Section'
import { StatTable } from './StatTable'
import { GroupedTable } from './GroupedTable'
import { EmptySplitState } from './SplitQueryFeedback'

export function SplitSections({ model, selectors, display, queries }: {
  model: SplitModel; selectors: ReturnType<typeof createSectionData>
  display: ReturnType<typeof useSplitDisplay>; queries: ReturnType<typeof useSplitQueries>
}) {
  const { singleEntity, entities, sectionDims, gameDims, gameMetrics, metrics, flip, showDefensiveRanks, metricGroup, defensiveRanks } = model
  const { sectionData, entitySection } = selectors
  const { hidden, expandedKeys, keyStatsOnly, setKeyStatsOnly, isOpen, toggleOpen, toggleHidden, toggleExpanded } = display
  const { playerProfiles, splitResults } = queries
  const visibleDims = sectionDims.filter(d => !hidden.has(d.key))
  return <><Card className="mb-3"
    title={singleEntity ? <span>All splits · <span className="text-ink-mid">{entities[0].label}</span></span> : 'All splits · side-by-side'}
    action={!singleEntity ? <SegmentControl value={keyStatsOnly ? 'key' : 'all'} options={[{ value: 'key', label: 'Key stats' }, { value: 'all', label: 'All stats' }]} onChange={v => setKeyStatsOnly(v === 'key')} /> : undefined}>
    <div className="flex flex-wrap items-center gap-1.5 border-t border-surface-line px-4 py-3">
      <span className="text-[11px] font-bold text-ink-dim uppercase tracking-wider mr-1">Show</span>
      {sectionDims.map(d => <FilterChip key={d.key} active={!hidden.has(d.key)} onClick={() => toggleHidden(d.key)}>{d.label}</FilterChip>)}
    </div>
  </Card>

    <div className="space-y-3">
      {visibleDims.map(d => {
        const gameBased = gameDims.has(d.key)
        if (singleEntity) {
          const { rows, total } = sectionData(d.key)
          return (
            <Section key={d.key} title={`By ${d.label}`} open={isOpen(d.key)} onToggle={() => toggleOpen(d.key)}>
              {rows.length === 0
                ? <div className="py-6 text-center"><EmptySplitState
                  queries={gameBased ? playerProfiles.slice(0, 1) : splitResults.slice(0, 1)}
                  resource={gameBased ? 'game records' : 'split statistics'} /></div>
                : <StatTable firstCol={d.label} rows={rows} total={total} metrics={gameBased ? gameMetrics : metrics} flip={flip}
                  hasDefRk={d.key === 'opponent' && showDefensiveRanks} naturalSort={!gameBased}
                  onToggleExpand={gameBased ? (k => toggleExpanded(k)) : undefined} />}
            </Section>
          )
        }
        // side-by-side
        const base = gameBased ? gameMetrics : metrics
        const keyList = gameBased ? GAME_METRICS[metricGroup] : KEY_METRICS[metricGroup]
        const km = keyStatsOnly ? base.filter(m => (keyList ?? []).includes(m.key)) : base
        const m = km.length ? km : base
        const secs = entities.map((_, i) => entitySection(i, d.key))
        const agg = new Map<string, { ord: number; vol: number }>()
        for (const s of secs) for (const [k, row] of s.map) { const e = agg.get(k) ?? { ord: row.sort_order ?? 9999, vol: 0 }; e.vol += splitVolume(row); agg.set(k, e) }
        const keys = [...agg.keys()]
        if (d.key === 'season') keys.sort((a, b) => Number(b) - Number(a))
        else if (d.key === 'opponent') keys.sort((a, b) => agg.get(b)!.vol - agg.get(a)!.vol || a.localeCompare(b))
        else keys.sort((a, b) => agg.get(a)!.ord - agg.get(b)!.ord)
        const keyLabel = (k: string) => d.key === 'season' ? k
          : d.key === 'opponent' ? <span className="inline-flex items-center gap-1.5"><img src={teamLogoUrl(k)} className="w-5 h-5 object-contain" alt="" />{k}</span>
            : splitValueLabel(d.key, k)
        return (
          <Section key={d.key} title={`By ${d.label}`} open={isOpen(d.key)} onToggle={() => toggleOpen(d.key)}>
            {keys.length === 0
              ? <div className="py-6 text-center"><EmptySplitState queries={gameBased ? playerProfiles : splitResults}
                resource={gameBased ? 'game records' : 'split statistics'} /></div>
              : <GroupedTable label={d.label} entities={entities} metrics={m} keys={keys} keyLabel={keyLabel} sections={secs}
                defRkFor={d.key === 'opponent' && showDefensiveRanks ? (k => defensiveRanks.get(k)) : undefined}
                expandable={gameBased} expandShowSeason={d.key === 'opponent'} expandedKeys={expandedKeys}
                onToggleExpand={gameBased ? (k => toggleExpanded(k)) : undefined}
                flip={flip} />}
          </Section>
        )
      })}
    </div>
    <p className="text-[11px] text-ink-dim mt-3 px-1">
      {singleEntity ? 'Click a column to sort · ' : ''}▸ expands a season into its games (linked to the game page) · Season &amp; Opponent use official game-log totals; other splits are play-by-play · green = best{singleEntity ? ' in column' : ''} · regular season.
    </p></>
}
