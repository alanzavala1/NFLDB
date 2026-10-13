import { useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, useLocation } from 'react-router-dom'
import type { LeagueLeader } from '../../types'
import type { PlayerLocationState } from '../../types/navigation'
import { leadersQueryOptions } from '../../api/leaders'
import { playerQueryOptions } from '../../api/players'
import Nav from '../../components/Nav'
import Card from '../../components/Card'
import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import { latestRegularSeason, selectPlayerCareer } from './selectors'
import { computeHighlightRanks } from './rankings'
import ProfileHeader from './ProfileHeader'
import BackgroundCard from './BackgroundCard'
import CareerTrajectory from './CareerTrajectory'
import HighlightsBar from './HighlightsBar'
import CareerTable from './CareerTable'
import TeamSplits from './TeamSplits'
import GameLog from './GameLog'
import ComparablesSection from './ComparablesSection'

export default function PlayerPage() {
  const { playerId } = useParams<{ playerId: string }>()
  const location = useLocation()
  const fromGame = (location.state as PlayerLocationState | null)?.fromGame

  const statsRef = useRef<HTMLDivElement>(null)
  const advRef   = useRef<HTMLDivElement>(null)
  const postRef   = useRef<HTMLDivElement>(null)
  const logRef    = useRef<HTMLDivElement>(null)
  const compRef   = useRef<HTMLDivElement>(null)
  function scrollTo(ref: { current: HTMLDivElement | null | undefined }) {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const playerQuery = useQuery(playerQueryOptions(playerId))
  const { data: player, isPending: loading } = playerQuery

  // Most recent regular season the player appears in -> drives the "5th in NFL" context
  const recentSeason = useMemo(() => player ? latestRegularSeason(player.games) : null, [player])

  const recentLeadersQuery = useQuery(leadersQueryOptions(recentSeason))
  const { data: recentLeadersData } = recentLeadersQuery
  const recentLeaders: { season: number; leaders: LeagueLeader[] } | null =
    recentSeason != null && recentLeadersData ? { season: recentSeason, leaders: recentLeadersData } : null

  if (loading) return <div className="min-h-screen bg-surface-bg"><Nav /><div className="p-8"><QueryLoading>Loading player profile…</QueryLoading></div></div>
  if (playerQuery.isError && !player) return (
    <div className="min-h-screen bg-surface-bg"><Nav /><div className="p-8">
      <QueryFailure resource="player profile" error={playerQuery.error} hasData={false} onRetry={() => void playerQuery.refetch()} />
    </div></div>
  )
  if (!player) return <div className="min-h-screen bg-surface-bg"><Nav /><p className="p-8 text-ink-dim">Player not found.</p></div>

  const {
    playoffGames, regBySeason, playoffBySeason, allBySeason, seasons, playoffSeasons,
    allSeasons, recentTeams, allTotals, careerGames, playerPos, hasAdvanced,
  } = selectPlayerCareer(player)

  // League ranks for the most recent regular season (computed once leaders load)
  const ranks: Record<string, string | null> = recentLeaders
    ? computeHighlightRanks(playerPos, player.player_id, recentLeaders.leaders, recentLeaders.season)
    : {}

  return (
    <div className="min-h-screen bg-surface-bg">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <QueryFailure resource="player profile" error={playerQuery.error} hasData onRetry={() => void playerQuery.refetch()} />
        <QueryFailure resource="league rank context" error={recentLeadersQuery.error} hasData={recentLeadersData !== undefined} onRetry={() => void recentLeadersQuery.refetch()} />
        {/* Profile header */}
        <ProfileHeader player={player} recentTeams={recentTeams} />

        {/* Background: draft pick + career achievements + combine.
            Always renders the same 3-card grid so the layout never shifts;
            each card has a filled and empty state. */}
        <BackgroundCard player={player} />

        {/* Highlights bar — regular season only */}
        {seasons.length > 0 && (
          <HighlightsBar
            pos={playerPos}
            totals={allTotals}
            games={careerGames}
            ngs={player.ngs ?? {}}
            ranks={ranks}
          />
        )}

        {/* Career trajectory chart — primary stat by season */}
        {seasons.length > 1 && (
          <CareerTrajectory seasons={seasons} bySeason={regBySeason} pos={playerPos} />
        )}

        {/* Sticky section nav */}
        {seasons.length > 0 && (
          <div className="sticky top-14 z-20 mb-6 flex gap-1 overflow-x-auto rounded-card bg-surface-card px-2 shadow-xl">
            <button onClick={() => scrollTo(statsRef)} className="relative px-3 py-3 text-xs font-semibold text-indigo-400 after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:bg-indigo-400">Stats</button>
            {hasAdvanced && <button onClick={() => scrollTo(advRef)} className="px-3 py-1.5 text-xs font-semibold text-ink-mid hover:text-ink rounded-lg hover:bg-surface-raise transition-colors">Advanced</button>}
            {playoffSeasons.length > 0 && <button onClick={() => scrollTo(postRef)} className="px-3 py-1.5 text-xs font-semibold text-ink-mid hover:text-ink rounded-lg hover:bg-surface-raise transition-colors">Postseason</button>}
            <button onClick={() => scrollTo(logRef)} className="px-3 py-1.5 text-xs font-semibold text-ink-mid hover:text-ink rounded-lg hover:bg-surface-raise transition-colors">Game Log</button>
            <button onClick={() => scrollTo(compRef)} className="px-3 py-1.5 text-xs font-semibold text-ink-mid hover:text-ink rounded-lg hover:bg-surface-raise transition-colors">Comparables</button>
          </div>
        )}

        {/* Regular season — main stats */}
        <div ref={statsRef} className="scroll-mt-12" />
        {!player.games.length && <p role="status" className="text-sm text-ink-dim mb-4">No game statistics are available for this player yet.</p>}
        <CareerTable
          title="Regular Season"
          seasons={seasons}
          bySeason={regBySeason}
          ngs={player.ngs ?? {}}
          snapTotals={player.snap_totals ?? {}}
          situational={player.situational ?? {}}
          kicking={player.kicking ?? {}}
          wpa={player.wpa ?? {}}
          advStats={player.adv_stats ?? {}}
          position={player.position}
          onlyKinds={['trad', 'snap']}
          showGroupHeaders={true}
        />
        {/* Regular season — advanced stats */}
        {hasAdvanced && seasons.length > 0 && (
          <>
            <div ref={advRef} className="scroll-mt-12" />
            <CareerTable
              title="Advanced Stats"
              seasons={seasons}
              bySeason={regBySeason}
              ngs={player.ngs ?? {}}
              snapTotals={player.snap_totals ?? {}}
              situational={player.situational ?? {}}
              wpa={player.wpa ?? {}}
              advStats={player.adv_stats ?? {}}
              position={player.position}
              onlyKinds={['adv', 'ngs', 'sit']}
            />
          </>
        )}

        {/* Postseason stats */}
        {playoffSeasons.length > 0 && (
          <>
            <div ref={postRef} className="scroll-mt-12" />
            <CareerTable
              title={`Postseason · ${playoffGames.length} game${playoffGames.length !== 1 ? 's' : ''}`}
              seasons={playoffSeasons}
              bySeason={playoffBySeason}
              ngs={{}}
              snapTotals={player.snap_totals ?? {}}
              situational={{}}
              position={player.position}
              onlyKinds={['trad', 'snap', 'adv']}
              showGroupHeaders={false}
            />

          </>
        )}


        {/* Team splits — regular season only */}
        <TeamSplits seasons={seasons} bySeason={regBySeason} position={player.position} />

        {/* Game log — all games, playoff games show their round label */}
        <div ref={logRef} className="scroll-mt-12" />
        <Card title="Game Log" className="mb-4"><div className="space-y-2 border-t border-surface-line p-3">
          {allSeasons.map((s, i) => (
            <GameLog
              key={s}
              season={s}
              games={allBySeason[s]}
              pos={playerPos}
              playerId={player.player_id}
              playerName={player.player_name}
              fromGame={fromGame}
              defaultOpen={i === 0}
            />
          ))}
        </div></Card>

        {/* Similar players */}
        {seasons.length > 0 && (
          <div ref={compRef} className="scroll-mt-12">
            <ComparablesSection playerId={player.player_id} pos={playerPos} />
          </div>
        )}

      </div>
    </div>
  )
}
