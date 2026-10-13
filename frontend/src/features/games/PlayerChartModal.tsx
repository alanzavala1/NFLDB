import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { GameDetail, LineupPlayer } from '../../types'
import { playerChartQueryOptions } from '../../api/games'
import { QueryFailure, QueryLoading } from '../../components/QueryFeedback'
import { teamPrimaryColor } from '../../utils/teams'
import { initials, ratingClass, gameLabel, formatSnapPercent, titleCase } from './formatting'
import { ungradedReason } from './lineupPlacement'
import { STAT_LABELS, ROLE_STAT_KEYS, SECONDARY_FAMILY, fallbackRole, formatStatValue, statColor, avgDepthOfTarget } from './playerChartStats'
import { TargetMap, ZoneGrid } from './PassingMap'
import { RunMap, GapStrip } from './RushingMap'

export function PlayerChartModal({ game, player, onClose }: { game: GameDetail; player: LineupPlayer | null; onClose: () => void }) {
  const chartQuery = useQuery(playerChartQueryOptions(game.game_id, player?.player_id ?? undefined))
  const chart = chartQuery.data
  useEffect(() => {
    if (!player) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [player, onClose])
  if (!player) return null
  const role = chart?.role ?? fallbackRole(player.position)
  const title = role === 'defender' ? 'Defense' : role === 'rusher' ? 'Rushing' : role === 'receiver' ? 'Receiving' : role === 'passer' ? 'Passing' : 'Game'
  const statRows = (keys: string[]) => keys
    .map(k => [k, chart?.stats?.[k as keyof typeof chart.stats]] as const)
    .filter(([k, v]) => {
      const num = Number(v)
      if (!Number.isFinite(num)) return false
      return k.endsWith('_epa') ? num !== 0 : num > 0
    })
    .slice(0, 8)
  const stats = statRows(ROLE_STAT_KEYS[role] ?? Object.keys(chart?.stats ?? {}))
  const secondary = (SECONDARY_FAMILY[role] ?? [])
    .filter(fam => Number(chart?.stats?.[fam.gate as keyof typeof chart.stats] ?? 0) > 0)
    .map(fam => ({ title: fam.title, rows: statRows(fam.keys) }))
    .filter(fam => fam.rows.length > 0)
  const events = chart?.events ?? []
  const showZones = role === 'passer' || role === 'receiver'
  const showRush = role === 'rusher'
  const adot = role === 'passer' ? avgDepthOfTarget(events) : null
  const footer = showRush
    ? 'From nflverse play-by-play: lane = recorded run gap and direction, height = yards gained on the carry. Exact counts, no interpolation.'
    : showZones
      ? "From nflverse play-by-play: lane = recorded pass direction (left/middle/right), band = air yards. Cells show completions/attempts and yards — exact counts, drawn at the data's real resolution."
      : 'From nflverse play-by-play and official game stats.'
  const ungraded = ungradedReason(player)
  return <div className="lineup-overlay" onClick={onClose}><div className="lineup-modal" role="dialog" aria-modal="true" aria-label={`${player.player_name} game chart`} onClick={e => e.stopPropagation()}>
    <div className="modal-head"><div className="modal-avatar" style={{ background: teamPrimaryColor(player.team) }}>{player.headshot_url ? <img src={player.headshot_url} alt="" /> : initials(player.player_name)}</div><div><div className="modal-name">{player.player_name}</div><div className="modal-sub">{player.position} · {player.team} · {gameLabel(game)} · {formatSnapPercent(player.snap_pct)} of snaps</div>{ungraded && <div className="modal-sub ungraded">Not graded — {ungraded}</div>}</div>{player.rating != null && <span className={`rbadge ${ratingClass(player.rating)} modal-rating`}>{player.rating.toFixed(1)}{player.rating >= 8.5 ? ' ✦' : ''}</span>}{ungraded && <span className="rbadge b-none modal-rating" title={`Not graded — ${ungraded}`}>–</span>}<button className="modal-close" aria-label="Close player chart" onClick={onClose}>✕</button></div>
    <QueryFailure resource="player chart" error={chartQuery.error} hasData={chart !== undefined} onRetry={() => void chartQuery.refetch()} />
    {player.player_id && chartQuery.isPending && <QueryLoading>Loading player chart…</QueryLoading>}
    {!player.player_id && <p className="micro">No chart is available for this player.</p>}
    {chart && events.length === 0 && stats.length === 0 && secondary.length === 0 && <p className="micro">No chart data is available for this player in this game.</p>}
    {chart && <>
    <div className={`modal-grid ${role === 'defender' ? 'single' : ''}`}><div><div className="micro popup-title">{title}</div>{stats.map(([k, v]) => <div className="rrow" key={k}><span>{STAT_LABELS[k] ?? titleCase(k.replaceAll('_', ' '))}</span><b style={{ marginLeft: 'auto', color: statColor(k, v) }}>{formatStatValue(k, v)}</b></div>)}{adot != null && <div className="rrow"><span>Average depth of target</span><b style={{ marginLeft: 'auto' }}>{adot.toFixed(1)}</b></div>}{secondary.map(fam => <div key={fam.title}><div className="micro popup-title">{fam.title}</div>{fam.rows.map(([k, v]) => <div className="rrow" key={k}><span>{STAT_LABELS[k] ?? titleCase(k.replaceAll('_', ' '))}</span><b style={{ marginLeft: 'auto', color: statColor(k, v) }}>{formatStatValue(k, v)}</b></div>)}</div>)}</div>{showZones && <div className="target-map"><TargetMap events={events} role={role} /><ZoneGrid events={events} /></div>}{showRush && <div className="target-map"><RunMap events={events} /><GapStrip events={events} /></div>}</div>
    <div className="modal-foot">{footer}</div>
    </>}
  </div></div>
}
