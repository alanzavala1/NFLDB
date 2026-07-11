import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { GameDetail, GameLineup, LineupPlayer, LineupScoringEvent, LineupTeam, PlayerChart, WeekGroup } from '../api'
import { teamName } from '../utils/teams'

type Unit = 'offense' | 'defense'
type Placed = LineupPlayer & { x: number; y: number; ol?: boolean }

const TEAM_COLORS: Record<string, string> = {
  SEA: '#69be28', NE: '#c8102e', KC: '#e31837', PHI: '#004c54', LA: '#003594', DEN: '#fb4f14',
  BUF: '#00338d', DAL: '#869397', PIT: '#ffb612', LV: '#a5acaf', MIN: '#4f2683', BAL: '#241773',
  MIA: '#008e97', CHI: '#c83803', HOU: '#03202f', SF: '#aa0000', GB: '#203731', CAR: '#0085ca',
}

const OFF_COORDS = {
  wr: [[8, 57], [22, 59], [92, 57]],
  te: [[83, 60.5]],
  ol: [[30, 62.5], [40, 66], [50, 62.5], [60, 66], [70, 62.5]],
  qb: [[50, 75]],
  rb: [[50, 85], [42, 84]],
}
const DEF_COORDS = {
  dl: [[30, 56], [43, 56], [57, 56], [70, 56]],
  cb: [[8, 59], [92, 59], [19, 64]],
  lb: [[40, 68], [60, 68], [50, 64]],
  s: [[35, 80], [65, 80]],
}

function initials(name: string) {
  const parts = name.replace(/[^a-zA-Z ]/g, '').split(/\s+/).filter(Boolean)
  return (parts.length > 1 ? `${parts[0][0]}${parts.at(-1)?.[0]}` : name.slice(0, 2)).toUpperCase()
}

function lastName(name: string | null | undefined) {
  if (!name) return ''
  const parts = name.split(' ').filter(Boolean)
  return parts.at(-1) ?? name
}

function ratingClass(r: number | null | undefined) {
  if (r == null) return ''
  if (r < 5) return 'b-bad'
  if (r < 7) return 'b-mid'
  return 'b-good'
}

function pct(v: number | null | undefined) {
  return v == null ? '—' : `${Math.round(v * 100)}%`
}

function isOL(p: LineupPlayer) {
  return ['OL', 'G', 'T', 'C', 'LT', 'LG', 'RG', 'RT'].includes((p.position ?? '').toUpperCase())
}

function posKey(p: LineupPlayer) {
  const pos = (p.position ?? '').toUpperCase()
  if (['WR'].includes(pos)) return 'wr'
  if (['TE'].includes(pos)) return 'te'
  if (['QB'].includes(pos)) return 'qb'
  if (['RB', 'FB', 'HB'].includes(pos)) return 'rb'
  if (['DT', 'DE', 'DL', 'NT', 'EDGE'].includes(pos)) return 'dl'
  if (['CB', 'DB', 'NB'].includes(pos)) return 'cb'
  if (['LB', 'ILB', 'OLB', 'MLB'].includes(pos)) return 'lb'
  if (['FS', 'SS', 'S'].includes(pos)) return 's'
  if (isOL(p)) return 'ol'
  return 'lb'
}

function placePlayers(players: LineupPlayer[], unit: Unit): Placed[] {
  const buckets = new Map<string, number>()
  const ordered = [...players].sort((a, b) => {
    const order = unit === 'offense'
      ? ['wr', 'te', 'ol', 'qb', 'rb']
      : ['dl', 'cb', 'lb', 's']
    return order.indexOf(posKey(a)) - order.indexOf(posKey(b))
  })
  return ordered.map((p) => {
    const key = unit === 'offense' ? posKey(p) : posKey(p)
    const idx = buckets.get(key) ?? 0
    buckets.set(key, idx + 1)
    const coords = unit === 'offense'
      ? (OFF_COORDS[key as keyof typeof OFF_COORDS] ?? [[50, 68]])
      : (DEF_COORDS[key as keyof typeof DEF_COORDS] ?? [[50, 68]])
    const [x, y] = coords[Math.min(idx, coords.length - 1)]
    return { ...p, x, y, ol: key === 'ol' }
  })
}

