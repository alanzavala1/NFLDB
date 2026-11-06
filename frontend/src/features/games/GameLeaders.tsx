import { Link } from 'react-router-dom'
import { hasReceivingActivity } from '../../utils/receiving'
import type { GameDetail, GamePlayerStats } from '../../types'
import type { GameOrigin } from '../../types/navigation'
import Card from '../../components/Card'
import { formatStat } from './formatting'
import { playerLink } from './navigation'

type Leader = { player: GamePlayerStats; stat: string; sub: string } | null

function LeaderSide({ leader, align, origin }: { leader: Leader; origin: GameOrigin; align: 'left' | 'right' }) {
  if (!leader) return <div className="flex-1" />
  const { to, state } = playerLink(leader.player.player_id, origin)
  const rev = align === 'right'
  return (
    <div className={`flex-1 flex items-center gap-3 min-w-0 ${rev ? 'flex-row-reverse' : ''}`}>
      {leader.player.headshot_url
        ? <img src={leader.player.headshot_url} alt="" className="w-12 h-12 rounded-full object-cover object-top shrink-0 bg-surface-raise" />
        : <div className="w-12 h-12 rounded-full bg-surface-raise shrink-0" />
      }
      <div className={`min-w-0 ${rev ? 'text-right' : ''}`}>
        <div className="text-xl font-black text-white tabular-nums leading-none">{leader.stat}</div>
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight block truncate mt-0.5">
          {leader.player.player_name}
        </Link>
        <div className="text-[11px] text-ink-dim mt-0.5">{leader.sub}</div>
      </div>
    </div>
  )
}

export function GameLeaders({ game, origin }: { game: GameDetail; origin: GameOrigin }) {
  function top(
    players: GamePlayerStats[],
    filter: (p: GamePlayerStats) => boolean,
    sortVal: (p: GamePlayerStats) => number,
    statFn: (p: GamePlayerStats) => string,
    subFn: (p: GamePlayerStats) => string,
  ): Leader {
    const p = [...players].filter(filter).sort((a, b) => sortVal(b) - sortVal(a))[0]
    return p ? { player: p, stat: statFn(p), sub: subFn(p) } : null
  }

  const categories = [
    {
      label: 'Passing Yds',
      away: top(game.away, p => p.attempts > 0, p => p.pass_yards,
        p => formatStat(p.pass_yards),
        p => `${p.completions}/${p.attempts}, ${p.pass_tds} TD${p.interceptions_thrown ? `, ${p.interceptions_thrown} INT` : ''}`),
      home: top(game.home, p => p.attempts > 0, p => p.pass_yards,
        p => formatStat(p.pass_yards),
        p => `${p.completions}/${p.attempts}, ${p.pass_tds} TD${p.interceptions_thrown ? `, ${p.interceptions_thrown} INT` : ''}`),
    },
    {
      label: 'Rushing Yds',
      away: top(game.away, p => p.carries > 0, p => p.rush_yards,
        p => formatStat(p.rush_yards),
        p => `${p.carries} CAR${p.rush_tds ? `, ${p.rush_tds} TD` : ''}`),
      home: top(game.home, p => p.carries > 0, p => p.rush_yards,
        p => formatStat(p.rush_yards),
        p => `${p.carries} CAR${p.rush_tds ? `, ${p.rush_tds} TD` : ''}`),
    },
    {
      label: 'Receiving Yds',
      away: top(game.away, p => hasReceivingActivity(p), p => p.rec_yards,
        p => formatStat(p.rec_yards),
        p => `${p.receptions}/${p.targets ?? '—'} TGT${p.rec_tds ? `, ${p.rec_tds} TD` : ''}`),
      home: top(game.home, p => hasReceivingActivity(p), p => p.rec_yards,
        p => formatStat(p.rec_yards),
        p => `${p.receptions}/${p.targets ?? '—'} TGT${p.rec_tds ? `, ${p.rec_tds} TD` : ''}`),
    },
    {
      label: 'Tackles',
      away: top(game.away, p => p.solo_tackles + p.assist_tackles > 0,
        p => p.solo_tackles + p.assist_tackles,
        p => formatStat(p.solo_tackles + p.assist_tackles),
        p => `${p.solo_tackles} SOLO${p.sacks ? `, ${formatStat(p.sacks)} SCK` : ''}`),
      home: top(game.home, p => p.solo_tackles + p.assist_tackles > 0,
        p => p.solo_tackles + p.assist_tackles,
        p => formatStat(p.solo_tackles + p.assist_tackles),
        p => `${p.solo_tackles} SOLO${p.sacks ? `, ${formatStat(p.sacks)} SCK` : ''}`),
    },
  ]

  if (categories.every(c => !c.away && !c.home)) return null

  return (
    <Card title="Game Leaders" className="mb-4">
      <div className="divide-y divide-surface-line/40">
        {categories.map(({ label, away, home }) => (away || home) && (
          <div key={label} className="flex items-center gap-3 px-4 py-3">
            <LeaderSide origin={origin} leader={away} align="left" />
            <div className="shrink-0 w-32 text-center">
              <span className="text-[10px] font-semibold text-ink-dim uppercase tracking-wider">{label}</span>
            </div>
            <LeaderSide origin={origin} leader={home} align="right" />
          </div>
        ))}
      </div>
    </Card>
  )
}
