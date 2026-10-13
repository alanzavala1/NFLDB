import type { GameDetail } from '../../types'
import Card from '../../components/Card'
import { teamLogoUrl } from '../../utils/teams'

// ── Scoring summary ───────────────────────────────────────────────────────────

const SCORE_KIND: Record<string, string> = {
  TD: 'text-data-win bg-data-win/15 border-data-win/30',
  FG: 'text-ink-mid bg-surface-raise border-surface-line',
  SAF: 'text-data-loss bg-data-loss/15 border-data-loss/30',
  SCORE: 'text-ink-mid bg-surface-raise/15 border-surface-line/30',
}

const trimScoreDesc = (d: string | null) =>
  (d ?? '').replace(/^\(\d+:\d+\)\s*/, '').replace(/^\((Shotgun|No Huddle)[^)]*\)\s*/, '')

export function ScoringSummary({ game }: { game: GameDetail }) {
  const plays = game.scoring ?? []
  if (!plays.length) return null
  return (
    <Card title="Scoring Summary" className="mb-4">
      <div className="divide-y divide-surface-line/40">
        {plays.map((s, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-2">
            <div className="shrink-0 w-14 text-[11px] text-ink-dim font-mono tabular-nums">Q{s.qtr} {s.clock}</div>
            {s.team && <img src={teamLogoUrl(s.team)} className="w-5 h-5 object-contain shrink-0 opacity-80" alt="" />}
            <span className={`shrink-0 inline-block text-[10px] font-bold uppercase tracking-wider border rounded px-1.5 py-0.5 ${SCORE_KIND[s.kind] ?? SCORE_KIND.SCORE}`}>{s.kind}</span>
            <p className="flex-1 text-xs text-ink-mid leading-snug line-clamp-1 min-w-0">{trimScoreDesc(s.desc)}</p>
            <span className="shrink-0 text-sm font-bold text-white tabular-nums">
              {s.away_score}<span className="text-ink-dim">–</span>{s.home_score}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}