function FieldSvg({ awayTeam, homeTeam }: { awayTeam: string; homeTeam: string }) {
  return (
    <svg className="turf" viewBox="0 0 500 860" aria-hidden="true">
      <rect x="0" y="0" width="500" height="860" fill="#122a1d" />
      <rect x="0" y="0" width="500" height="860" fill="url(#vign-lineup)" />
      <defs>
        <radialGradient id="vign-lineup" cx="50%" cy="50%" r="75%"><stop offset="0%" stopColor="#16311f" /><stop offset="100%" stopColor="#0f2318" /></radialGradient>
        <pattern id="ezstripe-lineup" width="14" height="14" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><rect width="14" height="14" fill="none" /><rect width="7" height="14" fill="rgba(255,255,255,.045)" /></pattern>
      </defs>
      <g fill="rgba(255,255,255,.022)"><rect x="0" y="140" width="500" height="72" /><rect x="0" y="284" width="500" height="72" /><rect x="0" y="428" width="500" height="72" /><rect x="0" y="572" width="500" height="72" /></g>
      <rect x="0" y="0" width="500" height="70" fill={TEAM_COLORS[awayTeam] ?? '#818cf8'} opacity=".16" /><rect x="0" y="0" width="500" height="70" fill="url(#ezstripe-lineup)" />
      <rect x="0" y="790" width="500" height="70" fill={TEAM_COLORS[homeTeam] ?? '#818cf8'} opacity=".14" /><rect x="0" y="790" width="500" height="70" fill="url(#ezstripe-lineup)" />
      <text x="250" y="45" textAnchor="middle" fontSize="26" fontWeight="900" letterSpacing="14" fill="rgba(255,255,255,.28)">{awayTeam}</text>
      <text x="250" y="835" textAnchor="middle" fontSize="26" fontWeight="900" letterSpacing="14" fill="rgba(255,255,255,.26)">{homeTeam}</text>
      <g stroke="rgba(255,255,255,.30)" strokeWidth="2.5"><line x1="0" y1="70" x2="500" y2="70" /><line x1="0" y1="790" x2="500" y2="790" /></g>
      <g stroke="rgba(255,255,255,.13)" strokeWidth="1.4">{[142, 214, 286, 358, 502, 574, 646, 718].map(y => <line key={y} x1="0" y1={y} x2="500" y2={y} />)}</g>
      <line x1="0" y1="430" x2="500" y2="430" stroke="rgba(255,255,255,.28)" strokeWidth="2.2" />
      <g stroke="rgba(255,255,255,.10)" strokeWidth="1.2">
        {Array.from({ length: 41 }, (_, i) => 78 + i * 17).map(y => <g key={y}><line x1="190" y1={y} x2="210" y2={y} /><line x1="290" y1={y} x2="310" y2={y} /></g>)}
      </g>
      <g fill="rgba(255,255,255,.20)" fontSize="15" fontWeight="800">{[147, 219, 291, 363, 435, 507, 579, 651, 723].map((y, i) => <text key={y} x="14" y={y}>{['1 0', '2 0', '3 0', '4 0', '5 0', '4 0', '3 0', '2 0', '1 0'][i]}</text>)}</g>
      <g fill="rgba(255,255,255,.20)" fontSize="15" fontWeight="800" textAnchor="end">{[147, 219, 291, 363, 435, 507, 579, 651, 723].map((y, i) => <text key={y} x="486" y={y}>{['1 0', '2 0', '3 0', '4 0', '5 0', '4 0', '3 0', '2 0', '1 0'][i]}</text>)}</g>
    </svg>
  )
}

