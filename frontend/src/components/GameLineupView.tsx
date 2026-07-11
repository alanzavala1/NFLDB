import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { GameDetail, GameLineup, LineupPlayer, LineupScoringEvent, LineupTeam, PlayerChart } from '../api'
import { teamLogoUrl, teamName } from '../utils/teams'

type Unit = 'offense' | 'defense'

const OFF_POS: Record<string, [number, number][]> = {
  QB: [[18, 50]],
  RB: [[30, 42], [30, 58]],
  FB: [[25, 58]],
  WR: [[8, 18], [8, 82], [14, 30], [14, 70]],
  TE: [[11, 38], [11, 62]],
  LT: [[10, 44]],
  LG: [[10, 47]],
  C: [[10, 50]],
  RG: [[10, 53]],
  RT: [[10, 56]],
}

const DEF_POS: Record<string, [number, number][]> = {
  DE: [[12, 39], [12, 61]],
  EDGE: [[12, 36], [12, 64]],
  DT: [[10, 47], [10, 53]],
  NT: [[10, 50]],
  OLB: [[22, 35], [22, 65]],
  ILB: [[24, 46], [24, 54]],
  MLB: [[24, 50]],
  LB: [[23, 42], [23, 58]],
  CB: [[36, 18], [36, 82], [30, 30]],
  NB: [[31, 50]],
  FS: [[48, 42]],
  SS: [[48, 58]],
  S: [[48, 42], [48, 58]],
}

function pct(v: number | null | undefined) {
  if (v == null) return '—'
  return `${Math.round(v * 100)}%`
}

function ratingTone(rating: number | null | undefined) {
  if (rating == null) return 'border-gray-700 bg-gray-900 text-gray-500'
  if (rating >= 8.5) return 'border-amber-300 bg-amber-300 text-gray-950 shadow-[0_0_18px_rgba(252,211,77,.32)]'
  if (rating >= 7) return 'border-emerald-400 bg-emerald-400 text-gray-950'
  if (rating >= 5) return 'border-indigo-400 bg-indigo-400 text-gray-950'
  return 'border-rose-400 bg-rose-400 text-gray-950'
}

function displayName(player: LineupPlayer) {
  const parts = player.player_name.split(' ')
  return parts.length > 1 ? `${parts[0][0]}. ${parts.slice(1).join(' ')}` : player.player_name
}

function nextCoord(position: string | null | undefined, counts: Map<string, number>, unit: Unit): [number, number] {
  const pos = (position ?? '').toUpperCase()
  const key = pos || 'UNK'
  const i = counts.get(key) ?? 0
  counts.set(key, i + 1)
  const template = unit === 'offense' ? OFF_POS : DEF_POS
  const coords = template[pos] ?? [[20 + (i % 4) * 8, 28 + Math.floor(i / 4) * 14]]
  return coords[Math.min(i, coords.length - 1)]
}

function PlayerNode({
  player,
  teamSide,
  unit,
  counts,
  onSelect,
}: {
  player: LineupPlayer
  teamSide: 'left' | 'right'
  unit: Unit
  counts: Map<string, number>
  onSelect: (p: LineupPlayer) => void
}) {
  const [depth, lane] = nextCoord(player.position, counts, unit)
  const left = teamSide === 'left' ? depth : 100 - depth
  const top = lane
  return (
    <button
      type="button"
      onClick={() => onSelect(player)}
      className="absolute -translate-x-1/2 -translate-y-1/2 group text-left"
      style={{ left: `${left}%`, top: `${top}%` }}
      title={`${player.player_name} · ${player.position ?? '—'} · ${player.rating ?? 'unrated'}`}
    >
      <div className="flex flex-col items-center gap-1">
        <span className={`min-w-10 h-8 px-2 rounded border text-xs font-black tabular-nums flex items-center justify-center ${ratingTone(player.rating)}`}>
          {player.rating == null ? '—' : player.rating.toFixed(1)}{player.rating != null && player.rating >= 8.5 ? '✦' : ''}
        </span>
        <span className="max-w-24 truncate rounded bg-gray-950/85 px-1.5 py-0.5 text-[10px] font-bold text-gray-200 group-hover:text-white">
          {displayName(player)}
        </span>
        <span className="text-[9px] font-semibold uppercase tracking-wide text-gray-500">{player.position ?? '—'} · {pct(player.snap_pct)}</span>
      </div>
    </button>
  )
}

