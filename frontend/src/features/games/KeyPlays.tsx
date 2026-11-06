import type { GameDetail } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl } from '../../utils/teams'
import { formatGameClock } from './formatting'
import { detectKeyPlays, type KeyPlayKind } from './playSelection'

const KIND_META: Record<KeyPlayKind, { label: string; color: string; bg: string }> = {
  int: { label: 'INT', color: 'text-data-loss',    bg: 'bg-data-loss/15 border-data-loss/30' },
  fum: { label: 'FUM', color: 'text-data-loss',    bg: 'bg-data-loss/15 border-data-loss/30' },
  big: { label: 'KEY', color: 'text-ink-mid',     bg: 'bg-surface-raise/15 border-surface-line/30' },
}

export function KeyPlays({ game }: { game: GameDetail }) {
  const plays = detectKeyPlays(game.win_prob ?? [])
  if (!plays.length) return null
  const homeTeam = game.home_team
  return (
    <Card title="Key Plays" action={<span className="text-[10px] text-ink-dim uppercase tracking-wider">{plays.length} events</span>} className="mb-4">
      <div className="divide-y divide-surface-line/40 max-h-96 overflow-y-auto">
        {plays.map((p, i) => {
          const isHome = p.team === homeTeam
          // For scoring plays, swing is in offense's favor; for turnovers, against
          const offSwing = isHome ? p.wpSwing : -p.wpSwing
          const swingStr = Math.abs(offSwing) >= 1 ? `${offSwing >= 0 ? '+' : ''}${offSwing.toFixed(0)}%` : null
          const meta = KIND_META[p.kind]
          return (
            <div key={i} className={`flex items-center gap-3 px-4 py-2.5 border-l-2 ${isHome ? 'border-l-indigo-500/60' : 'border-l-rose-500/60'}`}>
              <div className="shrink-0 w-12 text-[11px] text-ink-dim font-mono tabular-nums">{formatGameClock(p.rem)}</div>
              <img src={teamLogoUrl(p.team ?? '')} className="w-5 h-5 object-contain shrink-0 opacity-70" alt="" />
              <span className={`shrink-0 inline-block text-[10px] font-bold uppercase tracking-wider border rounded px-1.5 py-0.5 ${meta.color} ${meta.bg}`}>
                {meta.label}
              </span>
              <p className="flex-1 text-xs text-ink-mid leading-snug line-clamp-2 min-w-0">{p.desc}</p>
              {swingStr && (
                <span className={`shrink-0 text-[11px] tabular-nums font-semibold ${offSwing >= 0 ? 'text-data-win' : 'text-data-loss'}`}>
                  {swingStr} WP
                </span>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}