function PlayerNode({ player, mirror, onSelect }: { player: Placed; mirror: boolean; onSelect: (p: LineupPlayer) => void }) {
  const top = mirror ? 100 - player.y : player.y
  const r = player.rating
  const star = r != null && r >= 8.5
  return (
    <button type="button" className={`player ${player.ol ? 'ol' : ''}`} style={{ left: `${player.x}%`, top: `${top}%` }} title={player.player_name} onClick={() => onSelect(player)}>
      <span className="pav" style={{ background: TEAM_COLORS[player.team] ?? '#6366f1' }}>
        {player.headshot_url ? <img src={player.headshot_url} alt="" /> : initials(player.player_name)}
        {player.scored_td && <span className="td-pip">◒</span>}
        {r != null && !player.ol && <span className={`badge ${ratingClass(r)}`}>{r.toFixed(1)}{star ? ' ✦' : ''}</span>}
      </span>
      <span className="pname"><span className="no">{player.jersey_number ?? ''}</span>{lastName(player.player_name)}</span>
    </button>
  )
}

function scoringByTeam(scoring: LineupScoringEvent[], team: string) {
  const tds = scoring.filter(s => s.team === team && s.kind === 'TD')
  const fgs = new Map<string, LineupScoringEvent[]>()
  for (const s of scoring.filter(s => s.team === team && s.kind === 'FG')) {
    const key = s.player_id ?? s.player_name ?? team
    fgs.set(key, [...(fgs.get(key) ?? []), s])
  }
  return { tds, fgs: [...fgs.values()] }
}

function ScorersBlock({ lineup }: { lineup: GameLineup }) {
  const away = scoringByTeam(lineup.scoring, lineup.away_team)
  const home = scoringByTeam(lineup.scoring, lineup.home_team)
  const col = (data: ReturnType<typeof scoringByTeam>, right = false) => (
    <div className={`sc-col ${right ? 'rt' : ''}`}>
      {data.tds.map((s, i) => <span className="sc" key={`td-${i}`}><span className="glyph">◒</span><b>{lastName(s.player_name)}</b><span className="t">Q{s.qtr} {s.clock}</span></span>)}
      {data.fgs.map((group, i) => <span className="sc" key={`fg-${i}`}><span className="glyph">╋</span><b>{lastName(group[0].player_name)}</b><span className="t">{group.map(s => s.distance).filter(Boolean).join(', ')}</span></span>)}
    </div>
  )
  return <div className="lineup-scorers scorers">{col(away)}<div />{col(home, true)}</div>
}

function RotationList({ team }: { team: LineupTeam }) {
  return <div className="rot-col">{team.rotation.slice(0, 5).map(p => (
    <div className="rrow" key={`${team.team}-${p.player_id ?? p.pfr_player_id}`}>
      <span className="chip" style={{ background: TEAM_COLORS[team.team] ?? '#6366f1' }}>{initials(p.player_name)}</span>
      <span className="who"><b>{p.player_name}</b><span>{p.position ?? '—'} · {pct(p.snap_pct)} snaps</span></span>
      {p.rating != null && <span className={`rbadge ${ratingClass(p.rating)}`}>{p.rating.toFixed(1)}</span>}
    </div>
  ))}</div>
}