function FieldTeam({ team, unit, side, onSelect }: { team: LineupTeam; unit: Unit; side: 'left' | 'right'; onSelect: (p: LineupPlayer) => void }) {
  const players = unit === 'offense' ? team.offense : team.defense
  const counts = new Map<string, number>()
  return (
    <>
      {players.map((player) => (
        <PlayerNode key={`${team.team}-${unit}-${player.player_id ?? player.pfr_player_id}`} player={player} teamSide={side} unit={unit} counts={counts} onSelect={onSelect} />
      ))}
    </>
  )
}

function RotationList({ team }: { team: LineupTeam }) {
  if (!team.rotation.length) return null
  return (
    <div className="mt-4">
      <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">Rotation</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {team.rotation.slice(0, 6).map((p) => (
          <div key={`${team.team}-rot-${p.player_id ?? p.pfr_player_id}`} className="flex items-center gap-2 rounded border border-gray-800 bg-gray-900/70 px-2.5 py-2">
            <span className={`w-10 rounded border text-center text-[11px] font-black tabular-nums ${ratingTone(p.rating)}`}>{p.rating == null ? '—' : p.rating.toFixed(1)}</span>
            <div className="min-w-0">
              <div className="truncate text-xs font-bold text-gray-200">{p.player_name}</div>
              <div className="text-[10px] text-gray-500">{p.position ?? '—'} · {p.snaps} snaps</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function scoreGroups(scoring: LineupScoringEvent[]) {
  const groups = new Map<string, LineupScoringEvent[]>()
  for (const s of scoring) {
    const key = `${s.team}-${s.player_id ?? s.player_name}-${s.kind}`
    groups.set(key, [...(groups.get(key) ?? []), s])
  }
  return [...groups.values()]
}

function RightRail({ game, lineup }: { game: GameDetail; lineup: GameLineup }) {
  const top = lineup.teams
    .flatMap(t => [...t.offense, ...t.defense, ...t.rotation])
    .filter((p): p is LineupPlayer & { rating: number } => p.rating != null)
    .sort((a, b) => b.rating - a.rating)
    .slice(0, 5)

  return (
    <aside className="space-y-4">
      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
        <div className="border-b border-gray-800 px-4 py-3 text-xs font-bold uppercase tracking-widest text-gray-500">Highlights</div>
        <div className="divide-y divide-gray-800/60">
          {top.map(p => (
            <div key={`top-${p.player_id}`} className="flex items-center gap-3 px-4 py-3">
              <span className={`w-11 rounded border text-center text-xs font-black tabular-nums ${ratingTone(p.rating)}`}>{p.rating.toFixed(1)}</span>
              <div className="min-w-0">
                <div className="truncate text-sm font-bold text-gray-100">{p.player_name}</div>
                <div className="text-[11px] text-gray-500">{p.team} · {p.position ?? '—'} · {pct(p.snap_pct)}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
        <div className="border-b border-gray-800 px-4 py-3 text-xs font-bold uppercase tracking-widest text-gray-500">Scorers</div>
        <div className="divide-y divide-gray-800/60">
          {scoreGroups(lineup.scoring).slice(0, 8).map((events, i) => {
            const first = events[0]
            const distances = events.filter(e => e.kind === 'FG' && e.distance != null).map(e => e.distance).join(', ')
            return (
              <div key={`score-${i}`} className="flex items-center gap-3 px-4 py-3">
                {first.team && <img src={teamLogoUrl(first.team)} className="h-6 w-6 object-contain" alt="" />}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-bold text-gray-100">{first.player_name ?? first.team}</div>
                  <div className="text-[11px] text-gray-500">{first.kind}{distances ? ` · ${distances}` : ` · ${events.length}`}</div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900 px-4 py-3">
        <div className="text-xs font-bold uppercase tracking-widest text-gray-500">Venue</div>
        <div className="mt-2 text-sm font-semibold text-gray-200">{game.stadium ?? 'TBD'}</div>
        <div className="mt-1 text-xs text-gray-500">{[game.roof, game.surface, game.temp != null ? `${game.temp}°F` : null, game.wind != null ? `${game.wind} mph` : null].filter(Boolean).join(' · ')}</div>
      </div>
    </aside>
  )
}

function ChartPopup({ gameId, player, onClose }: { gameId: string; player: LineupPlayer | null; onClose: () => void }) {
  const [chart, setChart] = useState<PlayerChart | null>(null)

  useEffect(() => {
    if (!player?.player_id) return
    let cancelled = false
    api.playerChart(gameId, player.player_id).then(data => {
      if (!cancelled) setChart(data)
    })
    return () => { cancelled = true }
  }, [gameId, player?.player_id])

  if (!player) return null
  const events = chart?.events ?? []
  const statPairs = Object.entries(chart?.stats ?? {}).filter(([, v]) => Number(v) > 0).slice(0, 8)
  const loading = Boolean(player.player_id && !chart)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-xl border border-gray-700 bg-gray-950 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-4 border-b border-gray-800 px-5 py-4">
          <div className="min-w-0">
            <div className="truncate text-lg font-black text-white">{player.player_name}</div>
            <div className="text-xs text-gray-500">{player.position ?? '—'} · {player.team} · {pct(player.snap_pct)} of snaps</div>
          </div>
          <div className={`rounded border px-3 py-1 text-xl font-black tabular-nums ${ratingTone(player.rating)}`}>{player.rating == null ? '—' : player.rating.toFixed(1)}</div>
        </div>
        <div className="grid gap-4 p-5 md:grid-cols-[1fr_1.15fr]">
          <div>
            <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">{chart?.role ?? 'Game'} line</div>
            <div className="grid grid-cols-2 gap-2">
              {loading && <div className="col-span-2 text-sm text-gray-500">Loading chart…</div>}
              {!loading && statPairs.map(([k, v]) => (
                <div key={k} className="rounded border border-gray-800 bg-gray-900 px-3 py-2">
                  <div className="text-lg font-black tabular-nums text-white">{String(v)}</div>
                  <div className="text-[10px] uppercase tracking-wide text-gray-500">{k.replaceAll('_', ' ')}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">Play chart</div>
            <div className="relative h-56 overflow-hidden rounded-lg border border-gray-800 bg-[linear-gradient(90deg,#0f3f2b,#155c3c)]">
              <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full opacity-40">
                {[10, 20, 30, 40, 50, 60, 70, 80, 90].map(x => <line key={x} x1={x} x2={x} y1="0" y2="100" stroke="white" strokeWidth=".35" />)}
              </svg>
              {events.slice(0, 28).map((e, i) => {
                const lane = e.lane === 'left' ? 25 : e.lane === 'right' ? 75 : 50
                const x = Math.max(8, Math.min(92, 18 + (Number(e.yards ?? e.air_yards ?? 0) * 2.4)))
                return <span key={`${e.play_id}-${i}`} className={`absolute h-3 w-3 rounded-full border border-gray-950 ${e.outcome === 'TD' ? 'bg-amber-300' : e.outcome === 'INT' || e.outcome === 'FUM' ? 'bg-rose-400' : 'bg-sky-300'}`} style={{ left: `${x}%`, top: `${lane}%` }} title={`${e.outcome} · ${e.yards ?? 0} yards`} />
              })}
            </div>
            <div className="mt-2 max-h-28 overflow-y-auto divide-y divide-gray-800/60">
              {events.slice(0, 6).map((e, i) => (
                <div key={`event-${i}`} className="flex gap-2 py-1.5 text-[11px]">
                  <span className="w-12 shrink-0 font-mono text-gray-500">Q{e.qtr} {e.clock}</span>
                  <span className="shrink-0 font-bold text-gray-300">{e.outcome}</span>
                  <span className="line-clamp-1 text-gray-500">{e.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <button type="button" onClick={onClose} className="absolute right-5 top-4 text-gray-500 hover:text-white" aria-label="Close">×</button>
      </div>
    </div>
  )
}

export default function GameLineupView({ game }: { game: GameDetail }) {
  const [lineup, setLineup] = useState<GameLineup | null>(null)
  const [unit, setUnit] = useState<Unit>('offense')
  const [infoOpen, setInfoOpen] = useState(false)
  const [selected, setSelected] = useState<LineupPlayer | null>(null)

  useEffect(() => {
    api.gameLineup(game.game_id).then(setLineup)
  }, [game.game_id])

  const away = useMemo(() => lineup?.teams.find(t => t.team === game.away_team), [lineup, game.away_team])
  const home = useMemo(() => lineup?.teams.find(t => t.team === game.home_team), [lineup, game.home_team])

  if (!lineup || !away || !home) {
    return <div className="rounded-xl border border-gray-800 bg-gray-900 p-6 text-sm text-gray-500">Loading lineup…</div>
  }

  return (
    <>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <img src={teamLogoUrl(game.away_team)} className="h-8 w-8 object-contain" alt="" />
              <div className="min-w-0">
                <div className="truncate text-sm font-black text-white">{teamName(game.away_team)} vs {teamName(game.home_team)}</div>
                <div className="text-[11px] text-gray-500">{away.offense_personnel} · {home.defense_personnel}</div>
              </div>
              <img src={teamLogoUrl(game.home_team)} className="h-8 w-8 object-contain" alt="" />
            </div>
            <div className="flex items-center gap-2">
              <div className="rounded-lg border border-gray-800 bg-gray-950 p-1">
                {(['offense', 'defense'] as const).map(v => (
                  <button key={v} type="button" onClick={() => setUnit(v)} className={`rounded-md px-3 py-1.5 text-xs font-bold capitalize ${unit === v ? 'bg-indigo-500 text-white' : 'text-gray-500 hover:text-gray-200'}`}>{v}</button>
                ))}
              </div>
              <button type="button" onClick={() => setInfoOpen(v => !v)} className="relative h-8 w-8 rounded-lg border border-gray-800 text-xs font-black text-gray-400 hover:text-white">
                i
                {infoOpen && (
                  <div className="absolute right-0 top-10 z-20 w-72 rounded-lg border border-gray-700 bg-gray-950 p-3 text-left text-xs font-normal leading-relaxed text-gray-400 shadow-xl">
                    Game ratings use a 3.0–10.0 scale from play-by-play EPA and defensive events, calibrated by position group. 6.5 is average; 9.0+ is a top performance. Linemen are shown from snap counts but are unrated.
                  </div>
                )}
              </button>
            </div>
          </div>

          <div className="relative aspect-[16/9] min-h-[440px] overflow-hidden bg-[#12412d]">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
              <rect width="100" height="100" fill="#12412d" />
              <rect x="48.5" y="0" width="3" height="100" fill="#f8fafc" opacity=".18" />
              {[10, 20, 30, 40, 60, 70, 80, 90].map(x => <line key={x} x1={x} x2={x} y1="0" y2="100" stroke="#ffffff" strokeOpacity=".22" strokeWidth=".35" />)}
              <line x1="50" x2="50" y1="0" y2="100" stroke="#ffffff" strokeOpacity=".35" strokeWidth=".45" />
              <rect x="0" y="0" width="5" height="100" fill="#0f2f23" opacity=".75" />
              <rect x="95" y="0" width="5" height="100" fill="#0f2f23" opacity=".75" />
            </svg>
            <div className="absolute left-4 top-4 flex items-center gap-2 rounded bg-gray-950/80 px-3 py-2">
              <img src={teamLogoUrl(away.team)} className="h-6 w-6 object-contain" alt="" />
              <span className="text-xs font-black text-white">{away.team}</span>
              <span className="text-[11px] text-gray-500">{away.avg_rating ?? '—'} avg</span>
            </div>
            <div className="absolute right-4 top-4 flex items-center gap-2 rounded bg-gray-950/80 px-3 py-2">
              <span className="text-[11px] text-gray-500">{home.avg_rating ?? '—'} avg</span>
              <span className="text-xs font-black text-white">{home.team}</span>
              <img src={teamLogoUrl(home.team)} className="h-6 w-6 object-contain" alt="" />
            </div>
            <FieldTeam team={away} unit={unit} side="left" onSelect={setSelected} />
            <FieldTeam team={home} unit={unit} side="right" onSelect={setSelected} />
          </div>

          <div className="grid gap-4 border-t border-gray-800 p-4 md:grid-cols-2">
            <RotationList team={away} />
            <RotationList team={home} />
          </div>
          <div className="flex flex-wrap gap-3 border-t border-gray-800 px-4 py-3 text-[11px] text-gray-500">
            <span className="font-semibold text-gray-400">Legend</span>
            <span>&lt;5.0</span><span>5.0–6.9</span><span>7.0+</span><span>✦ 8.5+</span>
          </div>
        </section>
        <RightRail game={game} lineup={lineup} />
      </div>
      <ChartPopup key={selected?.player_id ?? 'none'} gameId={game.game_id} player={selected} onClose={() => setSelected(null)} />
    </>
  )
}
