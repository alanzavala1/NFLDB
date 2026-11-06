import { Link } from 'react-router-dom'
import type { WpaLeader } from '../../types'
import { teamLogoUrl } from '../../utils/teams'

export function WpaTable({ players, contextLabel }: { players: WpaLeader[]; contextLabel: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-line/50">
            <th colSpan={4} />
            <th colSpan={1} className="py-1 text-center text-[10px] font-semibold text-ink-dim/60 uppercase tracking-widest bg-surface-raise/20 border-l border-surface-line/40">WPA</th>
            <th colSpan={2} className="py-1 text-center text-[10px] font-semibold text-ink-dim uppercase tracking-widest border-l border-surface-line/40">Context</th>
          </tr>
          <tr className="border-b border-surface-line">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-ink-dim text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-ink-dim text-left">Player</th>
            <th className="py-2.5 px-2 text-xs font-semibold text-ink-dim text-left">Pos</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-ink-dim text-left">Team</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-ink-dim/50 text-right border-l border-surface-line/40 bg-surface-raise/10">WPA</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-ink-dim text-right border-l border-surface-line/40">G</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-ink-dim text-right">{contextLabel}</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p, i) => {
            const wpaStr = `${p.wpa >= 0 ? '+' : ''}${p.wpa.toFixed(3)}`
            const isPos = p.wpa >= 0
            const ctx = p.attempts ?? p.carries ?? p.receptions ?? null
            return (
              <tr key={p.player_id} className="border-t border-surface-line/50 hover:bg-surface-raise/30 transition-colors">
                <td className="py-2.5 pl-4 pr-2 text-right">
                  <span className={`text-sm tabular-nums ${i === 0 ? 'text-gold font-black' : i === 1 ? 'text-ink-mid font-bold' : i === 2 ? 'text-ink-mid font-bold' : 'text-ink-dim font-medium'}`}>{i + 1}</span>
                </td>
                <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    {p.headshot_url
                      ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-surface-raise" alt="" />
                      : <div className="w-7 h-7 rounded-full bg-surface-raise shrink-0" />
                    }
                    <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{p.player_name}</Link>
                  </div>
                </td>
                <td className="py-2.5 px-2 whitespace-nowrap">
                  <span className="text-xs text-ink-dim font-medium">{p.position ?? '—'}</span>
                </td>
                <td className="py-2.5 px-3 whitespace-nowrap">
                  {p.team
                    ? <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
                        <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                        <span className="text-xs text-ink-mid group-hover:text-ink transition-colors font-medium">{p.team}</span>
                      </Link>
                    : <span className="text-ink-dim text-xs">—</span>
                  }
                </td>
                <td className={`py-2.5 px-3 text-right tabular-nums font-bold text-sm border-l border-surface-line/30 bg-surface-raise/10 ${isPos ? 'text-data-win' : 'text-data-loss'}`}>
                  {wpaStr}
                </td>
                <td className="py-2.5 px-3 text-right tabular-nums text-sm text-ink-dim border-l border-surface-line/30">{p.games_played}</td>
                <td className="py-2.5 px-3 text-right tabular-nums text-sm text-ink-dim">{ctx ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
