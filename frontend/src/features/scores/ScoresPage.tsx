import { useMemo, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { ScheduleWeek } from '../../types'
import { seasonsQueryOptions } from '../../api/seasons'
import { scheduleQueryOptions } from '../../api/schedule'
import { leadersQueryOptions } from '../../api/leaders'
import { powerRankingsQueryOptions } from '../../api/powerRankings'
import { standingsQueryOptions } from '../standings/queries'
import { QueryFailure } from '../../components/QueryFeedback'
import { LiveScoresProvider } from '../../hooks/useLiveScores'
import Card, { CardRow } from '../../components/Card'
import Nav from '../../components/Nav'
import { SeasonCard } from './SeasonCard'
import { WeekNavigator } from './WeekNavigator'
import { FeaturedGameHero } from './FeaturedGame'
import { KickoffSlotCard } from './GameList'
import { StorylinesCard } from './Storylines'
import { LastSeasonRecap } from './SeasonRecap'
import { TeamsCard, ConferenceLeadersCard, LeagueLeadersCard } from './SidebarPanels'
import { parseNumberParam, defaultSeason, SELECTABLE, findCurrentWeek, pickFeaturedGame, groupKickoffSlots } from './selectors'
import { isFinished } from './presentation'

const EMPTY_SCHEDULE: ScheduleWeek[] = []

function StatusCard({ title, message }: { title: string; message: ReactNode }) {
  return (
    <Card title={title}>
      <CardRow className="text-sm text-ink-dim">{message}</CardRow>
    </Card>
  )
}

function ScoresPageBody() {
  const [searchParams, setSearchParams] = useSearchParams()
  const seasonsQuery = useQuery(seasonsQueryOptions())
  const seasons = seasonsQuery.data ?? []
  const seasonFromUrl = parseNumberParam(searchParams.get('season'))
  const season = seasonFromUrl ?? defaultSeason(seasons)
  const requestedWeek = parseNumberParam(searchParams.get('week'))
  const seasonEntry = seasons.find(entry => entry.season === season)
  const canReadSeason = seasonEntry !== undefined && SELECTABLE.has(seasonEntry.status)
  const querySeason = canReadSeason ? season : null
  const scheduleQuery = useQuery(scheduleQueryOptions(querySeason))
  const standingsQuery = useQuery(standingsQueryOptions(querySeason))
  const leadersQuery = useQuery(leadersQueryOptions(querySeason))
  const powerQuery = useQuery(powerRankingsQueryOptions(querySeason))
  const schedule = scheduleQuery.data ?? EMPTY_SCHEDULE
  const seasonGames = useMemo(() => schedule.flatMap(group => group.games), [schedule])
  const defaultWeek = useMemo(() => findCurrentWeek(schedule), [schedule])
  const activeGroup = schedule.find(group => group.week === (requestedWeek ?? defaultWeek))
    ?? schedule.find(group => group.week === defaultWeek)
    ?? schedule[0]
    ?? null
  const activeWeek = activeGroup?.week ?? null
  const featuredGame = activeGroup ? pickFeaturedGame(activeGroup.games) : null
  const slotGames = activeGroup
    ? activeGroup.games.filter(game => game.game_id !== featuredGame?.game_id)
    : []
  const kickoffSlots = groupKickoffSlots(slotGames)
  const seasonFinished = seasonGames.filter(isFinished).length
  const showRecap = season !== null && seasonFinished < 3

  function setSeasonParam(nextSeason: number) {
    const next = new URLSearchParams(searchParams)
    next.set('season', String(nextSeason))
    next.delete('week')
    next.delete('view')
    setSearchParams(next)
  }

  function setWeekParam(nextWeek: number) {
    if (season === null) return
    const next = new URLSearchParams(searchParams)
    next.set('season', String(season))
    next.set('week', String(nextWeek))
    next.delete('view')
    setSearchParams(next)
  }

  let centerContent
  if (seasonsQuery.isPending) {
    centerContent = <StatusCard title="Season" message="Loading seasons..." />
  } else if (seasonsQuery.isError && !seasonsQuery.data) {
    centerContent = <StatusCard title="Season unavailable" message={<QueryFailure resource="seasons" error={seasonsQuery.error} hasData={false} onRetry={() => void seasonsQuery.refetch()} />} />
  } else if (season === null) {
    centerContent = <StatusCard title="Season unavailable" message="No seasons are available yet." />
  } else if (!canReadSeason) {
    centerContent = <StatusCard title="Season unavailable" message="Scores for this season are not available yet." />
  } else if (scheduleQuery.isPending) {
    centerContent = <StatusCard title={`${season} scores`} message="Loading schedule..." />
  } else if (scheduleQuery.isError && !scheduleQuery.data) {
    centerContent = <StatusCard title={`${season} scores`} message={<QueryFailure resource="schedule" error={scheduleQuery.error} hasData={false} onRetry={() => void scheduleQuery.refetch()} />} />
  } else if (!schedule.length) {
    centerContent = <StatusCard title={`${season} scores`} message="No games found." />
  } else {
    centerContent = (
      <>
        <WeekNavigator schedule={schedule} activeWeek={activeWeek} season={season} onWeekChange={setWeekParam} />
        {featuredGame && <FeaturedGameHero game={featuredGame} />}
        {kickoffSlots.map(slot => <KickoffSlotCard key={slot.key} label={slot.label} games={slot.games} />)}
        {activeGroup && (
          <StorylinesCard
            weekGames={activeGroup.games}
            seasonGames={seasonGames}
            omitGameId={featuredGame?.game_id}
          />
        )}
        {showRecap && <LastSeasonRecap season={season} />}
      </>
    )
  }

  return (
    <>
      <Nav />
      <main className="mx-auto grid max-w-[1460px] grid-cols-[250px_minmax(0,1fr)_330px] gap-5 px-7 pb-16 pt-5 max-[1100px]:grid-cols-[minmax(0,1fr)_330px] max-[780px]:grid-cols-1 max-[780px]:px-3 max-[780px]:pb-12 max-[780px]:pt-4">
        <aside className="grid h-fit gap-5 max-[1100px]:hidden">
          <SeasonCard
            seasons={seasons}
            season={season}
            onSeasonChange={setSeasonParam}
          />
          {canReadSeason && <TeamsCard rankings={powerQuery.data} loading={powerQuery.isPending} error={powerQuery.error} onRetry={() => void powerQuery.refetch()} />}
        </aside>

        <section className="grid min-w-0 content-start gap-5">
          {seasonsQuery.data !== undefined && <QueryFailure resource="seasons" error={seasonsQuery.error} hasData onRetry={() => void seasonsQuery.refetch()} />}
          {scheduleQuery.data !== undefined && <QueryFailure resource="schedule" error={scheduleQuery.error} hasData onRetry={() => void scheduleQuery.refetch()} />}
          {centerContent}
        </section>

        <aside className="grid h-fit gap-5">
          {season !== null && canReadSeason && (
            <>
              <ConferenceLeadersCard conference="AFC" standings={standingsQuery.data} season={season} loading={standingsQuery.isPending} error={standingsQuery.error} onRetry={() => void standingsQuery.refetch()} />
              <ConferenceLeadersCard conference="NFC" standings={standingsQuery.data} season={season} loading={standingsQuery.isPending} error={standingsQuery.error} onRetry={() => void standingsQuery.refetch()} />
              <LeagueLeadersCard season={season} leaders={leadersQuery.data} loading={leadersQuery.isPending} error={leadersQuery.error} onRetry={() => void leadersQuery.refetch()} />
            </>
          )}
        </aside>
      </main>
    </>
  )
}

export default function ScoresPage() {
  // One poll feeds every card on the page.
  return (
    <LiveScoresProvider>
      <ScoresPageBody />
    </LiveScoresProvider>
  )
}
