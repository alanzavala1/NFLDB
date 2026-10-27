import ReceivingDataNote from '../../components/ReceivingDataNote'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { functionalUpdate, type OnChangeFn, type SortingState } from '@tanstack/react-table'
import { useSearchParams } from 'react-router-dom'
import { seasonsQueryOptions } from '../../api/seasons'
import { leadersQueryOptions } from '../../api/leaders'
import { loadedSeasons, selectedSeason } from '../../utils/seasons'
import Nav from '../../components/Nav'
import Card from '../../components/Card'
import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import { PAST_AWARDS } from '../../utils/awards'
import { STAT_TABS, POS_TABS } from './columns'
import { STAT_PRIMARY, POS_PRIMARY } from './primaryStats'
import { AwardsSection } from './Awards'
import { StatDashboard } from './LeaderDashboard'
import { Podium } from './Podium'
import { LeaderTable } from './LeaderTable'
import { LeaderHeader, LeaderControls, type Mode } from './LeaderControls'
import { WpaPanel, type WpaSubTab } from './WpaPanel'

export default function LeadersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const seasonsQuery = useQuery(seasonsQueryOptions())
  const years = loadedSeasons(seasonsQuery.data ?? [])
  const season = selectedSeason(searchParams.get('season'), years)
  const leadersQuery = useQuery(leadersQueryOptions(season))
  const leaders = leadersQuery.data ?? []
  const mode: Mode = searchParams.get('mode') === 'positions' ? 'positions' : 'leaders'
  const requestedStat = searchParams.get('tab') ?? 'passing'
  const statTab = STAT_TABS.find(tab => tab.key === requestedStat) ?? STAT_TABS[0]
  const posTab = POS_TABS.find(tab => tab.key === searchParams.get('pos')) ?? POS_TABS[0]
  const isWpa = mode === 'leaders' && requestedStat === 'wpa'
  const activeTab = mode === 'leaders' ? statTab : posTab
  const players = leaders.filter(activeTab.filter)
  const primary = mode === 'leaders' ? STAT_PRIMARY[statTab.key] : POS_PRIMARY[posTab.key]
  const [wpaSubTab, setWpaSubTab] = useState<WpaSubTab>('passing')
  const [sorts, setSorts] = useState<Record<string, SortingState>>(() => Object.fromEntries(
    [...STAT_TABS, ...POS_TABS].map(tab => [tab.key, [{ id: tab.defaultSort, desc: true }]]),
  ))

  function updateParams(values: Record<string, string>) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(values)) next.set(key, value)
    setSearchParams(next, { replace: true })
  }

  const handleSortingChange: OnChangeFn<SortingState> = updater => {
    setSorts(previous => ({ ...previous, [activeTab.key]: functionalUpdate(updater, previous[activeTab.key]) }))
  }

  const tableContent = leadersQuery.isPending
    ? <div className="p-8"><QueryLoading>Loading player statistics…</QueryLoading></div>
    : leadersQuery.data === undefined ? null
    : !players.length ? <p className="p-8 text-ink-dim text-sm">No {activeTab.label} data for {season}.</p>
    : <LeaderTable players={players} cols={activeTab.cols} sorting={sorts[activeTab.key]}
        onSortingChange={handleSortingChange} view={mode === 'leaders' ? 'stats' : 'positions'} />

  let content
  if (seasonsQuery.isPending) {
    content = <QueryLoading>Loading seasons…</QueryLoading>
  } else if (seasonsQuery.isError && !seasonsQuery.data) {
    content = <QueryFailure resource="seasons" error={seasonsQuery.error} hasData={false} onRetry={() => void seasonsQuery.refetch()} />
  } else if (!years.length) {
    content = <p className="text-ink-dim text-sm">No loaded seasons are available yet.</p>
  } else if (season === null) {
    content = <p role="alert" className="text-ink-dim text-sm">That season is unavailable. Choose a loaded season above.</p>
  } else {
    content = <>
      <QueryFailure resource="player statistics" error={leadersQuery.error} hasData={leadersQuery.data !== undefined} onRetry={() => void leadersQuery.refetch()} />
      <ReceivingDataNote rows={leaders} />
      {(PAST_AWARDS[season] || leaders.length > 0) && <AwardsSection season={season} leaders={leaders} />}
      {leaders.length > 0 && <StatDashboard leaders={leaders} onPick={tab => updateParams({ mode: 'leaders', tab })} />}
      <LeaderControls mode={mode} statKey={isWpa ? 'wpa' : statTab.key} posKey={posTab.key}
        onModeChange={value => updateParams({ mode: value })}
        onStatChange={tab => updateParams({ tab })} onPositionChange={pos => updateParams({ pos })} />
      {isWpa ? <WpaPanel season={season} subTab={wpaSubTab} onSubTabChange={setWpaSubTab} /> : <>
        {players.length >= 3 && primary && <Podium players={players} primary={primary} />}
        {mode === 'leaders'
          ? <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden">{tableContent}</div>
          : <Card title={`${posTab.label} leaders`}>{tableContent}</Card>}
      </>}
    </>
  }

  return (
    <div className="min-h-screen bg-surface-bg">
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <LeaderHeader years={years} season={season} onSeasonChange={year => updateParams({ season: year })} />
        {seasonsQuery.data !== undefined && <QueryFailure resource="seasons" error={seasonsQuery.error} hasData onRetry={() => void seasonsQuery.refetch()} />}
        {content}
      </main>
    </div>
  )
}
