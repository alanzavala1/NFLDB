import type { TeamLeader } from '../../types'
import { Link } from 'react-router-dom'
import { hasReceivingActivity } from '../../utils/receiving'
import { sv, pct, avg } from './formatting'

const LEADERS_PREVIEW = 3

interface LeaderRowProps {
  player: TeamLeader
  primary: { value: string; label: string }
  secondary: string
}

function LeaderRow({ player, primary, secondary }: LeaderRowProps) {
  return (
    <Link to={`/players/${player.player_id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-raise/50 transition-colors group">
      {player.headshot_url
        ? <img src={player.headshot_url} alt={player.player_name} className="w-8 h-8 rounded-full object-cover shrink-0 opacity-80 group-hover:opacity-100 transition-opacity" />
        : <div className="w-8 h-8 rounded-full bg-surface-raise shrink-0 flex items-center justify-center text-xs text-ink-dim">#</div>
      }
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-ink truncate group-hover:text-ink transition-colors">{player.player_name}</div>
        <div className="text-xs text-ink-dim">{player.position ?? '—'} · {player.games_played}G</div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-base font-bold text-ink tabular-nums">{primary.value} <span className="text-xs font-normal text-ink-dim">{primary.label}</span></div>
        <div className="text-xs text-ink-dim tabular-nums">{secondary}</div>
      </div>
    </Link>
  )
}

function LeaderSection({ title, rows }: { title: string; rows: React.ReactNode[] }) {
  if (!rows.length) return null
  return (
    <div>
      <div className="px-4 py-1.5 bg-surface-raise/40 border-t border-surface-line">
        <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">{title}</span>
      </div>
      {rows}
    </div>
  )
}

export default function LeadersPanel({ leaders, onViewFull }: { leaders: TeamLeader[]; onViewFull: () => void }) {
  const passers   = leaders.filter(p => p.attempts >= 50).sort((a, b) => b.pass_yards - a.pass_yards).slice(0, LEADERS_PREVIEW)
  const rushers   = leaders.filter(p => p.carries >= 20).sort((a, b) => b.rush_yards - a.rush_yards).slice(0, LEADERS_PREVIEW)
  const receivers = leaders.filter(p => hasReceivingActivity(p, 10)).sort((a, b) => b.rec_yards - a.rec_yards).slice(0, LEADERS_PREVIEW)
  const defenders = leaders
    .filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
    .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles))
    .slice(0, LEADERS_PREVIEW)

  return (
    <div>
      <LeaderSection title="Passing" rows={passers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.pass_yards), label: 'YDS' }}
          secondary={`${sv(p.pass_tds)} TD · ${sv(p.interceptions_thrown)} INT · ${pct(p.completions, p.attempts)}`}
        />
      ))} />
      <LeaderSection title="Rushing" rows={rushers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.rush_yards), label: 'YDS' }}
          secondary={`${sv(p.carries)} CAR · ${avg(p.rush_yards, p.carries)} YPC · ${sv(p.rush_tds)} TD`}
        />
      ))} />
      <LeaderSection title="Receiving" rows={receivers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.rec_yards), label: 'YDS' }}
          secondary={`${sv(p.receptions)}/${sv(p.targets)} REC · ${avg(p.rec_yards, p.receptions)} YPR · ${sv(p.rec_tds)} TD`}
        />
      ))} />
      <LeaderSection title="Defense" rows={defenders.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.solo_tackles + p.assist_tackles), label: 'TKL' }}
          secondary={`${sv(p.sacks)} SCK · ${sv(p.def_interceptions)} INT · ${sv(p.pass_breakups)} PBU`}
        />
      ))} />
      <button
        onClick={onViewFull}
        className="w-full text-xs text-indigo-400 hover:text-indigo-300 py-2.5 border-t border-surface-line transition-colors font-medium"
      >
        Full season stats →
      </button>
    </div>
  )
}