function Rail({ game, lineup, sameRound }: { game: GameDetail; lineup: GameLineup; sameRound: GameDetail[] }) {
  const yt = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${lineup.away_team} vs ${lineup.home_team} ${lineup.season} week ${lineup.week} highlights`)}`
  return <aside className="rail">
    <section className="card"><div className="card-h">Highlights <a className="micro act" href={yt} target="_blank" rel="noreferrer">YouTube ↗</a></div><a className="thumb" href={yt} target="_blank" rel="noreferrer"><span className="play"><i>▶</i></span><span className="tl">{lineup.away_team} vs {lineup.home_team} Game Highlights</span></a></section>
    <section className="card venue">
      <div className="card-h"><span className="glyph">⌖</span><div>{game.stadium ?? 'Venue'}<div style={{ fontSize: 10, color: 'var(--t3)', fontWeight: 600, marginTop: 1 }}>via nflverse</div></div></div>
      {game.surface && <div className="vrow"><span className="glyph">≋</span><span className="lab">Surface</span><span className="val">{game.surface}</span></div>}
      {game.roof && <div className="vrow"><span className="glyph">⌂</span><span className="lab">Roof</span><span className="val">{game.roof}</span></div>}
      {(game.temp != null || game.wind != null) && <div className="vrow"><span className="glyph">◌</span><span className="lab">Weather</span><span className="val">{game.temp != null ? `${game.temp}°F` : '—'}<small>{game.wind != null ? `wind ${game.wind} mph` : ''}</small></span></div>}
      {(game.spread_line != null || game.total_line != null) && <div className="vrow"><span className="glyph">⌁</span><span className="lab">Closing line</span><span className="val">{game.spread_line != null ? `${game.home_team} ${game.spread_line > 0 ? '-' : '+'}${Math.abs(game.spread_line)}` : '—'}<small>{game.total_line != null ? `O/U ${game.total_line} · via nflverse` : 'via nflverse'}</small></span></div>}
    </section>
    <section className="card"><div className="card-h">{game.season} Week {game.week}</div>{sameRound.slice(0, 5).map(g => <div className={`row pg ${g.game_id === game.game_id ? 'cur' : ''}`} key={g.game_id} style={{ display: 'grid' }}><span className="lbl">{g.game_type}</span><span className="m"><span className={`tline ${(g.away_score ?? 0) < (g.home_score ?? 0) ? 'dim' : ''}`}><span className="chip" style={{ background: TEAM_COLORS[g.away_team] ?? '#6366f1' }}>{g.away_team}</span>{teamName(g.away_team).split(' ').at(-1)}<span className="scr">{g.away_score ?? '—'}</span></span><span className={`tline ${(g.home_score ?? 0) < (g.away_score ?? 0) ? 'dim' : ''}`}><span className="chip" style={{ background: TEAM_COLORS[g.home_team] ?? '#6366f1' }}>{g.home_team}</span>{teamName(g.home_team).split(' ').at(-1)}<span className="scr">{g.home_score ?? '—'}</span></span></span><span className="ft">FT</span></div>)}</section>
  </aside>
}

function Popup({ game, player, onClose }: { game: GameDetail; player: LineupPlayer | null; onClose: () => void }) {
  const [chart, setChart] = useState<PlayerChart | null>(null)
  useEffect(() => {
    if (!player?.player_id) return
    let cancelled = false
    api.playerChart(game.game_id, player.player_id).then(d => { if (!cancelled) setChart(d) })
    return () => { cancelled = true }
  }, [game.game_id, player?.player_id])
  if (!player) return null
  const role = chart?.role ?? 'player'
  const title = role === 'defender' ? 'Defense' : role === 'rusher' ? 'Rushing' : role === 'receiver' ? 'Receiving' : role === 'passer' ? 'Passing' : 'Game'
  const stats = Object.entries(chart?.stats ?? {}).filter(([, v]) => Number(v) > 0 && (role !== 'defender' || ['sacks', 'tackles', 'def_interceptions'].some(k => k === 'def_interceptions' ? k in chart!.stats : true))).slice(0, 8)
  const events = chart?.events ?? []
  const showMap = role === 'passer' || role === 'receiver'
  const showRush = role === 'rusher'
  return <div className="lineup-overlay" onClick={onClose}><div className="lineup-modal" onClick={e => e.stopPropagation()}>
    <div className="modal-head"><div className="modal-avatar" style={{ background: TEAM_COLORS[player.team] ?? '#6366f1' }}>{player.headshot_url ? <img src={player.headshot_url} alt="" /> : initials(player.player_name)}</div><div><div className="modal-name">{player.player_name}</div><div className="modal-sub">{player.position} · {player.team} · {game.game_type} {game.week} · {pct(player.snap_pct)} of snaps</div></div>{player.rating != null && <span className={`rbadge ${ratingClass(player.rating)} modal-rating`}>{player.rating.toFixed(1)}{player.rating >= 8.5 ? ' ✦' : ''}</span>}<button className="modal-close" onClick={onClose}>✕</button></div>
    <div className={`modal-grid ${role === 'defender' ? 'single' : ''}`}><div><div className="micro popup-title">{title}</div>{stats.map(([k, v]) => <div className="rrow" key={k}><span>{k.replaceAll('_', ' ')}</span><b style={{ marginLeft: 'auto' }}>{String(v)}</b></div>)}</div>{showMap && <div className="target-map"><div className="micro">Target map</div><div className="map-box"><div className="los">LOS</div>{events.slice(0, 40).map((e, i) => <span key={i} className={`dot ${e.outcome === 'Incomplete' ? 'miss' : e.outcome === 'INT' ? 'bad' : 'good'}`} style={{ left: `${e.lane === 'left' ? 25 : e.lane === 'right' ? 75 : 50}%`, bottom: `${24 + Math.min(205, Math.max(0, Number(e.air_yards ?? e.yards ?? 0) * 6))}px` }}>{e.outcome === 'TD' ? '✦' : ''}</span>)}</div><div className="legend"><span>● Catch</span><span>○ Incomplete</span><span>✦ TD</span></div></div>}{showRush && <div className="target-map"><div className="micro">Carry by gap</div><div className="gap-box">{events.slice(0, 30).map((e, i) => <span key={i} className={Number(e.yards ?? 0) >= 0 ? 'good' : 'bad'}>{e.lane || 'run'} · {e.yards ?? 0}</span>)}</div></div>}</div>
    <div className="modal-foot">Charted from nflverse play-by-play — lane = pass direction, depth = air yards. RBs get a carry-by-gap chart; QBs the full passing map.</div>
  </div></div>
}

