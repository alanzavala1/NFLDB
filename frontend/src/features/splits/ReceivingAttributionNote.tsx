import { Link } from 'react-router-dom'
import { RECEIVING_YARDAGE_NOTE_ID, type ReceivingYardageDifference } from './receivingAttribution'

export type NamedYardageDifference = ReceivingYardageDifference & { playerId: string; playerName: string }

export function ReceivingAttributionNote({ differences }: { differences: NamedYardageDifference[] }) {
  if (!differences.length) return null
  return <aside id={RECEIVING_YARDAGE_NOTE_ID} aria-label="Receiving yardage sources" className="mb-4 rounded-lg border border-surface-line bg-surface-card p-4 text-sm text-ink-mid">
    <p className="font-semibold text-ink">Receiving yardage differs between sources †</p>
    <p className="mt-1">Season, Opponent and game rows use weekly game-log totals. Situational rows use play-by-play. Yardage-based columns marked † refer to the differences below; the recorded values are retained.</p>
    <div className="mt-3 space-y-4">
      {differences.map(item => <div key={`${item.playerId}:${item.season}`}>
        <p className="font-semibold text-ink">{item.playerName} · {item.season}</p>
        <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
          {[
            ['Weekly total', item.weeklyYards.toLocaleString()],
            ['Play-by-play total (Down)', item.splitYards.toLocaleString()],
            ['Difference', `${item.difference > 0 ? '+' : ''}${item.difference.toLocaleString()}`],
          ].map(([label, value]) => <div key={label} className="rounded bg-surface-raise/50 p-2">
            <dt className="text-ink-dim">{label}</dt><dd className="mt-1 text-base font-bold tabular-nums text-ink">{value} <span className="text-xs font-normal">yds</span></dd>
          </div>)}
        </dl>
        {item.reviewedPlays ? <>
          <p className="mt-2">Two reviewed lateral plays account for the 41 additional yards. Gibbs received the ball after another player’s catch, and those yards are omitted from this play-by-play breakdown.</p>
          <details className="mt-2">
            <summary className="w-fit cursor-pointer py-1 text-indigo-300 focus-visible:outline-2 focus-visible:outline-indigo-400">Reviewed lateral plays</summary>
            <ul className="mt-1 space-y-1">
              {item.reviewedPlays.map(play => <li key={play.gameId}><Link className="text-indigo-300 underline underline-offset-2" to={`/games/${play.gameId}`}>{play.label}</Link> · {play.yards} receiving yards</li>)}
            </ul>
          </details>
        </> : <p className="mt-2">The totals differ, but the cause has not been confirmed for these values. This comparison does not adjust or redistribute any yards.</p>}
      </div>)}
    </div>
  </aside>
}
