import ReceivingDataNote from '../../components/ReceivingDataNote'
import Nav from '../../components/Nav'
import { useQuery } from '@tanstack/react-query'
import { seasonsQueryOptions } from '../../api/seasons'
import { loadedSeasons } from '../../utils/seasons'
import { SeasonSelectionFeedback } from './SeasonSelectionFeedback'
import { useComparisonState } from './useComparisonState'
import { useSplitQueries } from './useSplitQueries'
import { useSplitDisplay } from './useSplitDisplay'
import { createSplitModel } from './createSplitModel'
import { createSectionData } from './sectionData'
import { selectStandouts } from './standouts'
import { ComparisonControls } from './ComparisonControls'
import { SplitQueryFeedback } from './SplitQueryFeedback'
import { GetStarted } from './GetStarted'
import { HeadToHead } from './HeadToHead'
import { StandoutSplits } from './StandoutSplits'
import { SplitSections } from './SplitSections'

export default function SplitsPage() {
  const seasonsQuery = useQuery(seasonsQueryOptions())
  const comparison = useComparisonState(loadedSeasons(seasonsQuery.data ?? []))
  const queries = useSplitQueries(comparison)
  const model = createSplitModel(comparison, queries)
  const display = useSplitDisplay(model.defaultOpen)
  const selectors = createSectionData(model, display.expandedKeys)
  const notable = selectStandouts(model, selectors.entitySection)
  return (
    <div className="min-h-screen bg-surface-bg text-ink">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <ComparisonControls comparison={comparison} entities={model.entities} />
        <SeasonSelectionFeedback query={seasonsQuery} availableYears={comparison.availableYears} season={comparison.season} mode={comparison.mode} />
        <SplitQueryFeedback entities={model.entities} splits={queries.splitResults} profiles={queries.playerProfiles}
          analytics={queries.rankQuery} splitKind={comparison.mode === 'teams' ? 'team' : model.isDefense ? 'defensive' : 'offensive'} />
        {comparison.season !== null && (model.entityCount === 0 ? <GetStarted mode={comparison.mode} loadExample={comparison.loadExample} /> : <>
          <ReceivingDataNote unavailable={comparison.mode === 'players' && comparison.playerLens === 'receiving' && (
            model.splitRows.some(rows => rows.some(row => 'category' in row && row.category === 'receiving' && row.att === null && (model.isCareer || row.season === comparison.season)))
            || model.playerGames.some(rows => rows.some(({ g }) => g.targets === null))
          )} career={model.isCareer} />
          <HeadToHead model={model} comparison={comparison} splitResults={queries.splitResults} />
          <StandoutSplits notable={notable} entityLabel={model.entities[0].label} isCareer={model.isCareer} season={comparison.season} />
          <SplitSections model={model} selectors={selectors} display={display} queries={queries} />
        </>)}
      </div>
    </div>
  )
}