export default function GameLineupView({ game }: { game: GameDetail }) {
  const [lineup, setLineup] = useState<GameLineup | null>(null)
  const [unit, setUnit] = useState<Unit>('offense')
  const [infoOpen, setInfoOpen] = useState(false)
  const [selected, setSelected] = useState<LineupPlayer | null>(null)
  const [weeks, setWeeks] = useState<WeekGroup[]>([])

  useEffect(() => { api.gameLineup(game.game_id).then(setLineup) }, [game.game_id])
  useEffect(() => { api.schedule(game.season).then(setWeeks).catch(() => setWeeks([])) }, [game.season])

  const away = useMemo(() => lineup?.teams.find(t => t.team === game.away_team), [lineup, game.away_team])
  const home = useMemo(() => lineup?.teams.find(t => t.team === game.home_team), [lineup, game.home_team])
  const sameRound = useMemo(() => weeks.find(w => w.week === game.week)?.games as unknown as GameDetail[] ?? [], [weeks, game.week])

  if (!lineup || !away || !home) return <div className="lineup-card card loading">Loading lineup…</div>
  const awayPlayers = placePlayers(unit === 'offense' ? away.offense : away.defense, unit)
  const homePlayers = placePlayers(unit === 'offense' ? home.offense : home.defense, unit)

  return <><style>{LINEUP_CSS}</style><ScorersBlock lineup={lineup} /><div className="lineup-page"><main className="feed"><section className="lineup-card card"><div className="lu-head"><div className="side"><span className={`avg ${ratingClass(away.avg_rating)}`}>{away.avg_rating ?? '—'}</span><span className="chip" style={{ background: TEAM_COLORS[away.team] ?? '#6366f1' }}>{away.team}</span><div><div className="tn">{teamName(away.team).split(' ').at(-1)}</div><div className="pers">{unit === 'offense' ? away.offense_personnel : away.defense_personnel}</div></div></div><div className="side rt"><span className={`avg ${ratingClass(home.avg_rating)}`}>{home.avg_rating ?? '—'}</span><span className="chip" style={{ background: TEAM_COLORS[home.team] ?? '#6366f1' }}>{home.team}</span><div><div className="tn">{teamName(home.team).split(' ').at(-1)}</div><div className="pers">{unit === 'offense' ? home.offense_personnel : home.defense_personnel}</div></div></div></div><div className="lu-chips"><button className={`upill ${unit === 'offense' ? 'on' : ''}`} onClick={() => setUnit('offense')}>Offense</button><button className={`upill ${unit === 'defense' ? 'on' : ''}`} onClick={() => setUnit('defense')}>Defense</button><button className="info-btn" onClick={(e) => { e.stopPropagation(); setInfoOpen(v => !v) }}>i<span className={`pop ${infoOpen ? 'open' : ''}`}><b>Game ratings</b> — every skill player, defender and kicker gets a 3.0–10.0 grade per game, computed from play-by-play <b>EPA</b> and defensive event stats, calibrated against 27 seasons. 6.5 is league average; 9.0+ is a top-2% performance. Linemen are unrated. Starters and snap counts from official participation data.<span className="ramp"><span className="lg"><i style={{ background: 'var(--rate-bad)' }} />&lt;5.0</span><span className="lg"><i style={{ background: 'var(--rate-mid)' }} />5.0–6.9</span><span className="lg"><i style={{ background: 'var(--rate-good)' }} />7.0+</span><span className="lg"><i style={{ background: 'var(--rate-good)' }} />✦ 8.5+</span></span></span></button></div><div className="fieldwrap"><div className="fieldbox"><FieldSvg awayTeam={away.team} homeTeam={home.team} />{awayPlayers.map(p => <PlayerNode key={`a-${p.player_id ?? p.pfr_player_id}`} player={p} mirror onSelect={setSelected} />)}{homePlayers.map(p => <PlayerNode key={`h-${p.player_id ?? p.pfr_player_id}`} player={p} mirror={false} onSelect={setSelected} />)}</div></div><div className="field-cap"><span className="glyph">◒</span> touchdown · placement shows typical formation, not pre-snap tracking</div><div className="coach"><div><b>{away.team}</b><br /><span>Coach unavailable</span></div><span className="micro">Coaches</span><div className="rt"><b>{home.team}</b><br /><span>Coach unavailable</span></div></div><div className="rot-h micro">Rotation</div><div className="rot"><RotationList team={away} /><RotationList team={home} /></div></section></main><Rail game={game} lineup={lineup} sameRound={sameRound} /></div><Popup key={selected?.player_id ?? selected?.pfr_player_id ?? 'none'} game={game} player={selected} onClose={() => setSelected(null)} /></>
}

