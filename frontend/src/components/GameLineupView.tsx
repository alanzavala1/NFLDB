import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { GameDetail, GameLineup, LineupPlayer, LineupScoringEvent, LineupTeam, PlayerChart } from '../api'
import { teamName, teamPrimaryColor } from '../utils/teams'

type Unit = 'offense' | 'defense'
type Placed = LineupPlayer & { x: number; y: number; ol?: boolean }

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
  const suffixes = new Set(['Jr.', 'Sr.', 'II', 'III', 'IV', 'V'])
  const last = parts.at(-1) ?? name
  if (parts.length > 1 && suffixes.has(last)) return `${parts.at(-2)} ${last}`
  return last
}

function titleCase(value: string | null | undefined) {
  if (!value) return ''
  return value.toLowerCase().replace(/\b[a-z]/g, c => c.toUpperCase())
}

function ratingClass(r: number | null | undefined) {
  if (r == null) return ''
  if (r < 5) return 'b-bad'
  if (r < 7) return 'b-mid'
  return 'b-good'
}

function pct(v: number | null | undefined) {
  return v == null ? '-' : `${Math.round(v * 100)}%`
}

function roman(n: number) {
  const vals: [number, string][] = [[100, 'C'], [90, 'XC'], [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']]
  let out = ''
  for (const [value, sym] of vals) {
    while (n >= value) {
      out += sym
      n -= value
    }
  }
  return out
}

function gameLabel(game: GameDetail) {
  if (game.game_type === 'SB') return `Super Bowl ${roman(game.season - 1965)}`
  if (game.game_type === 'CONF' || game.game_type === 'CON') return 'Conference'
  if (game.game_type === 'DIV') return 'Divisional'
  if (game.game_type === 'WC') return 'Wild Card'
  return `Week ${game.week}`
}

function roundTitle(game: GameDetail) {
  return game.game_type === 'REG' ? `${game.season} Week ${game.week}` : `${game.season} Postseason`
}

function roundLabel(gameType: string) {
  return ({ WC: 'WC', DIV: 'DIV', CONF: 'CONF', CON: 'CONF', SB: 'SB', REG: 'WK' } as Record<string, string>)[gameType] ?? gameType
}

function spreadLabel(game: GameDetail) {
  const spread = game.spread_line
  if (spread == null) return '-'
  if (spread === 0) return 'Pick'
  const favorite = spread < 0 ? game.away_team : game.home_team
  return `${favorite} -${Math.abs(spread)}`
}

const STAT_LABELS: Record<string, string> = {
  attempts: 'Attempts',
  completions: 'Completions',
  pass_yards: 'Passing yards',
  pass_tds: 'Passing TD',
  interceptions_thrown: 'Interceptions',
  targets: 'Targets',
  receptions: 'Receptions',
  rec_yards: 'Receiving yards',
  rec_tds: 'Receiving TD',
  carries: 'Carries',
  rush_yards: 'Rushing yards',
  rush_tds: 'Rushing TD',
  sacks: 'Sacks',
  tackles: 'Tackles',
  def_interceptions: 'Interceptions',
  pass_epa: 'EPA',
  rec_epa: 'EPA',
  rush_epa: 'EPA',
}

const ROLE_STAT_KEYS: Record<string, string[]> = {
  passer: ['attempts', 'completions', 'pass_yards', 'pass_tds', 'interceptions_thrown', 'pass_epa'],
  receiver: ['targets', 'receptions', 'rec_yards', 'rec_tds', 'rec_epa'],
  rusher: ['carries', 'rush_yards', 'rush_tds', 'rush_epa'],
  defender: ['sacks', 'tackles', 'def_interceptions'],
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

function fallbackRole(position: string | null | undefined) {
  const pos = (position ?? '').toUpperCase()
  if (['DT', 'DE', 'DL', 'NT', 'EDGE', 'CB', 'DB', 'NB', 'LB', 'ILB', 'OLB', 'MLB', 'FS', 'SS', 'S'].includes(pos)) return 'defender'
  if (pos === 'QB') return 'passer'
  if (['WR', 'TE'].includes(pos)) return 'receiver'
  if (['RB', 'FB', 'HB'].includes(pos)) return 'rusher'
  return 'player'
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
    let [x, y] = coords[Math.min(idx, coords.length - 1)]
    // A group can exceed its template slots (e.g. 3 safeties in a big-nickel
    // look); fan extras horizontally off the last slot so nodes never stack.
    const overflow = idx - (coords.length - 1)
    if (overflow > 0) {
      const step = Math.ceil(overflow / 2) * 14 * (overflow % 2 === 1 ? 1 : -1)
      x = Math.min(93, Math.max(7, x + step))
      y += 3.5
    }
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
      <rect x="0" y="0" width="500" height="70" fill={teamPrimaryColor(awayTeam)} opacity=".16" /><rect x="0" y="0" width="500" height="70" fill="url(#ezstripe-lineup)" />
      <rect x="0" y="790" width="500" height="70" fill={teamPrimaryColor(homeTeam)} opacity=".16" /><rect x="0" y="790" width="500" height="70" fill="url(#ezstripe-lineup)" />
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
      <span className="pav" style={{ background: teamPrimaryColor(player.team) }}>
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

export function GameScorers({ lineup }: { lineup: GameLineup }) {
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
      <span className="chip" style={{ background: teamPrimaryColor(team.team) }}>{initials(p.player_name)}</span>
      <span className="who"><b>{p.player_name}</b><span>{p.position ?? '—'} · {pct(p.snap_pct)} snaps</span></span>
      {p.rating != null && <span className={`rbadge ${ratingClass(p.rating)}`}>{p.rating.toFixed(1)}</span>}
    </div>
  ))}</div>
}

function teamNickname(team: string) {
  return teamName(team).split(' ').at(-1) ?? team
}

function formatStatValue(key: string, value: unknown) {
  const num = Number(value)
  if (key.endsWith('_epa') && Number.isFinite(num)) return `${num >= 0 ? '+' : ''}${num.toFixed(1)}`
  return String(value)
}

function statColor(key: string, value: unknown) {
  if (!key.endsWith('_epa')) return undefined
  return Number(value) >= 0 ? 'var(--win)' : 'var(--rate-bad)'
}

export function GameRail({ game, lineup, sameRound }: { game: GameDetail; lineup: GameLineup; sameRound: GameDetail[] }) {
  const yt = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${lineup.away_team} vs ${lineup.home_team} ${lineup.season} week ${lineup.week} highlights`)}`
  return <aside className="rail">
    <section className="card"><div className="card-h">Highlights <a className="micro act" href={yt} target="_blank" rel="noreferrer">YouTube ↗</a></div><a className="thumb" href={yt} target="_blank" rel="noreferrer"><span className="play"><i>▶</i></span><span className="tl">{lineup.away_team} vs {lineup.home_team} Game Highlights</span></a></section>
    <section className="card venue">
      <div className="card-h"><span className="glyph">⌖</span><div>{game.stadium ?? 'Venue'}</div></div>
      {game.surface && <div className="vrow"><span className="glyph">≋</span><span className="lab">Surface</span><span className="val">{titleCase(game.surface)}</span></div>}
      {game.roof && <div className="vrow"><span className="glyph">⌂</span><span className="lab">Roof</span><span className="val">{titleCase(game.roof)}</span></div>}
      {(game.temp != null || game.wind != null) && <div className="vrow"><span className="glyph">◌</span><span className="lab">Weather</span><span className="val">{game.temp != null ? `${game.temp}°F` : '-'}<small>{game.wind != null ? `wind ${game.wind} mph` : ''}</small></span></div>}
      {(game.spread_line != null || game.total_line != null) && <div className="vrow"><span className="glyph">⌁</span><span className="lab">Closing line</span><span className="val">{spreadLabel(game)}<small>{game.total_line != null ? `O/U ${game.total_line} · via nflverse` : 'via nflverse'}</small></span></div>}
    </section>
    <section className="card"><div className="card-h">{roundTitle(game)}</div>{sameRound.map(g => <div className={`row pg ${g.game_id === game.game_id ? 'cur' : ''}`} key={g.game_id} style={{ display: 'grid' }}><span className="lbl">{roundLabel(g.game_type)}</span><span className="m"><span className={`tline ${(g.away_score ?? 0) < (g.home_score ?? 0) ? 'dim' : ''}`}><span className="chip" style={{ background: teamPrimaryColor(g.away_team) }}>{g.away_team}</span>{teamNickname(g.away_team)}<span className="scr">{g.away_score ?? '-'}</span></span><span className={`tline ${(g.home_score ?? 0) < (g.away_score ?? 0) ? 'dim' : ''}`}><span className="chip" style={{ background: teamPrimaryColor(g.home_team) }}>{g.home_team}</span>{teamNickname(g.home_team)}<span className="scr">{g.home_score ?? '-'}</span></span></span><span className="ft">FT</span></div>)}</section>
  </aside>
}

type ZoneCell = { att: number; comp: number; yds: number; td: boolean; int: boolean }

const ZONE_BANDS = [
  { key: '20+', min: 20, max: Infinity },
  { key: '10–19', min: 10, max: 19.5 },
  { key: '0–9', min: 0, max: 9.5 },
  { key: 'Screen', min: -Infinity, max: -0.5 },
] as const
const ZONE_LANES = ['left', 'middle', 'right'] as const

function zoneData(events: PlayerChart['events']) {
  const cells = new Map<string, ZoneCell>()
  let plotted = 0
  for (const e of events) {
    const lane = (e.lane ?? '').toLowerCase()
    if (e.air_yards == null || !ZONE_LANES.includes(lane as typeof ZONE_LANES[number])) continue
    const band = ZONE_BANDS.find(b => e.air_yards! >= b.min && e.air_yards! <= b.max)
    if (!band) continue
    const key = `${band.key}|${lane}`
    const cell = cells.get(key) ?? { att: 0, comp: 0, yds: 0, td: false, int: false }
    cell.att += 1
    if (e.outcome === 'Complete' || e.outcome === 'TD') {
      cell.comp += 1
      cell.yds += Number(e.yards ?? 0)
    }
    if (e.outcome === 'TD') cell.td = true
    if (e.outcome === 'INT') cell.int = true
    cells.set(key, cell)
    plotted += 1
  }
  return { cells, plotted }
}

function zoneShade(att: number) {
  if (att <= 0) return 'z0'
  if (att === 1) return 'z1'
  if (att <= 3) return 'z2'
  return 'z3'
}

function ZoneGrid({ events }: { events: PlayerChart['events'] }) {
  const { cells, plotted } = zoneData(events)
  if (plotted === 0) return null
  return (
    <div>
      <div className="micro">Passing zones · comp/att</div>
      <div className="zones">
        <span className="zlab" /><span className="zlab col">Left</span><span className="zlab col">Middle</span><span className="zlab col">Right</span>
        {ZONE_BANDS.map(band => (
          <span key={band.key} style={{ display: 'contents' }}>
            <span className="zlab">{band.key}</span>
            {ZONE_LANES.map(lane => {
              const cell = cells.get(`${band.key}|${lane}`)
              if (!cell) return <div key={lane} className="zcell z0"><b>—</b></div>
              return <div key={lane} className={`zcell ${zoneShade(cell.att)}`}>
                {cell.td && <span className="zstar">✦</span>}
                {cell.int && <span className="zint">✕</span>}
                <b>{cell.comp}/{cell.att}</b>
                <small>{Math.round(cell.yds)} yds</small>
              </div>
            })}
          </span>
        ))}
        <span className="zone-los">Line of scrimmage</span>
      </div>
      <div className="legend"><span className="lg"><i style={{ background: '#403a6e' }} />More attempts</span><span style={{ color: 'var(--rate-good)' }}>✦ TD</span><span style={{ color: 'var(--rate-bad)' }}>✕ INT</span></div>
    </div>
  )
}

const GAP_ORDER = [
  { key: 'left end', label: 'L END' },
  { key: 'left tackle', label: 'L TKL' },
  { key: 'left guard', label: 'L GRD' },
  { key: 'middle', label: 'MID' },
  { key: 'right guard', label: 'R GRD' },
  { key: 'right tackle', label: 'R TKL' },
  { key: 'right end', label: 'R END' },
] as const

function GapStrip({ events }: { events: PlayerChart['events'] }) {
  const gaps = new Map<string, { att: number; yds: number; td: boolean }>()
  for (const e of events) {
    if (e.role !== 'rusher') continue
    const key = (e.lane ?? '').toLowerCase().trim()
    if (!GAP_ORDER.some(g => g.key === key)) continue
    const cell = gaps.get(key) ?? { att: 0, yds: 0, td: false }
    cell.att += 1
    cell.yds += Number(e.yards ?? 0)
    if (e.outcome === 'TD') cell.td = true
    gaps.set(key, cell)
  }
  if (gaps.size === 0) return null
  return (
    <div>
      <div className="micro">Run direction · carries &amp; yards</div>
      <div className="gaps">
        {GAP_ORDER.map(g => {
          const cell = gaps.get(g.key)
          return <div key={g.key} className={`gcell ${zoneShade(cell?.att ?? 0)}`}>
            {cell?.td && <span className="zstar">✦</span>}
            <b>{cell?.att ?? '—'}</b>
            {cell && <small>{Math.round(cell.yds)} yds</small>}
            <span className="glab">{g.label}</span>
          </div>
        })}
      </div>
      <div className="oline-strip"><span /><span className="oc" /><span className="oc" /><span className="oc" /><span className="oc" /><span className="oc" /><span /></div>
      <div className="oline-cap">Offensive line</div>
    </div>
  )
}

function avgDepthOfTarget(events: PlayerChart['events']) {
  const depths = events.filter(e => e.air_yards != null).map(e => e.air_yards as number)
  if (!depths.length) return null
  return depths.reduce((s, v) => s + v, 0) / depths.length
}

function Popup({ game, player, onClose }: { game: GameDetail; player: LineupPlayer | null; onClose: () => void }) {
  const [chart, setChart] = useState<PlayerChart | null>(null)
  useEffect(() => {
    if (!player?.player_id) return
    let cancelled = false
    api.playerChart(game.game_id, player.player_id).then(d => { if (!cancelled) setChart(d) })
    return () => { cancelled = true }
  }, [game.game_id, player?.player_id])
  useEffect(() => {
    if (!player) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [player, onClose])
  if (!player) return null
  const role = chart?.role ?? fallbackRole(player.position)
  const title = role === 'defender' ? 'Defense' : role === 'rusher' ? 'Rushing' : role === 'receiver' ? 'Receiving' : role === 'passer' ? 'Passing' : 'Game'
  const stats = (ROLE_STAT_KEYS[role] ?? Object.keys(chart?.stats ?? {}))
    .map(k => [k, chart?.stats?.[k as keyof typeof chart.stats]] as const)
    .filter(([k, v]) => {
      const num = Number(v)
      if (!Number.isFinite(num)) return false
      return k.endsWith('_epa') ? num !== 0 : num > 0
    })
    .slice(0, 8)
  const events = chart?.events ?? []
  const showZones = role === 'passer' || role === 'receiver'
  const showRush = role === 'rusher'
  const adot = role === 'passer' ? avgDepthOfTarget(events) : null
  const footer = showRush
    ? 'From nflverse play-by-play: gap = recorded run gap and direction. Cell shading = more carries. Exact counts, no interpolation.'
    : showZones
      ? "From nflverse play-by-play: lane = recorded pass direction (left/middle/right), band = air yards. Cells show completions/attempts and yards — exact counts, drawn at the data's real resolution."
      : 'From nflverse play-by-play and official game stats.'
  return <div className="lineup-overlay" onClick={onClose}><div className="lineup-modal" onClick={e => e.stopPropagation()}>
    <div className="modal-head"><div className="modal-avatar" style={{ background: teamPrimaryColor(player.team) }}>{player.headshot_url ? <img src={player.headshot_url} alt="" /> : initials(player.player_name)}</div><div><div className="modal-name">{player.player_name}</div><div className="modal-sub">{player.position} · {player.team} · {gameLabel(game)} · {pct(player.snap_pct)} of snaps</div></div>{player.rating != null && <span className={`rbadge ${ratingClass(player.rating)} modal-rating`}>{player.rating.toFixed(1)}{player.rating >= 8.5 ? ' ✦' : ''}</span>}<button className="modal-close" onClick={onClose}>✕</button></div>
    <div className={`modal-grid ${role === 'defender' ? 'single' : ''}`}><div><div className="micro popup-title">{title}</div>{stats.map(([k, v]) => <div className="rrow" key={k}><span>{STAT_LABELS[k] ?? titleCase(k.replaceAll('_', ' '))}</span><b style={{ marginLeft: 'auto', color: statColor(k, v) }}>{formatStatValue(k, v)}</b></div>)}{adot != null && <div className="rrow"><span>Average depth of target</span><b style={{ marginLeft: 'auto' }}>{adot.toFixed(1)}</b></div>}</div>{showZones &&<div className="target-map"><ZoneGrid events={events} /></div>}{showRush && <div className="target-map"><GapStrip events={events} /></div>}</div>
    <div className="modal-foot">{footer}</div>
  </div></div>
}

export default function GameLineupView({ game, lineup }: { game: GameDetail; lineup: GameLineup | null }) {
  const [ball, setBall] = useState<'away' | 'home'>('home')
  const [infoOpen, setInfoOpen] = useState(false)
  const [selected, setSelected] = useState<LineupPlayer | null>(null)

  const away = useMemo(() => lineup?.teams.find(t => t.team === game.away_team), [lineup, game.away_team])
  const home = useMemo(() => lineup?.teams.find(t => t.team === game.home_team), [lineup, game.home_team])
  if (!lineup || !away || !home) return <div className="lineup-card card loading">Loading lineup…</div>
  // Matchup view: the possessing team's offense on the bottom half, the
  // opposing defense mirrored on top — one real football situation at a time.
  const off = ball === 'away' ? away : home
  const def = ball === 'away' ? home : away
  const offense = placePlayers(off.offense, 'offense')
  const defense = placePlayers(def.defense, 'defense')

  return <>
    <style>{LINEUP_CSS}</style>
    <div className="feed">
        <section className="lineup-card card">
          <div className="lu-head">
            <div className="side">
              <span className={`avg ${ratingClass(off.offense_avg)}`}>{off.offense_avg?.toFixed(1) ?? '-'}</span>
              <span className="chip" style={{ background: teamPrimaryColor(off.team) }}>{off.team}</span>
              <div><div className="tn">{teamNickname(off.team)} offense</div><div className="pers">{off.offense_personnel}</div></div>
            </div>
            <div className="side rt">
              <span className={`avg ${ratingClass(def.defense_avg)}`}>{def.defense_avg?.toFixed(1) ?? '-'}</span>
              <span className="chip" style={{ background: teamPrimaryColor(def.team) }}>{def.team}</span>
              <div><div className="tn">{teamNickname(def.team)} defense</div><div className="pers">{def.defense_personnel}</div></div>
            </div>
          </div>
          <div className="lu-chips">
            <button className={`upill ${ball === 'away' ? 'on' : ''}`} onClick={() => setBall('away')}><span className="mini" style={{ background: teamPrimaryColor(away.team) }} />{teamNickname(away.team)} ball</button>
            <button className={`upill ${ball === 'home' ? 'on' : ''}`} onClick={() => setBall('home')}><span className="mini" style={{ background: teamPrimaryColor(home.team) }} />{teamNickname(home.team)} ball</button>
            <button className="info-btn" onClick={(e) => { e.stopPropagation(); setInfoOpen(v => !v) }}>i<span className={`pop ${infoOpen ? 'open' : ''}`}><b>Game ratings</b> — every skill player, defender and kicker gets a 3.0–10.0 grade per game, computed from play-by-play <b>EPA</b> and defensive event stats, calibrated against 27 seasons. 6.5 is league average; 9.0+ is a top-2% performance. <b>Linemen share one unit grade</b> — public data records nothing per-blocker, so the line is graded on what it allows together: sacks, QB hits and stuffed runs versus league average. The field shows one team's offense against the other's defense; placement is the typical formation, not tracking.<span className="ramp"><span className="lg"><i style={{ background: 'var(--rate-bad)' }} />&lt;5.0</span><span className="lg"><i style={{ background: 'var(--rate-mid)' }} />5.0–6.9</span><span className="lg"><i style={{ background: 'var(--rate-good)' }} />7.0+</span><span className="lg"><i style={{ background: 'var(--rate-good)' }} />✦ 8.5+</span></span></span></button>
          </div>
          <div className="fieldwrap"><div className="fieldbox">
            <FieldSvg awayTeam={def.team} homeTeam={off.team} />
            {defense.map(p => <PlayerNode key={`d-${p.player_id ?? p.pfr_player_id}`} player={p} mirror onSelect={setSelected} />)}
            {offense.map(p => <PlayerNode key={`o-${p.player_id ?? p.pfr_player_id}`} player={p} mirror={false} onSelect={setSelected} />)}
            {off.ol_grade != null && <div className="ol-unit" style={{ left: '50%', top: '70.5%' }}><span className="micro">O-Line</span><span className={`val ${ratingClass(off.ol_grade)}`}>{off.ol_grade.toFixed(1)}</span></div>}
          </div></div>
          <div className="field-cap"><span className="glyph">◒</span> touchdown · offense vs the opposing defense · placement shows typical formation, not tracking · line grade is unit-level</div>
          {(lineup.away_coach || lineup.home_coach) && <div className="coach"><div><b>{lineup.away_coach}</b><br /><span>{away.team}</span></div><span className="micro">Coaches</span><div className="rt"><b>{lineup.home_coach}</b><br /><span>{home.team}</span></div></div>}
          <div className="rot-h micro">Rotation</div>
          <div className="rot"><RotationList team={away} /><RotationList team={home} /></div>
        </section>
    </div>
    <Popup key={selected?.player_id ?? selected?.pfr_player_id ?? 'none'} game={game} player={selected} onClose={() => setSelected(null)} />
  </>
}

export const LINEUP_CSS = `
:root{--rate-bad:#ef4444;--rate-mid:#34324a;--rate-good:#10b981;--line:#2e2b3e;--card:#1b1a26;--raise:#262433;--t1:#f4f3f8;--t2:#a3a0b8;--t3:#6c6885;--acc:#818cf8;--acc-fill:#6366f1;--r:14px;--win:#34d399}
.lineup-page{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:20px;align-items:start}.feed{min-width:0}.rail{display:grid;gap:20px}.card{background:var(--card);border-radius:var(--r);overflow:hidden}.lineup-card{border:0}.lineup-scorers{margin:-4px 0 14px;background:var(--card);border-radius:var(--r);border-top:1px solid var(--line)}.scorers{display:grid;grid-template-columns:1fr 44px 1fr;gap:6px 14px;padding:12px 24px}.sc-col{display:flex;flex-direction:column;gap:4px}.sc-col.rt{align-items:flex-end}.sc{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--t2)}.sc b{font-weight:600;color:var(--t2)}.sc .t{color:var(--t3);font-variant-numeric:tabular-nums}.glyph{width:14px;height:14px;flex:none;color:var(--t3)}.chip{width:22px;height:22px;border-radius:50%;flex:none;display:inline-flex;align-items:center;justify-content:center;font-size:8px;font-weight:800;color:#fff}.lu-head{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)}.lu-head .side{display:flex;align-items:center;gap:9px;min-width:0}.lu-head .side.rt{margin-left:auto;flex-direction:row-reverse;text-align:right}.lu-head .tn{font-size:13px;font-weight:800}.lu-head .pers{font-size:10px;color:var(--t3);margin-top:1px}.avg{min-width:34px;text-align:center;padding:3px 7px;border-radius:8px;font-size:12px;font-weight:800;font-variant-numeric:tabular-nums}.lu-chips{display:flex;gap:8px;padding:12px 16px 0;align-items:center}.upill{border:none;border-radius:999px;padding:6px 13px;font-size:11.5px;font-weight:700;background:var(--raise);color:var(--t2);cursor:pointer}.upill.on{background:var(--acc-fill);color:#fff}.info-btn{margin-left:auto;width:24px;height:24px;border-radius:50%;border:1px solid var(--line);background:none;color:var(--t3);font-size:12px;font-weight:700;cursor:pointer;position:relative}.pop{position:absolute;right:0;top:30px;width:270px;background:var(--raise);border:1px solid var(--line);border-radius:10px;padding:12px 14px;font-size:11.5px;font-weight:500;color:var(--t2);text-align:left;line-height:1.55;display:none;z-index:30;box-shadow:0 8px 28px rgba(0,0,0,.5)}.pop.open{display:block}.pop b{color:var(--t1)}.pop .ramp{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}.lg{display:inline-flex;align-items:center;gap:5px;font-size:10px;color:var(--t2)}.lg i{width:16px;height:11px;border-radius:4px;display:inline-block;font-style:normal}.fieldwrap{padding:16px 16px 6px;display:flex;justify-content:center}.fieldbox{position:relative;width:100%;max-width:500px}.fieldbox svg.turf{display:block;width:100%;height:auto;border-radius:12px}.player{position:absolute;width:74px;margin-left:-37px;margin-top:-16px;text-align:center;cursor:pointer;transition:transform .1s;background:none;border:0;padding:0}.player:hover{transform:scale(1.08);z-index:5}.pav{position:relative;width:32px;height:32px;margin:0 auto;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#fff;box-shadow:0 1px 4px rgba(0,0,0,.55),0 0 0 1.5px rgba(14,13,21,.55);overflow:visible}.pav img{width:100%;height:100%;border-radius:50%;object-fit:cover;object-position:top}.badge{position:absolute;top:-6px;right:-13px;min-width:24px;padding:1.5px 4px;border-radius:6px;font-size:9px;font-weight:800;font-variant-numeric:tabular-nums;text-align:center;box-shadow:0 0 0 1.5px rgba(14,13,21,.7)}.b-bad{background:var(--rate-bad);color:#fff}.b-mid{background:var(--rate-mid);color:var(--t1)}.b-good{background:var(--rate-good);color:#04120c}.td-pip{position:absolute;left:-13px;top:-5px;width:14px;height:14px;border-radius:50%;background:rgba(14,13,21,.85);display:flex;align-items:center;justify-content:center;font-size:9px}.pname{display:block;margin-top:3px;font-size:9px;font-weight:600;color:rgba(255,255,255,.92);text-shadow:0 1px 3px rgba(0,0,0,.9);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pname .no{color:rgba(255,255,255,.45);font-weight:700;margin-right:2px}.player.ol .pav{width:26px;height:26px;font-size:8.5px;opacity:.85}.field-cap{padding:8px 16px 14px;font-size:10px;color:var(--t3);display:flex;gap:6px;align-items:center;justify-content:center}.coach{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:11px 16px;border-top:1px solid var(--line);font-size:12px}.coach .rt{text-align:right}.coach b{font-weight:700}.coach span{color:var(--t3);font-size:10px}.micro{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--t3)}.rot-h{padding:11px 16px;border-top:1px solid var(--line);text-align:center}.rot{display:grid;grid-template-columns:1fr 1fr}.rot-col{border-top:1px solid var(--line)}.rot-col:first-child{border-right:1px solid var(--line)}.rrow{display:flex;align-items:center;gap:9px;padding:9px 14px;border-top:1px solid var(--line);font-size:12px}.rrow:first-child{border-top:none}.rrow .who{min-width:0}.rrow .who b{display:block;font-weight:700;font-size:12px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.rrow .who span{font-size:10px;color:var(--t3)}.rrow .rbadge{margin-left:auto}.rbadge{min-width:30px;text-align:center;padding:2px 6px;border-radius:7px;font-size:11px;font-weight:800;font-variant-numeric:tabular-nums;flex:none}.card-h{display:flex;align-items:center;gap:10px;padding:13px 16px;font-size:13px;font-weight:700}.card-h .act{margin-left:auto;font-size:12px;font-weight:600;color:var(--acc);text-decoration:none}.row{display:flex;align-items:center;gap:10px;padding:11px 16px;border-top:1px solid var(--line);color:var(--t1);text-decoration:none}.row.cur{background:var(--raise)}.thumb{position:relative;display:block;margin:0 16px 14px;height:120px;border-radius:10px;overflow:hidden;cursor:pointer;background:linear-gradient(135deg,#173a2a,#0f2c3f 60%,#251a3f)}.thumb .play{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}.thumb .play i{width:44px;height:44px;border-radius:50%;background:rgba(244,243,248,.92);display:flex;align-items:center;justify-content:center;font-size:15px;color:#0e0d15;font-style:normal}.thumb .tl{position:absolute;left:10px;bottom:8px;font-size:11px;font-weight:700;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,.8)}.vrow{display:flex;align-items:center;gap:11px;padding:10px 16px;border-top:1px solid var(--line)}.vrow .lab{font-size:11px;color:var(--t3);font-weight:600}.vrow .val{margin-left:auto;font-size:12.5px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}.vrow .val small{display:block;font-size:10px;color:var(--t3);font-weight:600}.pg{display:grid;grid-template-columns:40px 1fr auto;gap:8px;align-items:center}.pg .lbl{font-size:9px;font-weight:800;letter-spacing:.08em;color:var(--t3);text-transform:uppercase}.pg .m{display:flex;flex-direction:column;gap:3px;min-width:0}.pg .tline{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:600}.pg .tline .scr{margin-left:auto;font-weight:800;font-variant-numeric:tabular-nums}.pg .tline.dim,.pg .tline.dim .scr{color:var(--t3)}.pg .ft{font-size:9.5px;color:var(--t3);font-weight:700}.lineup-overlay{position:fixed;inset:0;background:rgba(8,7,13,.7);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;z-index:60;padding:16px}.lineup-modal{width:100%;max-width:640px;max-height:92vh;overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:var(--r)}.modal-head{display:flex;align-items:center;gap:14px;padding:16px}.modal-avatar{width:52px;height:52px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:#fff;flex:none;overflow:hidden}.modal-avatar img{width:100%;height:100%;object-fit:cover;object-position:top}.modal-name{font-size:18px;font-weight:900}.modal-sub{font-size:11px;color:var(--t3);margin-top:2px}.modal-rating{margin-left:auto;font-size:17px;padding:6px 12px;border-radius:10px}.modal-close{margin-left:8px;border:none;background:var(--raise);color:var(--t2);width:30px;height:30px;border-radius:50%;font-size:13px;cursor:pointer}.modal-grid{display:grid;grid-template-columns:1fr 280px;border-top:1px solid var(--line)}.modal-grid.single{display:block}.modal-grid>div:first-child{border-right:1px solid var(--line)}.modal-grid.single>div:first-child{border-right:0}.popup-title{padding:12px 14px 0}.target-map{padding:14px}.legend{display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;font-size:10px;color:var(--t2);align-items:center}.modal-foot{padding:10px 16px;border-top:1px solid var(--line);font-size:10px;color:var(--t3)}
.upill .mini{width:14px;height:14px;border-radius:50%;display:inline-block;margin-right:7px;vertical-align:-2px}
.ol-unit{position:absolute;transform:translate(-50%,-50%);display:flex;align-items:center;gap:6px;background:rgba(14,13,21,.82);border:1px solid var(--line);border-radius:8px;padding:3px 9px;pointer-events:none}
.ol-unit .micro{letter-spacing:.1em;font-size:8.5px}.ol-unit .val{font-size:10.5px;font-weight:800;padding:1px 6px;border-radius:5px;font-variant-numeric:tabular-nums}
.zones{display:grid;grid-template-columns:46px repeat(3,1fr);gap:4px;align-items:stretch;margin-top:8px}
.zlab{display:flex;align-items:center;font-size:8.5px;font-weight:800;letter-spacing:.08em;color:var(--t3);text-transform:uppercase}.zlab.col{justify-content:center;padding-bottom:2px}
.zcell{position:relative;border-radius:8px;padding:8px 6px 7px;text-align:center;min-height:52px;display:flex;flex-direction:column;justify-content:center;gap:2px}
.z0{background:var(--raise);opacity:.45}.z1{background:var(--raise)}.z2{background:#332f52}.z3{background:#403a6e}
.zcell b{font-size:13px;font-weight:800;font-variant-numeric:tabular-nums}.zcell small{font-size:9px;color:var(--t2);font-variant-numeric:tabular-nums}
.zcell .zstar,.gcell .zstar{position:absolute;top:4px;right:6px;font-size:9px;color:var(--rate-good)}.zcell .zint{position:absolute;top:4px;left:6px;font-size:8px;font-weight:900;color:var(--rate-bad)}
.zone-los{grid-column:2/5;text-align:center;font-size:8px;font-weight:800;letter-spacing:.2em;color:var(--t3);border-top:2px solid rgba(244,243,248,.25);padding-top:3px;margin-top:2px;text-transform:uppercase}
.gaps{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-top:8px}
.gcell{position:relative;border-radius:8px;padding:7px 2px 6px;text-align:center;min-height:56px;display:flex;flex-direction:column;justify-content:center;gap:1px}
.gcell b{font-size:12.5px;font-weight:800;font-variant-numeric:tabular-nums}.gcell small{font-size:8.5px;color:var(--t2);font-variant-numeric:tabular-nums}.gcell .glab{font-size:7.5px;font-weight:800;letter-spacing:.06em;color:var(--t3);margin-top:2px}
.oline-strip{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-top:6px}.oline-strip .oc{width:14px;height:14px;border-radius:50%;background:var(--raise);margin:0 auto;border:1px solid var(--line)}
.oline-cap{text-align:center;font-size:8px;color:var(--t3);margin-top:2px;letter-spacing:.15em;text-transform:uppercase}
@media(max-width:980px){.lineup-page{grid-template-columns:1fr}.rot{grid-template-columns:1fr}.rot-col:first-child{border-right:none}.lineup-scorers{grid-template-columns:1fr;gap:10px}.lineup-scorers>div:nth-child(2){display:none}.fieldwrap{padding-left:8px;padding-right:8px}.modal-grid{grid-template-columns:1fr}.modal-grid>div:first-child{border-right:0}.rail{display:grid}}
`
