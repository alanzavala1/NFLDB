import { Link } from 'react-router-dom'
import type { GameDetail, GameLineup, LiveGameOut } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl, teamName } from '../../utils/teams'
import { weekLabel, formatGameday } from './formatting'
import { GameScorers } from './GameScorers'

export type GameTab = 'overview' | 'lineup' | 'stats' | 'plays'

export function GameHeader({ game, lineup, tab, onTab, live }: { game: GameDetail; lineup: GameLineup | null; tab: GameTab; onTab: (tab: GameTab) => void; live?: LiveGameOut | null }) {
  const isLive = live?.state === 'in'
  const dbFinal = game.away_score != null && game.home_score != null
  // Between the final whistle and the next ingest — hours, every game day — the
  // database has no score but the live source does. Without this the page calls
  // a finished game Upcoming.
  const awayScore = dbFinal ? game.away_score : live?.away_score ?? null
  const homeScore = dbFinal ? game.home_score : live?.home_score ?? null
  const final = !isLive && (dbFinal || live?.state === 'post')
  const charted = game.away.length > 0 || game.home.length > 0
  const awayWon = final && awayScore != null && homeScore != null && awayScore > homeScore
  const homeWon = final && awayScore != null && homeScore != null && homeScore > awayScore
  return <Card className="mb-5">
    <div className={`flex items-center gap-4 border-b border-surface-line px-4 py-3 ${game.game_type === 'SB' ? 'bg-gradient-to-r from-gold/25 via-gold/10 to-transparent' : 'bg-surface-raise'}`}><div className="min-w-0"><div className={`text-[10px] font-bold uppercase tracking-[.14em] ${game.game_type === 'SB' ? 'text-gold' : 'text-ink-dim'}`}>{weekLabel(game.week)}</div><div className="mt-0.5 truncate text-xs text-ink-mid">{formatGameday(game.gameday)}{game.stadium ? ` · ${game.stadium}` : ''}</div></div><div className={`ml-auto shrink-0 text-[10px] font-bold uppercase tracking-[.14em] ${isLive ? 'text-data-live' : 'text-ink-dim'}`}>{isLive ? <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-data-live motion-reduce:animate-none" />Live</span> : final ? 'Final' : 'Upcoming'}</div></div>
    <div className="flex items-center gap-2 px-4 py-6 sm:px-6">
      <Link to={`/teams/${game.away_team}`} className={`group flex flex-1 flex-col items-center gap-2 sm:flex-row ${awayWon || !final ? '' : 'opacity-50'}`}><img src={teamLogoUrl(game.away_team)} alt="" className="h-12 w-12 object-contain sm:h-16 sm:w-16" /><div className="text-center sm:text-left"><div className="text-xs font-bold text-ink group-hover:text-indigo-400 sm:text-sm">{teamName(game.away_team)}</div>{game.away_record && <div className="text-[10px] text-ink-dim sm:text-xs">{game.away_record}</div>}</div></Link>
      <div className="flex shrink-0 flex-col items-center gap-1" aria-live="polite">{isLive ? <><div className="flex items-center gap-2 sm:gap-3"><span className="text-3xl font-black tabular-nums text-ink sm:text-5xl">{live?.away_score ?? 0}</span><span className="text-xl text-ink-dim">–</span><span className="text-3xl font-black tabular-nums text-ink sm:text-5xl">{live?.home_score ?? 0}</span></div><div className="text-[11px] font-bold uppercase tracking-[.12em] tabular-nums text-data-live">{live?.period ? `Q${live.period}` : 'Live'}{live?.clock ? ` · ${live.clock}` : ''}</div>{live?.possession && <div className="text-[10px] font-bold uppercase tracking-[.12em] text-ink-dim">{live.possession} ball</div>}</> : final ? <div className="flex items-center gap-2 sm:gap-3"><span className={`text-3xl font-black tabular-nums sm:text-5xl ${awayWon ? 'text-ink' : 'text-ink-dim'}`}>{awayScore}</span><span className="text-xl text-ink-dim">–</span><span className={`text-3xl font-black tabular-nums sm:text-5xl ${homeWon ? 'text-ink' : 'text-ink-dim'}`}>{homeScore}</span></div> : <span className="text-sm text-ink-dim">Upcoming</span>}</div>
      <Link to={`/teams/${game.home_team}`} className={`group flex flex-1 flex-col items-center gap-2 sm:flex-row-reverse ${homeWon || !final ? '' : 'opacity-50'}`}><img src={teamLogoUrl(game.home_team)} alt="" className="h-12 w-12 object-contain sm:h-16 sm:w-16" /><div className="text-center sm:text-right"><div className="text-xs font-bold text-ink group-hover:text-indigo-400 sm:text-sm">{teamName(game.home_team)}</div>{game.home_record && <div className="text-[10px] text-ink-dim sm:text-xs">{game.home_record}</div>}</div></Link>
    </div>
    {lineup && <GameScorers lineup={lineup} />}
    <div className="flex overflow-x-auto border-t border-surface-line px-2">{([['overview', 'Overview'], ['lineup', 'Lineup'], ['stats', 'Stats'], ['plays', 'Plays']] as const).map(([key, label]) => {
      // Everything but Overview is built from charted play-by-play, which
      // doesn't exist until hours after the whistle. A disabled tab that says
      // why beats a tab that opens onto nothing.
      const uncharted = key !== 'overview' && !charted
      return <button key={key} type="button" disabled={uncharted} onClick={() => onTab(key)} title={uncharted ? 'Available once the game is charted' : undefined} className={`relative min-w-24 px-4 py-3 text-xs font-bold ${uncharted ? 'cursor-not-allowed text-ink-dim/40' : tab === key ? 'text-indigo-400 after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:bg-indigo-400' : 'text-ink-dim hover:text-ink'}`}>{label}</button>
    })}</div>
  </Card>
}
