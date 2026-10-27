import ReceivingDataNote from '../../components/ReceivingDataNote'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, useLocation } from 'react-router-dom'
import { gameQueryOptions, gameLineupQueryOptions } from '../../api/games'
import { scheduleQueryOptions } from '../../api/schedule'
import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import Nav from '../../components/Nav'
import LiveGameCard from '../../components/LiveGameCard'
import { useLiveGame } from '../live-scores/useLiveGame'
import type { GameOrigin, GameLocationState } from '../../types/navigation'
import { GameHeader, type GameTab } from './GameHeader'
import { QuarterScore } from './QuarterScore'
import { BoxScore } from './BoxScore'
import { GameLeaders } from './GameLeaders'
import { PlayerStatSections } from './PlayerStatSections'
import { ScoringSummary } from './ScoringSummary'
import { KeyPlays } from './KeyPlays'
import { WinProbabilityChart } from './WinProbabilityChart'
import GameLineupView from './GameLineupView'
import { GameRail } from './GameRail'
import { LINEUP_CSS } from './styles'
import { selectSameRound } from './selectors'

function GamePageBody() {
  const { gameId } = useParams<{ gameId: string }>()
  const live = useLiveGame(gameId)
  const location = useLocation()
  const fromWeek = (location.state as GameLocationState | null)?.fromWeek
  const gameQuery = useQuery(gameQueryOptions(gameId))
  const { data: game } = gameQuery
  const [tab, setTab] = useState<GameTab>('overview')
  const lineupQuery = useQuery(gameLineupQueryOptions(gameId))
  const lineup = lineupQuery.data ?? null
  const scheduleQuery = useQuery(scheduleQueryOptions(game?.season ?? null))
  const weeks = scheduleQuery.data
  // Show the live card only while there is nothing charted to replace it.
  const showLiveCard = !!live && live.state !== 'pre' && !!game && game.away.length === 0 && game.home.length === 0

  const sameRound = useMemo(() => selectSameRound(game, weeks), [game, weeks])

  if (gameQuery.isPending) return <div className="min-h-screen bg-surface-bg"><Nav /><div className="p-8"><QueryLoading>Loading game…</QueryLoading></div></div>
  if (gameQuery.isError && !game) return <div className="min-h-screen bg-surface-bg"><Nav /><div className="p-8">
    <QueryFailure resource="game" error={gameQuery.error} hasData={false} onRetry={() => void gameQuery.refetch()} />
  </div></div>
  if (!game) return <div className="min-h-screen bg-surface-bg"><Nav /><p className="p-8 text-ink-dim">Game not found.</p></div>

  const origin: GameOrigin = {
    gameId: game.game_id, season: game.season, week: game.week,
    awayTeam: game.away_team, homeTeam: game.home_team, fromWeek,
  }

  return (
    <div className="min-h-screen bg-surface-bg">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <style>{LINEUP_CSS}</style>
        <QueryFailure resource="game" error={gameQuery.error} hasData onRetry={() => void gameQuery.refetch()} />
        <QueryFailure resource="lineup" error={lineupQuery.error} hasData={lineupQuery.data !== undefined} onRetry={() => void lineupQuery.refetch()} />
        {lineupQuery.isPending && <QueryLoading>Loading lineup…</QueryLoading>}
        <QueryFailure resource="game schedule" error={scheduleQuery.error} hasData={weeks !== undefined} onRetry={() => void scheduleQuery.refetch()} />
        <ReceivingDataNote rows={[...game.away, ...game.home]} />
        <GameHeader game={game} lineup={lineup} tab={tab} onTab={setTab} live={live} />
        <div className="lineup-page">
          <main className="feed">
            {tab === 'overview' && (
              <>
                {showLiveCard && live && <LiveGameCard live={live} />}
                <QuarterScore game={game} />
                <ScoringSummary game={game} />
                <WinProbabilityChart game={game} />
                <KeyPlays game={game} />
                <GameLeaders game={game} origin={origin} />
                <BoxScore game={game} />
              </>
            )}
            {tab === 'lineup' && lineup && <GameLineupView game={game} lineup={lineup} />}
            {tab === 'stats' && (
              <>
                <BoxScore game={game} />
                {(game.away.length > 0 || game.home.length > 0) && <PlayerStatSections game={game} origin={origin} />}
              </>
            )}
            {tab === 'plays' && (
              <>
                <ScoringSummary game={game} />
                <WinProbabilityChart game={game} />
                <KeyPlays game={game} />
              </>
            )}
          </main>
          {lineup && <GameRail game={game} lineup={lineup} sameRound={sameRound} scheduleFeedback={
            scheduleQuery.isPending ? <QueryLoading>Loading game schedule…</QueryLoading>
              : weeks !== undefined && sameRound.length === 0 ? <p className="micro">No other game results are available for this round.</p> : null
          } />}
        </div>
      </div>
    </div>
  )
}

export default function GamePage() {
  const { gameId } = useParams<{ gameId: string }>()
  return <GamePageBody key={gameId} />
}
