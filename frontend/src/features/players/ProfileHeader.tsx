import { Link } from 'react-router-dom'
import type { PlayerProfile, DepthChartEntry, InjuryStatus } from '../../types'
import { CURRENT_NFL_SEASON } from '../../utils/seasons'
import Card from '../../components/Card'
import { teamLogoUrl, teamName } from '../../utils/teams'

function injuryToneClasses(status: string | null | undefined): string {
  switch (status) {
    case 'Out':           return 'bg-data-loss/60 border-data-loss text-data-loss'
    case 'Doubtful':      return 'bg-data-loss/60 border-data-loss text-data-loss'
    case 'Questionable':  return 'bg-surface-raise/60 border-data-loss/40 text-data-loss'
    case 'Probable':      return 'bg-data-win/60 border-data-win text-data-win'
    default:              return 'bg-surface-card border-surface-line text-ink-mid'
  }
}

function StatusStrip({ depth, injury }: {
  depth: DepthChartEntry | null
  injury: InjuryStatus | null
}) {
  // StatusStrip is intended as "what's going on with this player RIGHT NOW".
  // For retired players, the most-recent depth and injury entries are
  // years old and showing them as "Starting QB" / "Out" is misleading. Drop
  // any data not from the current NFL season — if nothing survives, the
  // strip doesn't render at all (correct behavior for retired players).
  const depthCurrent  = depth  && depth.season  === CURRENT_NFL_SEASON ? depth  : null
  const injuryCurrent = injury && injury.season === CURRENT_NFL_SEASON ? injury : null

  if (!depthCurrent && !injuryCurrent) return null

  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {depthCurrent && depthCurrent.depth_position && depthCurrent.depth_team === '1' && (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-bold uppercase tracking-wider bg-data-win/50 border border-data-win text-data-win">
          <span className="w-1.5 h-1.5 rounded-full bg-data-win" />
          Starting {depthCurrent.depth_position}
        </span>
      )}
      {depthCurrent && depthCurrent.depth_position && depthCurrent.depth_team !== '1' && (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-bold uppercase tracking-wider bg-surface-card border border-surface-line text-ink-mid">
          {depthCurrent.depth_position} · {depthCurrent.depth_team === '2' ? 'Backup' : `Depth ${depthCurrent.depth_team}`}
        </span>
      )}
      {injuryCurrent && injuryCurrent.report_status && (
        <span
          title={[injuryCurrent.report_primary_injury, injuryCurrent.report_secondary_injury].filter(Boolean).join(' / ')}
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-bold uppercase tracking-wider border ${injuryToneClasses(injuryCurrent.report_status)}`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-current" />
          {injuryCurrent.report_status}
          {injuryCurrent.report_primary_injury && (
            <span className="font-normal normal-case opacity-80">· {injuryCurrent.report_primary_injury}</span>
          )}
        </span>
      )}
    </div>
  )
}

export default function ProfileHeader({ player, recentTeams }: { player: PlayerProfile; recentTeams: string[] }) {
  return (
    <Card title={player.player_name} className="mb-8"><div className="flex items-start gap-6 border-t border-surface-line p-5 flex-wrap">
      {player.headshot_url
        ? <img src={player.headshot_url} alt={player.player_name} className="w-24 h-24 rounded-full object-cover bg-surface-raise shrink-0 object-top ring-2 ring-surface-line" />
        : <div className="w-24 h-24 rounded-full bg-surface-raise shrink-0" />
      }
      <div className="flex-1 min-w-0">
        {(player.position || player.jersey_number != null) && (
          <div className="text-[10px] font-bold text-ink-dim uppercase tracking-widest flex items-center gap-2">
            {player.position && <span>{player.position}</span>}
            {player.jersey_number != null && (
              <>
                {player.position && <span className="text-ink-dim">·</span>}
                <span className="text-ink-dim">#{player.jersey_number}</span>
              </>
            )}
          </div>
        )}

        {/* Team chips — prominent and clearly clickable */}
        {recentTeams.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {recentTeams.map(t => (
              <Link
                key={t}
                to={`/teams/${t}`}
                className="inline-flex items-center gap-2 px-3 py-1.5 bg-surface-card hover:bg-surface-raise border border-surface-line hover:border-indigo-500 rounded-lg transition-colors group"
              >
                <img src={teamLogoUrl(t)} className="w-5 h-5 object-contain" alt="" />
                <span className="text-sm font-bold text-ink">{t}</span>
                <span className="text-xs text-ink-mid group-hover:text-ink transition-colors">{teamName(t)}</span>
                <span className="text-indigo-400 text-xs">→</span>
              </Link>
            ))}
          </div>
        )}

        {/* Status strip: starting role + injury report (current or historical) */}
        <StatusStrip
          depth={player.depth ?? null}
          injury={player.current_injury ?? null}
        />

        {/* Bio */}
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-3 text-xs text-ink-dim">
          {player.height && <span>{player.height}</span>}
          {player.weight && <span>{player.weight} lbs</span>}
          {player.age && <span>Age {player.age}</span>}
          {player.college && <span>{player.college}</span>}
          {player.entry_year && <span>Since {player.entry_year}</span>}
        </div>
      </div>
    </div></Card>
  )
}
