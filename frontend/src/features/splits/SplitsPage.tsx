import Nav from '../../components/Nav'
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
  const comparison = useComparisonState()
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
        <SplitQueryFeedback entities={model.entities} splits={queries.splitResults} profiles={queries.playerProfiles}
          analytics={queries.rankQuery} splitKind={comparison.mode === 'teams' ? 'team' : model.isDefense ? 'defensive' : 'offensive'} />
        {model.entityCount === 0 ? <GetStarted mode={comparison.mode} loadExample={comparison.loadExample} /> : <>
          <HeadToHead model={model} comparison={comparison} splitResults={queries.splitResults} />
          <StandoutSplits notable={notable} entityLabel={model.entities[0].label} isCareer={model.isCareer} season={model.season} />
          <SplitSections model={model} selectors={selectors} display={display} queries={queries} />
        </>}
      </div>
    </div>
  )
}