const LINEUP_CSS = `
:root{--rate-bad:#ef4444;--rate-mid:#34324a;--rate-good:#10b981;--line:#2e2b3e;--card:#1b1a26;--raise:#262433;--t1:#f4f3f8;--t2:#a3a0b8;--t3:#6c6885;--acc:#818cf8;--acc-fill:#6366f1;--r:14px;--win:#34d399}
.lineup-page{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:20px;align-items:start}.feed{min-width:0}.rail{display:grid;gap:20px}.card{background:var(--card);border-radius:var(--r);overflow:hidden}.lineup-card{border:0}.lineup-scorers{margin:-4px 0 14px;background:var(--card);border-radius:var(--r);border-top:1px solid var(--line)}.scorers{display:grid;grid-template-columns:1fr 44px 1fr;gap:6px 14px;padding:12px 24px}.sc-col{display:flex;flex-direction:column;gap:4px}.sc-col.rt{align-items:flex-end}.sc{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--t2)}.sc b{font-weight:600;color:var(--t2)}.sc .t{color:var(--t3);font-variant-numeric:tabular-nums}.glyph{width:14px;height:14px;flex:none;color:var(--t3)}.chip{width:22px;height:22px;border-radius:50%;flex:none;display:inline-flex;align-items:center;justify-content:center;font-size:8px;font-weight:800;color:#fff}.lu-head{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)}.lu-head .side{display:flex;align-items:center;gap:9px;min-width:0}.lu-head .side.rt{margin-left:auto;flex-direction:row-reverse;text-align:right}.lu-head .tn{font-size:13px;font-weight:800}.lu-head .pers{font-size:10px;color:var(--t3);margin-top:1px}.avg{min-width:34px;text-align:center;padding:3px 7px;border-radius:8px;font-size:12px;font-weight:800;font-variant-numeric:tabular-nums}.lu-chips{display:flex;gap:8px;padding:12px 16px 0;align-items:center}.upill{border:none;border-radius:999px;padding:6px 13px;font-size:11.5px;font-weight:700;background:var(--raise);color:var(--t2);cursor:pointer}.upill.on{background:var(--acc-fill);color:#fff}.info-btn{margin-left:auto;width:24px;height:24px;border-radius:50%;border:1px solid var(--line);background:none;color:var(--t3);font-size:12px;font-weight:700;cursor:pointer;position:relative}.pop{position:absolute;right:0;top:30px;width:270px;background:var(--raise);border:1px solid var(--line);border-radius:10px;padding:12px 14px;font-size:11.5px;font-weight:500;color:var(--t2);text-align:left;line-height:1.55;display:none;z-index:30;box-shadow:0 8px 28px rgba(0,0,0,.5)}.pop.open{display:block}.pop b{color:var(--t1)}.pop .ramp{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}.lg{display:inline-flex;align-items:center;gap:5px;font-size:10px;color:var(--t2)}.lg i{width:16px;height:11px;border-radius:4px;display:inline-block;font-style:normal}.fieldwrap{padding:16px 16px 6px;display:flex;justify-content:center}.fieldbox{position:relative;width:100%;max-width:500px}.fieldbox svg.turf{display:block;width:100%;height:auto;border-radius:12px}.player{position:absolute;width:74px;margin-left:-37px;margin-top:-16px;text-align:center;cursor:pointer;transition:transform .1s;background:none;border:0;padding:0}.player:hover{transform:scale(1.08);z-index:5}.pav{position:relative;width:32px;height:32px;margin:0 auto;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#fff;box-shadow:0 1px 4px rgba(0,0,0,.55),0 0 0 1.5px rgba(14,13,21,.55);overflow:visible}.pav img{width:100%;height:100%;border-radius:50%;object-fit:cover;object-position:top}.badge{position:absolute;top:-6px;right:-13px;min-width:24px;padding:1.5px 4px;border-radius:6px;font-size:9px;font-weight:800;font-variant-numeric:tabular-nums;text-align:center;box-shadow:0 0 0 1.5px rgba(14,13,21,.7)}.b-bad{background:var(--rate-bad);color:#fff}.b-mid{background:var(--rate-mid);color:var(--t1)}.b-good{background:var(--rate-good);color:#04120c}.td-pip{position:absolute;left:-13px;top:-5px;width:14px;height:14px;border-radius:50%;background:rgba(14,13,21,.85);display:flex;align-items:center;justify-content:center;font-size:9px}.pname{display:block;margin-top:3px;font-size:9px;font-weight:600;color:rgba(255,255,255,.92);text-shadow:0 1px 3px rgba(0,0,0,.9);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pname .no{color:rgba(255,255,255,.45);font-weight:700;margin-right:2px}.player.ol .pav{width:26px;height:26px;font-size:8.5px;opacity:.85}.field-cap{padding:8px 16px 14px;font-size:10px;color:var(--t3);display:flex;gap:6px;align-items:center;justify-content:center}.coach{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:11px 16px;border-top:1px solid var(--line);font-size:12px}.coach .rt{text-align:right}.coach b{font-weight:700}.coach span{color:var(--t3);font-size:10px}.micro{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--t3)}.rot-h{padding:11px 16px;border-top:1px solid var(--line);text-align:center}.rot{display:grid;grid-template-columns:1fr 1fr}.rot-col{border-top:1px solid var(--line)}.rot-col:first-child{border-right:1px solid var(--line)}.rrow{display:flex;align-items:center;gap:9px;padding:9px 14px;border-top:1px solid var(--line);font-size:12px}.rrow:first-child{border-top:none}.rrow .who{min-width:0}.rrow .who b{display:block;font-weight:700;font-size:12px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.rrow .who span{font-size:10px;color:var(--t3)}.rrow .rbadge{margin-left:auto}.rbadge{min-width:30px;text-align:center;padding:2px 6px;border-radius:7px;font-size:11px;font-weight:800;font-variant-numeric:tabular-nums;flex:none}.card-h{display:flex;align-items:center;gap:10px;padding:13px 16px;font-size:13px;font-weight:700}.card-h .act{margin-left:auto;font-size:12px;font-weight:600;color:var(--acc);text-decoration:none}.row{display:flex;align-items:center;gap:10px;padding:11px 16px;border-top:1px solid var(--line);color:var(--t1);text-decoration:none}.row.cur{background:var(--raise)}.thumb{position:relative;display:block;margin:0 16px 14px;height:120px;border-radius:10px;overflow:hidden;cursor:pointer;background:linear-gradient(135deg,#173a2a,#0f2c3f 60%,#251a3f)}.thumb .play{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}.thumb .play i{width:44px;height:44px;border-radius:50%;background:rgba(244,243,248,.92);display:flex;align-items:center;justify-content:center;font-size:15px;color:#0e0d15;font-style:normal}.thumb .tl{position:absolute;left:10px;bottom:8px;font-size:11px;font-weight:700;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,.8)}.vrow{display:flex;align-items:center;gap:11px;padding:10px 16px;border-top:1px solid var(--line)}.vrow .lab{font-size:11px;color:var(--t3);font-weight:600}.vrow .val{margin-left:auto;font-size:12.5px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}.vrow .val small{display:block;font-size:10px;color:var(--t3);font-weight:600}.pg{display:grid;grid-template-columns:40px 1fr auto;gap:8px;align-items:center}.pg .lbl{font-size:9px;font-weight:800;letter-spacing:.08em;color:var(--t3);text-transform:uppercase}.pg .m{display:flex;flex-direction:column;gap:3px;min-width:0}.pg .tline{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:600}.pg .tline .scr{margin-left:auto;font-weight:800;font-variant-numeric:tabular-nums}.pg .tline.dim,.pg .tline.dim .scr{color:var(--t3)}.pg .ft{font-size:9.5px;color:var(--t3);font-weight:700}.lineup-overlay{position:fixed;inset:0;background:rgba(8,7,13,.7);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;z-index:60;padding:16px}.lineup-modal{width:100%;max-width:640px;max-height:92vh;overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:var(--r)}.modal-head{display:flex;align-items:center;gap:14px;padding:16px}.modal-avatar{width:52px;height:52px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:#fff;flex:none;overflow:hidden}.modal-avatar img{width:100%;height:100%;object-fit:cover;object-position:top}.modal-name{font-size:18px;font-weight:900}.modal-sub{font-size:11px;color:var(--t3);margin-top:2px}.modal-rating{margin-left:auto;font-size:17px;padding:6px 12px;border-radius:10px}.modal-close{margin-left:8px;border:none;background:var(--raise);color:var(--t2);width:30px;height:30px;border-radius:50%;font-size:13px;cursor:pointer}.modal-grid{display:grid;grid-template-columns:1fr 240px;border-top:1px solid var(--line)}.modal-grid.single{display:block}.modal-grid>div:first-child{border-right:1px solid var(--line)}.modal-grid.single>div:first-child{border-right:0}.popup-title{padding:12px 14px 0}.target-map{padding:14px}.map-box{position:relative;width:100%;height:250px;border-radius:10px;border:1px solid rgba(244,243,248,.08);background:repeating-linear-gradient(180deg,transparent 0 49px,rgba(244,243,248,.1) 49px 50px),linear-gradient(180deg,#10231a,#122a1d);margin-top:8px}.map-box:after{content:'';position:absolute;left:0;right:0;bottom:24px;height:2px;background:rgba(244,243,248,.3)}.los{position:absolute;right:6px;bottom:8px;font-size:8px;font-weight:800;letter-spacing:.15em;color:rgba(244,243,248,.4)}.dot{position:absolute;width:11px;height:11px;margin:-5.5px;border-radius:50%;box-shadow:0 0 0 2px rgba(14,13,21,.6);font-size:8px;text-align:center;line-height:11px}.dot.good{background:var(--rate-good);color:#04120c}.dot.bad{background:var(--rate-bad)}.dot.miss{background:transparent;border:2.5px solid var(--t2)}.legend{display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;font-size:10px;color:var(--t2)}.gap-box{display:grid;gap:6px;margin-top:8px}.gap-box span{padding:8px;border-radius:8px;background:var(--raise);font-size:11px}.gap-box .good{color:var(--win)}.gap-box .bad{color:var(--rate-bad)}.modal-foot{padding:10px 16px;border-top:1px solid var(--line);font-size:10px;color:var(--t3)}
@media(max-width:980px){.lineup-page{grid-template-columns:1fr}.rot{grid-template-columns:1fr}.rot-col:first-child{border-right:none}.lineup-scorers{grid-template-columns:1fr;gap:10px}.lineup-scorers>div:nth-child(2){display:none}.fieldwrap{padding-left:8px;padding-right:8px}.modal-grid{grid-template-columns:1fr}.modal-grid>div:first-child{border-right:0}.rail{display:grid}}
`
