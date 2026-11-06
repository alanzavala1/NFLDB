import type { GameDetail } from '../../types'
import Card from '../../components/Card'

export function QuarterScore({ game }: { game: GameDetail }) {
  const qs = game.quarter_scores ?? []
  if (!qs.length) return null
  const quarters = [1, 2, 3, 4, ...(qs.some(q => q.qtr >= 5) ? [5] : [])]
  const byQtr = Object.fromEntries(qs.map(q => [q.qtr, q]))
  const awayWon = (game.away_score ?? 0) > (game.home_score ?? 0), homeWon = (game.home_score ?? 0) > (game.away_score ?? 0)
  return <Card title="Scoring by quarter" className="mb-4"><div className="overflow-x-auto"><table className="w-full min-w-[420px] text-sm"><thead><tr className="border-t border-surface-line bg-surface-raise/40"><th className="px-4 py-2 text-left text-[10px] uppercase tracking-wider text-ink-dim">Team</th>{quarters.map(q => <th key={q} className="px-3 py-2 text-center text-[10px] uppercase tracking-wider text-ink-dim">{q <= 4 ? `Q${q}` : 'OT'}</th>)}<th className="border-l border-surface-line px-3 py-2 text-center text-[10px] uppercase tracking-wider text-ink-dim">Final</th></tr></thead><tbody>{([{ team: game.away_team, key: 'away' as const, won: awayWon, total: game.away_score }, { team: game.home_team, key: 'home' as const, won: homeWon, total: game.home_score }]).map(({ team, key, won, total }) => <tr key={team} className="border-t border-surface-line"><td className="px-4 py-3 font-bold text-ink">{team}</td>{quarters.map(q => <td key={q} className="px-3 py-3 text-center tabular-nums text-ink-mid">{byQtr[q]?.[key] ?? '—'}</td>)}<td className={`border-l border-surface-line px-3 py-3 text-center text-lg font-black tabular-nums ${won ? 'text-ink' : 'text-ink-dim'}`}>{total ?? '—'}</td></tr>)}</tbody></table></div></Card>
}
