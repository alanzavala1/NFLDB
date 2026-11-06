import { Link } from 'react-router-dom'
import type { LeagueLeader } from '../../types'
import { teamLogoUrl } from '../../utils/teams'
import type { PrimaryStat } from './primaryStats'

const PODIUM_TONES: Record<1 | 2 | 3, { ring: string; text: string; chipBg: string; chipText: string; medal: string }> = {
  1: { ring: 'ring-gold/60', text: 'text-gold', chipBg: 'bg-gold/15 border-gold/40', chipText: 'text-gold', medal: '1st' },
  2: { ring: 'ring-surface-line/50',   text: 'text-ink',   chipBg: 'bg-surface-raise border-surface-line/40',     chipText: 'text-ink',  medal: '2nd' },
  3: { ring: 'ring-surface-line',  text: 'text-ink-mid',  chipBg: 'bg-surface-raise border-surface-line',   chipText: 'text-ink-mid', medal: '3rd' },
}

function PodiumCard({ player, rank, primary }: { player: LeagueLeader; rank: 1 | 2 | 3; primary: PrimaryStat }) {
  const tone = PODIUM_TONES[rank]
  const isGold = rank === 1
  return (
    <Link
      to={`/players/${player.player_id}`}
      className={`block relative bg-surface-card border border-surface-line rounded-xl px-4 hover:border-surface-line transition-colors ${isGold ? 'py-5' : 'py-4'}`}
    >
      <div className={`absolute -top-2.5 left-3 px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-widest border ${tone.chipBg} ${tone.chipText}`}>
        {tone.medal}
      </div>
      <div className="flex items-center gap-3 mt-1">
        {player.headshot_url
          ? <img src={player.headshot_url} className={`rounded-full object-cover object-top shrink-0 bg-surface-raise ring-2 ${tone.ring} ${isGold ? 'w-16 h-16' : 'w-14 h-14'}`} alt="" />
          : <div className={`rounded-full bg-surface-raise shrink-0 ${isGold ? 'w-16 h-16' : 'w-14 h-14'}`} />
        }
        <div className="flex-1 min-w-0">
          <div className={`font-bold text-ink truncate leading-tight ${isGold ? 'text-base' : 'text-sm'}`}>{player.player_name}</div>
          <div className="text-[11px] text-ink-dim flex items-center gap-1.5 mt-0.5">
            {player.team && <img src={teamLogoUrl(player.team)} className="w-3.5 h-3.5 object-contain opacity-80" alt="" />}
            <span>{player.team ?? '—'}</span>
            {player.position && <><span className="text-ink-dim">·</span><span>{player.position}</span></>}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className={`font-black text-ink tabular-nums leading-none ${isGold ? 'text-3xl' : 'text-2xl'}`}>
          {primary.display(player)}
        </span>
        <span className={`text-[10px] font-bold uppercase tracking-widest ${tone.text}`}>{primary.label}</span>
      </div>
      <div className="text-[11px] text-ink-dim mt-1 truncate">{primary.secondary(player)}</div>
    </Link>
  )
}

export function Podium({ players, primary }: { players: LeagueLeader[]; primary: PrimaryStat }) {
  const sorted = [...players].sort((a, b) => primary.value(b) - primary.value(a))
  const top3 = sorted.slice(0, 3)
  if (top3.length < 3) return null
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
      <div className="order-2 sm:order-1"><PodiumCard player={top3[1]} rank={2} primary={primary} /></div>
      <div className="order-1 sm:order-2"><PodiumCard player={top3[0]} rank={1} primary={primary} /></div>
      <div className="order-3"><PodiumCard player={top3[2]} rank={3} primary={primary} /></div>
    </div>
  )
}

export function RankBadge({ rank }: { rank: number }) {
  const cls = rank === 1 ? 'text-gold font-black' : rank === 2 ? 'text-ink-mid font-bold' : rank === 3 ? 'text-ink-mid font-bold' : 'text-ink-dim font-medium'
  return <span className={`text-sm tabular-nums ${cls}`}>{rank}</span>
}
