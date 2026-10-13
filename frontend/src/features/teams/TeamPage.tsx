import { useParams } from 'react-router-dom'
import { useQuery, useQueries } from '@tanstack/react-query'
import { seasonsQueryOptions } from '../../api/seasons'
import { loadedSeasons } from '../../utils/seasons'
import { useState } from 'react'
import { teamQueryOptions } from '../../api/teams'
import Nav from '../../components/Nav'
import { QueryLoading, QueryFailure } from '../../components/QueryFeedback'
import { computeRecord } from './selectors'
import Card from '../../components/Card'
import { teamName, teamLogoUrl } from '../../utils/teams'
import SeasonSidebar from './SeasonSidebar'
import SeasonDetail from './SeasonDetail'

const INITIAL_SEASONS = 5

export default function TeamPage() {
  const { teamAbbrev } = useParams<{ teamAbbrev: string }>()
  const seasonsQuery = useQuery(seasonsQueryOptions())
  const availableYears = loadedSeasons(seasonsQuery.data ?? [])
  const [expandedYears, setExpandedYears] = useState<number[]>([])
  const [requestedSeason, setRequestedSeason] = useState<number | null>(null)
  const visibleYears = availableYears.filter((year, index) => index < INITIAL_SEASONS || expandedYears.includes(year))
  const selectedSeason = requestedSeason !== null && visibleYears.includes(requestedSeason)
    ? requestedSeason : visibleYears[0]
  const nextYear = availableYears.find(year => !visibleYears.includes(year))
  const profileQueries = useQueries({ queries: visibleYears.map(year => teamQueryOptions(teamAbbrev, year)) })
  const profiles = profileQueries.flatMap(query => query.data ? [query.data] : [])
  const activeQuery = profileQueries[visibleYears.indexOf(selectedSeason)]
  const activeProfile = activeQuery?.data

  if (!teamAbbrev) return <div className="min-h-screen bg-surface-bg"><Nav /><p className="p-8 text-ink-dim">Team not found.</p></div>
  if (seasonsQuery.isPending) return (
    <div className="min-h-screen bg-surface-bg"><Nav /><div className="p-8"><QueryLoading>Loading available seasons…</QueryLoading></div></div>
  )
  if (seasonsQuery.isError && !seasonsQuery.data) return (
    <div className="min-h-screen bg-surface-bg"><Nav /><div className="p-8">
      <QueryFailure resource="available seasons" error={seasonsQuery.error} hasData={false} onRetry={() => void seasonsQuery.refetch()} />
    </div></div>
  )

  const allTime = computeRecord(profiles.flatMap(profile => profile.games), teamAbbrev)
  return (
    <div className="min-h-screen bg-surface-bg">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <QueryFailure resource="available seasons" error={seasonsQuery.error} hasData onRetry={() => void seasonsQuery.refetch()} />
        {profileQueries.map((query, index) => (
          <QueryFailure key={visibleYears[index]} resource={`${visibleYears[index]} team profile`} error={query.error}
            hasData={query.data !== undefined} onRetry={() => void query.refetch()} />
        ))}
        <Card title={teamName(teamAbbrev)} className="mb-8"><div className="flex items-center gap-5 border-t border-surface-line p-5">
          <img src={teamLogoUrl(teamAbbrev)} alt={teamAbbrev} className="w-20 h-20 object-contain shrink-0" />
          <div>
            {profiles.length > 0 && (
              <div className="text-ink-mid mt-1">
                {profiles.length} season{profiles.length !== 1 ? 's' : ''} loaded ·{' '}
                <span className="text-ink font-semibold">{allTime.label}</span>
                <span className="text-ink-dim text-xs ml-2">{allTime.w + allTime.l + allTime.t} games</span>
              </div>
            )}
            {!availableYears.length && <p className="text-ink-dim mt-1">No published season statistics are available for this team.</p>}
          </div>
        </div></Card>

        {visibleYears.length > 0 && (
          <div className="flex flex-col lg:flex-row gap-4 lg:items-start">
            <SeasonSidebar profiles={profiles} years={visibleYears} selected={selectedSeason}
              onSelect={setRequestedSeason} nextYear={nextYear}
              onShowOlder={year => setExpandedYears(previous => [...previous, year])} />
            <div className="flex-1 min-w-0 w-full">
              {activeQuery?.isPending && <QueryLoading>Loading team profile…</QueryLoading>}
              {activeProfile && <SeasonDetail key={`${teamAbbrev}-${activeProfile.season}`} profile={activeProfile} />}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
