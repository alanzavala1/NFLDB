import type { LineupPlayer, LineupTeam } from '../../types'
import { teamPrimaryColor } from '../../utils/teams'
import { initials, lastName, ratingClass, formatSnapPercent } from './formatting'
import { ungradedReason, type Placed } from './lineupPlacement'

export function PlayerNode({ player, mirror, onSelect }: { player: Placed; mirror: boolean; onSelect: (p: LineupPlayer) => void }) {
  const top = mirror ? 100 - player.y : player.y
  const r = player.rating
  const star = r != null && r >= 8.5
  const reason = ungradedReason(player)
  const ungradedTitle = reason ? `${player.player_name} — not graded (${reason})` : player.player_name
  return (
    <button type="button" className={`player ${player.ol ? 'ol' : ''}`} style={{ left: `${player.x}%`, top: `${top}%` }} title={ungradedTitle} onClick={() => onSelect(player)}>
      <span className="pav" style={{ background: teamPrimaryColor(player.team) }}>
        {player.headshot_url ? <img src={player.headshot_url} alt="" /> : initials(player.player_name)}
        {player.scored_td && <span className="td-pip">◒</span>}
        {r != null && !player.ol && <span className={`badge ${ratingClass(r)}`}>{r.toFixed(1)}{star ? ' ✦' : ''}</span>}
        {/* Rendering nothing made "not enough to grade" look identical to
            a data error. The dash is the honest answer. */}
        {reason && <span className="badge b-none" aria-label="not graded">–</span>}
      </span>
      <span className="pname"><span className="no">{player.jersey_number ?? ''}</span>{lastName(player.player_name)}</span>
    </button>
  )
}

export function RotationList({ team }: { team: LineupTeam }) {
  return <div className="rot-col">{team.rotation.slice(0, 5).map(p => {
    const reason = ungradedReason(p)
    return (
      <div className="rrow" key={`${team.team}-${p.player_id ?? p.pfr_player_id}`}>
        <span className="chip" style={{ background: teamPrimaryColor(team.team) }}>{initials(p.player_name)}</span>
        <span className="who"><b>{p.player_name}</b><span>{p.position ?? '—'} · {formatSnapPercent(p.snap_pct)} snaps</span></span>
        {p.rating != null && <span className={`rbadge ${ratingClass(p.rating)}`}>{p.rating.toFixed(1)}</span>}
        {/* The rail sorts rated players first, so a blank row here reads as a
            hole in the data rather than the bottom of the list. */}
        {reason && <span className="rbadge b-none" title={`Not graded — ${reason}`} aria-label="not graded">–</span>}
      </div>
    )
  })}</div>
}
