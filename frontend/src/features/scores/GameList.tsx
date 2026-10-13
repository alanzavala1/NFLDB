import type { Game, LiveGameOut } from '../../types'
import Card, { CardRow } from '../../components/Card'
import { useLiveGame } from '../../hooks/useLiveScores'
import { teamLogoUrl, teamNickname } from '../../utils/teams'
import {
  MICRO, recordText, isFinished, gameWinner, formatTimeShort, formatMonthDay,
  finalLabel, formatSpread, formatTotalLine, dayAbbrev,
} from './presentation'

function GameTeam({
  team,
  record,
  won,
  finished,
  align,
}: {
  team: string
  record?: string | null
  won: boolean
  finished: boolean
  align: 'left' | 'right'
}) {
  return (
    <div className={`flex min-w-0 items-center gap-2 max-[780px]:gap-1.5 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}>
      <img src={teamLogoUrl(team)} className="h-8 w-8 shrink-0 object-contain max-[780px]:h-6 max-[780px]:w-6" alt="" />
      <div className="min-w-0">
        <div className={`truncate text-sm font-bold max-[780px]:text-[13px] ${finished && !won ? 'text-ink-dim' : 'text-ink'}`}>{teamNickname(team)}</div>
        <div className="truncate text-xs text-ink-dim">{recordText(record)}</div>
      </div>
    </div>
  )
}

function LiveScoreBlock({ live }: { live: LiveGameOut }) {
  // No dimming of a "losing" side here: the game isn't over, and greying out a
  // team that is one score behind reads as a result it hasn't earned.
  return (
    <div className="min-w-[78px] text-center" aria-live="polite">
      <div className="flex items-center justify-center gap-1.5 text-xl font-black tabular-nums text-ink">
        <span>{live.away_score ?? 0}</span>
        <span className="text-ink-dim">-</span>
        <span>{live.home_score ?? 0}</span>
      </div>
      <div className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.12em] tabular-nums text-data-live">
        {live.period ? `Q${live.period}` : 'LIVE'}{live.clock ? ` · ${live.clock}` : ''}
      </div>
    </div>
  )
}

function GameScoreBlock({ game, live }: { game: Game; live?: LiveGameOut | null }) {
  const finished = isFinished(game)
  const awayWon = gameWinner(game) === game.away_team
  const homeWon = gameWinner(game) === game.home_team

  if (live?.state === 'in') return <LiveScoreBlock live={live} />

  if (!finished) {
    return (
      <div className="min-w-[72px] text-center">
        <div className="text-sm font-black tabular-nums text-ink">{formatTimeShort(game.gametime)}</div>
        <div className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-dim">{formatMonthDay(game.gameday)}</div>
      </div>
    )
  }

  return (
    <div className="min-w-[78px] text-center">
      <div className="flex items-center justify-center gap-1.5 text-xl font-black tabular-nums">
        <span className={awayWon ? 'text-ink' : 'text-ink-dim'}>{game.away_score}</span>
        <span className="text-ink-dim">-</span>
        <span className={homeWon ? 'text-ink' : 'text-ink-dim'}>{game.home_score}</span>
      </div>
      <div className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-dim">{finalLabel(game)}</div>
    </div>
  )
}

function MarketLineMeta({ spread, total, label }: { spread: string | null; total: string | null; label: string }) {
  if (!spread && !total) {
    return <div className="justify-self-end text-right text-xs font-bold text-ink-dim max-[780px]:hidden">Line TBD</div>
  }

  return (
    <div className="justify-self-end rounded-lg border border-surface-line bg-surface-raise/45 px-3 py-2 text-right max-[780px]:hidden">
      <div className="mb-1 text-[9px] font-black uppercase tracking-[0.12em] text-ink-dim">{label}</div>
      <div className="flex flex-col items-end gap-0.5">
        {spread && <div className="text-xs font-bold tabular-nums text-ink">{spread}</div>}
        {total && <div className="text-xs font-bold tabular-nums text-ink">{total}</div>}
      </div>
    </div>
  )
}

function GameRow({ game }: { game: Game }) {
  const live = useLiveGame(game.game_id)
  const isLive = live?.state === 'in'
  // A game in progress is not finished, whatever the stored scores say.
  const finished = !isLive && isFinished(game)
  const winner = finished ? gameWinner(game) : null
  const spread = formatSpread(game)
  const total = formatTotalLine(game)

  return (
    <CardRow
      to={`/games/${game.game_id}`}
      className="grid grid-cols-[40px_minmax(0,1fr)_auto_minmax(0,1fr)_116px] gap-3 py-[13px] max-[780px]:grid-cols-[40px_minmax(0,1fr)_auto_minmax(0,1fr)] max-[780px]:gap-2"
    >
      {isLive ? (
        <span
          className="grid h-8 w-10 place-items-center gap-[3px] rounded-lg bg-surface-raise text-[9px] font-black uppercase tracking-[0.1em] text-data-live"
          title={live?.detail ?? 'In progress'}
        >
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-data-live motion-reduce:animate-none" />
            LIVE
          </span>
        </span>
      ) : (
        <span className="grid h-8 w-10 place-items-center rounded-lg bg-surface-raise text-[10px] font-black uppercase tracking-[0.12em] text-ink-mid">
          {finished ? 'FT' : dayAbbrev(game.gameday)}
        </span>
      )}
      <GameTeam
        team={game.away_team}
        record={game.away_record}
        won={winner === game.away_team}
        finished={finished}
        align="left"
      />
      <GameScoreBlock game={game} live={live} />
      <GameTeam
        team={game.home_team}
        record={game.home_record}
        won={winner === game.home_team}
        finished={finished}
        align="right"
      />
      {isLive
        ? <div className="justify-self-end text-right text-xs font-bold tabular-nums text-ink-mid max-[780px]:hidden">
            {live?.possession ? `${live.possession} ball` : 'In progress'}
          </div>
        : spread || total
          ? <MarketLineMeta spread={spread} total={total} label={finished ? 'Closing' : 'Line'} />
          : <div className="justify-self-end text-right text-xs font-bold text-ink-dim max-[780px]:hidden">{finished ? 'View' : 'Line TBD'}</div>
      }
    </CardRow>
  )
}

export function KickoffSlotCard({ label, games }: { label: string; games: Game[] }) {
  const hasLineData = games.some(game => game.spread_line !== null || game.total_line !== null)
  const countLabel = `${games.length} game${games.length === 1 ? '' : 's'}`

  return (
    <Card
      title={<span className={MICRO}>{label}</span>}
      action={<span className="text-xs font-bold text-ink-dim">{hasLineData ? `${countLabel} · lines via nflverse` : countLabel}</span>}
    >
      {games.map(game => <GameRow key={game.game_id} game={game} />)}
    </Card>
  )
}
