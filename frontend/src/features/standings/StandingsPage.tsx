import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { seasonsQueryOptions } from '../../api/seasons'
import Nav from '../../components/Nav'
import Card from '../../components/Card'
import { PlayoffBracket } from '../../components/PlayoffBracket'
import { QueryError, QueryLoading } from '../../components/QueryFeedback'
import { standingsQueryOptions } from './queries'
import { loadedSeasons, selectedSeason } from './season'
import { ConferenceSection } from './StandingsTable'

export default function StandingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const seasons = useQuery(seasonsQueryOptions())
  const available = loadedSeasons(seasons.data ?? [])
  const season = selectedSeason(searchParams.get('season'), available)
  const standings = useQuery(standingsQueryOptions(season))

  let content
  if (seasons.isPending) {
    content = <QueryLoading>Loading seasons…</QueryLoading>
  } else if (seasons.isError && !seasons.data) {
    content = <QueryError message={`Could not load seasons. ${seasons.error.message}`} onRetry={() => void seasons.refetch()} />
  } else if (!available.length) {
    content = <p className="text-ink-dim text-sm">No loaded seasons are available yet.</p>
  } else if (season === null) {
    content = <p role="alert" className="text-ink-dim text-sm">That season is unavailable. Choose a loaded season above.</p>
  } else if (standings.isPending) {
    content = <QueryLoading>Loading standings…</QueryLoading>
  } else if (standings.isError && !standings.data) {
    content = <QueryError message={`Could not load standings. ${standings.error.message}`} onRetry={() => void standings.refetch()} />
  } else if (!standings.data?.length) {
    content = <p className="text-ink-dim text-sm">No standings data for {season}.</p>
  } else {
    content = <>
      <PlayoffBracket season={season} />
      <ConferenceSection divisions={standings.data.filter(d => d.division.startsWith('AFC'))} />
      <ConferenceSection divisions={standings.data.filter(d => d.division.startsWith('NFC'))} />
    </>
  }

  return (
    <div className="min-h-screen bg-surface-bg">
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <Card title="Standings" className="mb-5">
          <div className="flex items-center justify-between gap-4 border-t border-surface-line px-4 py-3">
            <p className="text-ink-dim text-[10px] uppercase tracking-widest font-bold">{season === null ? 'NFL Season' : `${season} NFL Season`}</p>
            <select
              aria-label="Season"
              value={season ?? ''}
              disabled={!available.length}
              onChange={e => {
                const next = new URLSearchParams(searchParams)
                next.set('season', e.target.value)
                setSearchParams(next)
              }}
              className="bg-surface-raise border border-surface-line text-ink text-sm font-semibold rounded-lg px-4 py-2.5 focus:outline-none focus:border-indigo-500 cursor-pointer hover:border-surface-line transition-colors"
            >
              {season === null && <option value="" disabled>Choose a season</option>}
              {available.map(year => <option key={year} value={year}>{year}</option>)}
            </select>
          </div>
        </Card>
        {seasons.isError && seasons.data && <QueryError message="Could not refresh the season list. Showing the last successful result." onRetry={() => void seasons.refetch()} />}
        {standings.isError && standings.data && <QueryError message="Could not refresh standings. Showing the last successful result." onRetry={() => void standings.refetch()} />}
        {content}
      </main>
    </div>
  )
}
