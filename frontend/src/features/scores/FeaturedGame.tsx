import { Link } from 'react-router-dom'
import type { Game } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl, teamNickname } from '../../utils/teams'
import {
  MICRO, recordText, isFinished, gameWinner, formatSpread, formatTotalValue,
  formatKickoffFact, weekLabel, primetimeBadge, finalLabel,
} from './presentation'

function HeroTeam({
  team,
  record,
  score,
  won,
  finished,
  align,
}: {
  team: string
  record?: string | null
  score: number | null
  won: boolean
  finished: boolean
  align: 'left' | 'right'
}) {
  return (
    <div className={`flex min-w-0 items-center gap-3 max-[780px]:flex-col max-[780px]:gap-1 max-[780px]:text-center ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}>
      <img src={teamLogoUrl(team)} className="h-[52px] w-[52px] shrink-0 object-contain max-[780px]:h-11 max-[780px]:w-11" alt="" />
      <div className="min-w-0">
        <div className={`truncate text-[26px] font-black leading-none text-ink max-[780px]:overflow-visible max-[780px]:whitespace-normal max-[780px]:text-lg ${finished && !won ? 'text-ink-dim' : ''}`}>
          {teamNickname(team)}
        </div>
        <div className="mt-1 truncate text-xs text-ink-dim max-[780px]:max-w-28">
          {recordText(record)}
        </div>
        {finished && (
          <div className={`mt-1 text-4xl font-black tabular-nums leading-none max-[780px]:text-3xl ${won ? 'text-ink' : 'text-ink-dim'}`}>
            {score}
          </div>
        )}
      </div>
    </div>
  )
}

export function FeaturedGameHero({ game }: { game: Game }) {
  const finished = isFinished(game)
  const winner = gameWinner(game)
  const playoff = game.game_type === 'SB' || game.game_type === 'CON'
  const bandClass = playoff
    ? 'border-b border-gold/25 bg-linear-to-r from-gold/25 via-gold/10 to-transparent text-gold'
    : 'border-b border-surface-line bg-surface-raise text-ink-dim'
  const total = finished ? game.away_score! + game.home_score! : null
  const margin = finished ? Math.abs(game.away_score! - game.home_score!) : null
  const spread = formatSpread(game)
  const totalValue = formatTotalValue(game)
  const facts = finished
    ? [
        { label: 'Margin', value: margin?.toString() ?? '-' },
        { label: 'Total', value: total?.toString() ?? '-' },
        { label: 'Closing spread', value: spread ?? 'No line' },
        { label: 'Closing O/U', value: totalValue ?? 'No total' },
      ]
    : [
        { label: 'Kickoff', value: formatKickoffFact(game) },
        { label: 'Spread', value: spread ?? 'No line' },
        { label: 'O/U', value: totalValue ?? 'No total' },
        { label: 'Venue', value: game.stadium ?? 'TBD' },
      ]

  return (
    <Card>
      <div className={`flex items-center gap-3 px-4 py-[11px] ${bandClass}`}>
        <span className="text-[10px] font-bold uppercase tracking-[0.14em]">Featured</span>
        <span className="min-w-0 truncate text-xs font-bold text-ink">
          {weekLabel(game.week, game.game_type)}
          {primetimeBadge(game.gameday, game.gametime) ? ` - ${primetimeBadge(game.gameday, game.gametime)}` : ''}
        </span>
        <Link to={`/games/${game.game_id}`} className="ml-auto shrink-0 text-xs font-bold text-indigo-300 hover:text-indigo-200">
          Gamebook
        </Link>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4 px-7 py-6 max-[780px]:gap-2 max-[780px]:px-4">
        <HeroTeam
          team={game.away_team}
          record={game.away_record}
          score={game.away_score}
          won={winner === game.away_team}
          finished={finished}
          align="left"
        />
        <div className="text-center">
          {finished ? (
            <div className="text-[11px] font-black uppercase tracking-[0.14em] text-ink-dim">{finalLabel(game)}</div>
          ) : (
            <>
              <div className="text-2xl font-black tabular-nums text-ink max-[780px]:text-lg">VS</div>
              <div className="mt-1 text-xs font-bold uppercase tracking-[0.12em] text-ink-dim">Preview</div>
            </>
          )}
        </div>
        <HeroTeam
          team={game.home_team}
          record={game.home_record}
          score={game.home_score}
          won={winner === game.home_team}
          finished={finished}
          align="right"
        />
      </div>
      <div className="grid grid-cols-4 border-t border-surface-line max-[780px]:grid-cols-2">
        {facts.map(fact => (
          <div
            key={fact.label}
            className="min-w-0 border-r border-surface-line px-4 py-3 last:border-r-0 max-[780px]:even:border-r-0 max-[780px]:[&:nth-child(n+3)]:border-t"
          >
            <div className={MICRO}>{fact.label}</div>
            <div className="mt-1 break-words text-sm font-bold leading-snug text-ink">
              {fact.value}
            </div>
          </div>
        ))}
      </div>
      {(spread || totalValue) && (
        <div className="border-t border-surface-line px-4 py-2 text-right text-[10px] text-ink-dim">
          Lines via nflverse
        </div>
      )}
    </Card>
  )
}
