/**
 * Splits explorer — compare players/teams and explore every split at once.
 *
 * Top: a head-to-head summary table (entities as rows) with situation chips to
 * compare on a slice. Below: ALL the splits for a focused entity shown at once
 * as stacked, sortable sections you can toggle on/off — Season (per-season,
 * each expandable to its game log), Down, Quarter, Game Script, Pass Depth,
 * Opponent (+ Def Rk), etc.
 *
 * Backed by player_splits / team_splits, the player profile (per-game), and
 * team_season_analytics (opponent defensive ranks).
 */
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { PlayerSplit, TeamSplit, SearchResult } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'
import {
  PLAYER_SPLIT_CONFIG, TEAM_SPLIT_CONFIG, PLAYER_SITUATIONS, TEAM_SITUATIONS,
  type PlayerCategory, type TeamSide, type Metric, type Situation,
  splitValueLabel, aggregateCareerByValue, aggregatePlayerSplitRows,
  aggregateTeamSplitRows, gameToSplitRow, CAREER_SEASON, OVERALL_DIM,
} from '../splits'

type Mode = 'players' | 'teams'
type PlayerEntity = { id: string; name: string; headshot?: string | null; sub?: string }
type Row = PlayerSplit | TeamSplit
type EntityCard = { key: string; label: string; sub?: string; headshot?: string | null; logo?: string; color: string }
type Sort = { key: string; dir: 'asc' | 'desc' }
type TRow = { key: string; label: React.ReactNode; row: Row | null; defRk?: number | null; sub?: boolean }

const SEASONS = Array.from({ length: CURRENT_NFL_SEASON - 1998 }, (_, i) => CURRENT_NFL_SEASON - i)
const ENTITY_COLORS = ['99,102,241', '20,184,166', '245,158,11', '56,189,248', '244,63,94', '168,85,247']
const colorOf = (i: number) => ENTITY_COLORS[i % ENTITY_COLORS.length]

// Curated "key stats" per category/side — keeps the side-by-side narrow.
const KEY_KEYS: Record<string, string[]> = {
  passing: ['ya', 'td', 'int', 'conv', 'epa', 'succ'],
  rushing: ['ypc', 'td', 'conv', 'epa', 'succ'],
  receiving: ['ypr', 'td', 'conv', 'epa', 'succ'],
  offense: ['epa', 'succ', 'ypp', 'expl'],
  defense: ['epa', 'succ', 'ypp', 'expl'],
}
// Game-based sections (Season / Opponent) read like a box score, so their
// key columns lead with total yards and the headline rate (passer rating).
const GAME_KEY_KEYS: Record<string, string[]> = {
  passing: ['yds', 'td', 'int', 'rate', 'epa'],
  rushing: ['yds', 'td', 'ypc', 'epa'],
  receiving: ['rec', 'yds', 'td', 'ypr', 'epa'],
}
const selectCls = 'bg-gray-900 border border-gray-800 text-gray-200 text-xs rounded-lg px-2.5 py-2 focus:outline-none focus:border-gray-600'

function Seg<T extends string | number>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex items-center gap-0.5 bg-gray-900 border border-gray-800 rounded-lg p-0.5 flex-wrap">
      {options.map(o => (
        <button key={String(o.value)} onClick={() => onChange(o.value)}
          className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${value === o.value ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}>{o.label}</button>
      ))}
    </div>
  )
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors ${active ? 'bg-indigo-600 border-indigo-500 text-white' : 'bg-gray-900 border-gray-800 text-gray-400 hover:text-white hover:border-gray-700'}`}>{children}</button>
  )
}

function AddEntity({ mode, onAdd }: { mode: Mode; onAdd: (r: SearchResult) => void }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current)
    const trimmed = q.trim()
    if (!trimmed) { setResults([]); return }
    let cancelled = false
    debounce.current = setTimeout(async () => {
      try { const res = await api.search(trimmed); if (!cancelled) setResults(res.filter(r => mode === 'players' ? r.type === 'player' : r.type === 'team')) }
      catch { if (!cancelled) setResults([]) }
    }, 250)
    return () => { cancelled = true }
  }, [q, mode])
  return (
    <div className="relative">
      <input value={q} onChange={e => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={mode === 'players' ? '+ Add player…' : '+ Add team…'}
        className="bg-gray-900 border border-gray-800 text-gray-200 text-sm rounded-lg px-3 py-2 w-52 focus:outline-none focus:border-gray-600 placeholder-gray-600" />
      {open && q.trim() && results.length > 0 && (
        <div className="absolute z-30 mt-1 w-64 max-h-72 overflow-y-auto bg-gray-900 border border-gray-700 rounded-lg shadow-2xl">
          {results.slice(0, 12).map(r => (
            <button key={r.id} onMouseDown={() => { onAdd(r); setQ(''); setResults([]) }} className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-gray-800 text-left">
              {r.type === 'team' ? <img src={teamLogoUrl(r.id)} className="w-6 h-6 object-contain shrink-0" alt="" />
                : r.headshot_url ? <img src={r.headshot_url} className="w-6 h-6 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" /> : <div className="w-6 h-6 rounded-full bg-gray-800 shrink-0" />}
              <div className="min-w-0">
                <div className="text-sm font-semibold text-white truncate">{r.type === 'team' ? teamName(r.id) : r.name}</div>
                <div className="text-xs text-gray-500 truncate">{r.type === 'team' ? r.id : [r.position, r.team].filter(Boolean).join(' · ')}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function MatchupHeader({ entities, onRemove }: { entities: EntityCard[]; onRemove: (key: string) => void }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2 mb-5">
      {entities.map((e, i) => (
        <div key={e.key} className="group relative flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-xl pl-3 pr-8 py-2.5 min-w-[150px]" style={{ boxShadow: `inset 0 2px 0 0 rgba(${e.color},0.9)` }}>
          {e.logo ? <img src={e.logo} className="w-10 h-10 object-contain shrink-0" alt="" />
            : e.headshot ? <img src={e.headshot} className="w-10 h-10 rounded-full object-cover object-top bg-gray-800 shrink-0" style={{ boxShadow: `0 0 0 2px rgba(${e.color},0.55)` }} alt="" /> : <div className="w-10 h-10 rounded-full bg-gray-800 shrink-0" />}
          <div className="min-w-0">
            <div className="text-sm font-bold text-white truncate leading-tight">{e.label}</div>
            {e.sub && <div className="text-[11px] text-gray-500 truncate">{e.sub}</div>}
          </div>
          <button onClick={() => onRemove(e.key)} className="absolute top-1.5 right-1.5 w-5 h-5 flex items-center justify-center rounded text-gray-600 hover:text-red-400 hover:bg-gray-800">×</button>
          {i < entities.length - 1 && entities.length === 2 && <span className="absolute -right-3 top-1/2 -translate-y-1/2 z-10 text-[10px] font-black text-gray-600">VS</span>}
        </div>
      ))}
    </div>
  )
}

function bestSet(values: (number | null)[], higherIsBetter: boolean | undefined): Set<number> {
  if (higherIsBetter === undefined) return new Set()
  const present = values.map((v, i) => [v, i] as const).filter(([v]) => v != null) as [number, number][]
  if (present.length < 2) return new Set()
  const best = present.reduce((m, [v]) => higherIsBetter ? Math.max(m, v) : Math.min(m, v), present[0][0])
  if (present.every(([v]) => v === best)) return new Set()
  return new Set(present.filter(([v]) => v === best).map(([, i]) => i))
}

const volume = (r: Row | null) => ((r as PlayerSplit)?.att ?? (r as TeamSplit)?.plays) ?? 0

// A sortable table: rows (entities or split values) × metric columns.
function StatTable({ firstCol, rows, total, metrics, flip, hasDefRk, defaultSort, naturalSort, onToggleExpand }: {
  firstCol: string
  rows: TRow[]
  total?: Row | null
  metrics: Metric<Row>[]
  flip: (hib: boolean | undefined) => boolean | undefined
  hasDefRk?: boolean
  defaultSort?: Sort | null
  naturalSort?: boolean
  onToggleExpand?: (key: string) => void
}) {
  const [sort, setSort] = useState<Sort | null>(defaultSort ?? null)
  const metricByKey = useMemo(() => Object.fromEntries(metrics.map(m => [m.key, m])), [metrics])

  const sorted = useMemo(() => {
    const arr = [...rows]
    if (sort) {
      const val = (r: TRow): number | null => sort.key === '__defrk' ? (r.defRk ?? null) : (r.row ? metricByKey[sort.key]?.value(r.row) ?? null : null)
      arr.sort((a, b) => {
        const av = val(a), bv = val(b)
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        return sort.dir === 'asc' ? av - bv : bv - av
      })
    } else if (naturalSort) {
      arr.sort((a, b) => ((a.row?.sort_order ?? 9999) - (b.row?.sort_order ?? 9999)) || (volume(b.row) - volume(a.row)))
    }
    return arr
  }, [rows, sort, naturalSort, metricByKey])

  const colBest = useMemo(() => {
    const m = new Map<string, Set<number>>()
    const visible = sorted.filter(r => !r.sub)
    for (const met of metrics) m.set(met.key, bestSet(visible.map(r => r.row ? met.value(r.row) : null), flip(met.higherIsBetter)))
    return m
  }, [sorted, metrics, flip])

  const clickSort = (key: string, dDir: 'asc' | 'desc' = 'desc') => setSort(s => s && s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: dDir })
  const arrow = (key: string) => sort?.key === key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''
  const visibleRows = sorted.filter(r => !r.sub)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b-2 border-gray-800">
            <th className="py-2 pl-4 pr-3 text-[11px] font-bold text-gray-400 uppercase tracking-wider text-left whitespace-nowrap">{firstCol}</th>
            {hasDefRk && <th onClick={() => clickSort('__defrk', 'asc')} className="py-2 px-3 text-[11px] font-bold text-amber-500/70 uppercase tracking-wider text-left whitespace-nowrap cursor-pointer hover:text-amber-300 select-none">Def Rk{arrow('__defrk')}</th>}
            {metrics.map(m => (
              <th key={m.key} onClick={() => clickSort(m.key)} className="py-2 px-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider text-left whitespace-nowrap cursor-pointer hover:text-white select-none">{m.label}{arrow(m.key)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(r => (
            <tr key={r.key} className={`border-t border-gray-800/50 hover:bg-gray-800/30 ${r.sub ? 'bg-gray-950/40' : ''}`}>
              <td className={`py-2 pr-3 whitespace-nowrap ${r.sub ? 'pl-9 text-gray-400 text-xs' : 'pl-4 font-semibold text-white'}`}>
                <span className="inline-flex items-center gap-1.5">
                  {onToggleExpand && !r.sub && (
                    <button onClick={() => onToggleExpand(r.key)} className="text-gray-600 hover:text-white w-3">▸</button>
                  )}
                  {r.label}
                </span>
              </td>
              {hasDefRk && <td className="py-2 px-3 whitespace-nowrap tabular-nums text-amber-200/80 text-xs">{r.defRk != null ? `#${r.defRk}` : '—'}</td>}
              {metrics.map(m => {
                const v = r.row ? m.value(r.row) : null
                const isBest = !r.sub && colBest.get(m.key)?.has(visibleRows.indexOf(r))
                return (
                  <td key={m.key} className={`py-2 px-3 whitespace-nowrap tabular-nums ${v == null ? 'text-gray-700' : isBest ? 'text-emerald-300 font-bold bg-emerald-500/15' : r.sub ? 'text-gray-400' : 'text-gray-200'}`}>
                    {v == null ? '—' : m.fmt(v)}
                  </td>
                )
              })}
            </tr>
          ))}
          {total && (
            <tr className="border-t-2 border-gray-700 bg-gray-800/50">
              <td className="py-2 pl-4 pr-3 whitespace-nowrap text-xs font-bold text-gray-300 uppercase tracking-wider">Total</td>
              {hasDefRk && <td />}
              {metrics.map(m => {
                const v = m.value(total)
                return <td key={m.key} className={`py-2 px-3 whitespace-nowrap tabular-nums font-bold ${v == null ? 'text-gray-700' : 'text-gray-200'}`}>{v == null ? '—' : m.fmt(v)}</td>
              })}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function Section({ title, children, open, onToggle }: { title: string; children: React.ReactNode; open: boolean; onToggle: () => void }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <button onClick={onToggle} className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-gray-800/40">
        <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">{title}</span>
        <span className="text-gray-600 text-xs">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="border-t border-gray-800">{children}</div>}
    </div>
  )
}

type GameLite = { game_id: string; season: number; week: number; location: string; opponent: string }
type EntitySecLite = { map: Map<string, Row>; total: Row | null; groups?: Map<string, { g: GameLite; r: Row }[]> }

// Side-by-side: rows = split values, columns grouped by entity (each entity's
// metrics). Sticky label column; best per metric across entities tinted.
function GroupedTable({ label, entities, metrics, keys, keyLabel, sections, defRkFor, expandable, expandShowSeason, expandedKeys, onToggleExpand, flip }: {
  label: string
  entities: EntityCard[]
  metrics: Metric<Row>[]
  keys: string[]
  keyLabel: (k: string) => React.ReactNode
  sections: EntitySecLite[]
  defRkFor?: (k: string) => number | null | undefined
  expandable?: boolean
  expandShowSeason?: boolean
  expandedKeys: Set<string>
  onToggleExpand?: (k: string) => void
  flip: (hib: boolean | undefined) => boolean | undefined
}) {
  const sticky = 'sticky left-0 z-10 bg-gray-900'
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm border-separate" style={{ borderSpacing: 0 }}>
        <thead>
          <tr>
            <th rowSpan={2} className={`${sticky} py-2 pl-4 pr-3 text-[11px] font-bold text-gray-400 uppercase tracking-wider text-left whitespace-nowrap border-b-2 border-gray-800`}>{label}</th>
            {entities.map(e => (
              <th key={e.key} colSpan={metrics.length} className="py-1.5 px-3 text-left whitespace-nowrap border-b border-l border-gray-800" style={{ color: `rgb(${e.color})` }}>
                <span className="inline-flex items-center gap-1.5 text-xs font-bold">
                  {e.headshot ? <img src={e.headshot} className="w-5 h-5 rounded-full object-cover object-top bg-gray-800" alt="" /> : e.logo ? <img src={e.logo} className="w-5 h-5 object-contain" alt="" /> : null}
                  {e.label}
                </span>
              </th>
            ))}
          </tr>
          <tr>
            {entities.map(e => metrics.map((m, mi) => (
              <th key={e.key + m.key} className={`py-1.5 px-3 text-[10px] font-semibold text-gray-500 uppercase tracking-wider text-left whitespace-nowrap border-b-2 border-gray-800 ${mi === 0 ? 'border-l border-gray-800' : ''}`}>{m.label}</th>
            )))}
          </tr>
        </thead>
        <tbody>
          {keys.map(k => {
            const dr = defRkFor?.(k)
            const bestByMetric = metrics.map(m => bestSet(sections.map(s => { const r = s.map.get(k); return r ? m.value(r) : null }), flip(m.higherIsBetter)))
            return (
              <Fragment key={k}>
                <tr className="hover:bg-gray-800/20">
                  <td className={`${sticky} py-2 pl-4 pr-3 whitespace-nowrap font-semibold text-white border-t border-gray-800/50`}>
                    <span className="inline-flex items-center gap-1.5">
                      {expandable && onToggleExpand && <button onClick={() => onToggleExpand(k)} className="text-gray-600 hover:text-white w-3">{expandedKeys.has(k) ? '▾' : '▸'}</button>}
                      {keyLabel(k)}
                      {dr != null && <span className="text-amber-500/70 text-[10px] font-bold">#{dr}</span>}
                    </span>
                  </td>
                  {sections.map((s, si) => {
                    const r = s.map.get(k)
                    return metrics.map((m, mi) => {
                      const v = r ? m.value(r) : null
                      return <td key={si + m.key} className={`py-2 px-3 whitespace-nowrap tabular-nums border-t border-gray-800/50 ${mi === 0 ? 'border-l border-gray-800/50' : ''} ${v == null ? 'text-gray-700' : bestByMetric[mi].has(si) ? 'text-emerald-300 font-bold bg-emerald-500/15' : 'text-gray-200'}`}>{v == null ? '—' : m.fmt(v)}</td>
                    })
                  })}
                </tr>
                {expandable && expandedKeys.has(k) && (() => {
                  // One row per game, aligned across entities by season+week so the
                  // same game lines up; each entity's stats fill its own columns
                  // (with a link to the game page). Season rows hide the year.
                  const rowMaps = sections.map(s => {
                    const mm = new Map<number, { g: GameLite; r: Row }>()
                    for (const x of (s.groups?.get(k) ?? [])) mm.set(x.g.season * 100 + x.g.week, x)
                    return mm
                  })
                  const gks = [...new Set(rowMaps.flatMap(mm => [...mm.keys()]))].sort((a, b) => a - b)
                  return gks.map(gk => (
                    <tr key={`g-${gk}`} className="bg-gray-950/40">
                      <td className={`${sticky} bg-gray-950 py-1.5 pl-9 pr-3 whitespace-nowrap text-xs text-gray-500 border-t border-gray-800/40`}>{expandShowSeason ? `${Math.floor(gk / 100)} Wk ${gk % 100}` : `Wk ${gk % 100}`}</td>
                      {sections.map((_, si) => {
                        const x = rowMaps[si].get(gk)
                        return metrics.map((m, mi) => {
                          const v = x ? m.value(x.r) : null
                          return (
                            <td key={si + m.key} className={`py-1.5 px-3 whitespace-nowrap tabular-nums text-xs border-t border-gray-800/40 ${mi === 0 ? 'border-l border-gray-800/50' : ''} ${v == null ? 'text-gray-800' : 'text-gray-400'}`}>
                              {mi === 0 && x ? (
                                <div className="flex flex-col leading-tight">
                                  <span>{v == null ? '—' : m.fmt(v)}</span>
                                  <Link to={`/games/${x.g.game_id}`} className="text-[10px] text-indigo-400/70 hover:text-indigo-300">{x.g.location === 'home' ? 'vs ' : '@ '}{x.g.opponent}</Link>
                                </div>
                              ) : (v == null ? '' : m.fmt(v))}
                            </td>
                          )
                        })
                      })}
                    </tr>
                  ))
                })()}
              </Fragment>
            )
          })}
          <tr>
            <td className={`${sticky} bg-gray-800 py-2 pl-4 pr-3 whitespace-nowrap text-xs font-bold text-gray-300 uppercase tracking-wider border-t-2 border-gray-700`}>Total</td>
            {sections.map((s, si) => metrics.map((m, mi) => {
              const v = s.total ? m.value(s.total) : null
              return <td key={si + m.key} className={`py-2 px-3 whitespace-nowrap tabular-nums font-bold bg-gray-800/40 border-t-2 border-gray-700 ${mi === 0 ? 'border-l border-gray-800/50' : ''} ${v == null ? 'text-gray-700' : 'text-gray-200'}`}>{v == null ? '—' : m.fmt(v)}</td>
            }))}
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export default function SplitsPage() {
  // Initial state is hydrated from the URL so any comparison is shareable.
  const [, setSearchParams] = useSearchParams()
  const init = useRef(new URLSearchParams(window.location.search)).current
  const initMode: Mode = init.get('mode') === 'teams' ? 'teams' : 'players'
  const initCat: PlayerCategory = (['passing', 'rushing', 'receiving'] as string[]).includes(init.get('cat') ?? '') ? init.get('cat') as PlayerCategory : 'passing'

  const [mode, setMode] = useState<Mode>(initMode)
  const [players, setPlayers] = useState<PlayerEntity[]>(() => {
    const ids = init.get('p'); return ids ? ids.split(',').filter(Boolean).slice(0, 6).map(id => ({ id, name: '' })) : []
  })
  const [teams, setTeams] = useState<string[]>(() => {
    const t = init.get('t'); return t ? t.split(',').filter(Boolean).slice(0, 6) : []
  })
  const [pCat, setPCat] = useState<PlayerCategory>(initCat)
  const [tSide, setTSide] = useState<TeamSide>(init.get('side') === 'defense' ? 'defense' : 'offense')
  const [season, setSeason] = useState<number>(() => {
    const s = init.get('season'); const n = s == null ? CAREER_SEASON : Number(s); return Number.isFinite(n) ? n : CAREER_SEASON
  })
  const [situation, setSituation] = useState<Situation | null>(() => {
    const sit = init.get('sit'); if (!sit) return null
    const [dim, value] = sit.split(':')
    const list = initMode === 'teams' ? TEAM_SITUATIONS : PLAYER_SITUATIONS[initCat]
    return list.find(s => s.dim === dim && s.value === value) ?? null
  })
  const [hidden, setHidden] = useState<Set<string>>(new Set())  // hidden section keys
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const [keyStatsOnly, setKeyStatsOnly] = useState(true)  // side-by-side metric focus
  const [copied, setCopied] = useState(false)

  // Reflect the live comparison back into the URL (replace, so it doesn't
  // stack history) — the Copy-link button just grabs window.location.href.
  useEffect(() => {
    const p = new URLSearchParams()
    p.set('mode', mode)
    if (mode === 'players') { if (players.length) p.set('p', players.map(x => x.id).join(',')); p.set('cat', pCat) }
    else { if (teams.length) p.set('t', teams.join(',')); p.set('side', tSide) }
    p.set('season', String(season))
    if (situation) p.set('sit', `${situation.dim}:${situation.value}`)
    setSearchParams(p, { replace: true })
  }, [mode, players, teams, pCat, tSide, season, situation, setSearchParams])

  const playerResults = useQueries({ queries: players.map(p => ({ queryKey: ['player-splits', p.id] as const, queryFn: () => api.splits(p.id), staleTime: Infinity })) })
  const teamResults = useQueries({ queries: teams.map(t => ({ queryKey: ['team-splits', t, season] as const, queryFn: () => api.teamSplits(t, season), staleTime: Infinity })) })

  const config = mode === 'players' ? PLAYER_SPLIT_CONFIG[pCat] : TEAM_SPLIT_CONFIG[tSide]
  const metrics = config.metrics as Metric<Row>[]
  const catOrSide = mode === 'players' ? pCat : tSide
  const situations: Situation[] = mode === 'players' ? PLAYER_SITUATIONS[pCat] : TEAM_SITUATIONS
  const isCareer = mode === 'players' && season === CAREER_SEASON
  const flip = (hib: boolean | undefined) => (mode === 'teams' && tSide === 'defense' && hib !== undefined) ? !hib : hib

  const entityData: Row[][] = mode === 'players' ? players.map((_, i) => (playerResults[i]?.data ?? []) as PlayerSplit[]) : teams.map((_, i) => (teamResults[i]?.data ?? []) as TeamSplit[])

  // Each player's official game log — source for Season/Opponent sections and
  // per-game drill-downs, so their totals match the game log exactly. Also
  // backfills name/headshot/sub for players that arrived via a shared URL (id only).
  const playerProfiles = useQueries({ queries: players.map(p => ({ queryKey: ['player', p.id] as const, queryFn: () => api.player(p.id), staleTime: Infinity })) })
  const entityMeta: EntityCard[] = mode === 'players'
    ? players.map((p, i) => { const prof = playerProfiles[i]?.data; return { key: p.id, label: p.name || prof?.player_name || p.id, sub: p.sub || (prof ? [prof.position, prof.team].filter(Boolean).join(' · ') : undefined), headshot: p.headshot ?? prof?.headshot_url, color: colorOf(i) } })
    : teams.map((t, i) => ({ key: t, label: teamName(t), sub: t, logo: teamLogoUrl(t), color: colorOf(i) }))
  const entityCount = entityMeta.length
  const focusData = entityData[0] ?? []
  const playerGames = useMemo(() => mode === 'players'
    ? players.map((_, i) => (playerProfiles[i]?.data?.games ?? [])
        .filter(g => g.game_type === 'REG' && (isCareer || g.season === season))
        .map(g => ({ g, r: gameToSplitRow(g, pCat) }))
        .filter(x => (x.r.att ?? 0) > 0))
    : [], [playerProfiles, players, mode, pCat, season, isCareer])
  const games = playerGames[0] ?? []
  const gameMetrics = useMemo(() => metrics.filter(m => m.key !== 'succ' && m.key !== 'cpoe'), [metrics])
  const single = entityCount === 1

  // Opponent defensive ranks for the season.
  const wantDef = mode === 'players' && !isCareer
  const analytics = useQuery({ queryKey: ['team-analytics', season] as const, queryFn: () => api.teamAnalytics(season), enabled: wantDef, staleTime: Infinity })
  const defRank = useMemo(() => { const m = new Map<string, number>(); for (const t of analytics.data?.league ?? []) if (t.def_epa_play_rank != null) m.set(t.team, t.def_epa_play_rank); return m }, [analytics.data])

  // Summary row per entity (Overall, or the active situation).
  function situationRow(data: Row[]): Row | null {
    if (mode === 'players') {
      const rows = data as PlayerSplit[]
      const dimKey = situation ? situation.dim : OVERALL_DIM
      let sel = rows.filter(s => s.category === pCat && s.split_dim === dimKey)
      if (situation) sel = sel.filter(s => s.split_value === situation.value)
      if (isCareer) return aggregatePlayerSplitRows(sel)
      sel = sel.filter(s => s.season === season)
      return situation ? (sel[0] ?? null) : aggregatePlayerSplitRows(sel)
    }
    const rows = data as TeamSplit[]
    const dimKey = situation ? situation.dim : OVERALL_DIM
    let sel = rows.filter(s => s.side === tSide && s.split_dim === dimKey)
    if (situation) sel = sel.filter(s => s.split_value === situation.value)
    return situation ? (sel[0] ?? null) : aggregateTeamSplitRows(sel)
  }

  const summaryRows: TRow[] = entityMeta.map((meta, i) => ({
    key: meta.key,
    label: <span className="inline-flex items-center gap-2"><span className="w-2 h-2 rounded-full" style={{ backgroundColor: `rgb(${meta.color})` }} />{meta.headshot ? <img src={meta.headshot} className="w-6 h-6 rounded-full object-cover object-top bg-gray-800" alt="" /> : meta.logo ? <img src={meta.logo} className="w-6 h-6 object-contain" alt="" /> : null}{meta.label}</span>,
    row: situationRow(entityData[i]),
  }))

  // Section dimensions (for the focused entity). Season first (players only).
  const sectionDims = mode === 'players' ? [{ key: 'season', label: 'Season' }, ...config.dims] : config.dims
  const DEFAULT_OPEN = mode === 'players' ? ['season', 'down', 'game_script', 'opponent'] : ['down', 'game_script', 'field_zone']

  // Season & Opponent come from the official game log (so the Total = sum of
  // the games shown, and each game links to its page). All other dims come
  // from the play-by-play splits (modeled stats incl. success%/cpoe).
  const GAME_DIMS = new Set(mode === 'players' ? ['season', 'opponent'] : [])

  function sectionData(dim: string): { rows: TRow[]; total: Row | null } {
    if (GAME_DIMS.has(dim)) {
      const groups = new Map<string, typeof games>()
      for (const x of games) {
        const k = dim === 'season' ? String(x.g.season) : x.g.opponent
        ;(groups.get(k) ?? groups.set(k, []).get(k)!).push(x)
      }
      const keys = [...groups.keys()]
      if (dim === 'season') keys.sort((a, b) => Number(b) - Number(a))
      else keys.sort((a, b) => (groups.get(b)!.length - groups.get(a)!.length) || a.localeCompare(b))
      const out: TRow[] = []
      for (const k of keys) {
        const grp = groups.get(k)!
        const pkey = `${dim}:${k}`
        const gp = <span className="text-gray-500 text-[11px] font-normal ml-1.5">· {grp.length} G</span>
        out.push({
          key: pkey, row: aggregatePlayerSplitRows(grp.map(x => x.r)),
          defRk: dim === 'opponent' && wantDef ? (defRank.get(k) ?? null) : undefined,
          label: dim === 'season'
            ? <span className="font-bold">{k}{gp}</span>
            : <span className="inline-flex items-center gap-1.5"><img src={teamLogoUrl(k)} className="w-5 h-5 object-contain" alt="" />{k}{gp}</span>,
        })
        if (expandedKeys.has(pkey)) {
          for (const { g, r } of [...grp].sort((a, b) => a.g.season - b.g.season || a.g.week - b.g.week)) {
            out.push({
              key: `g:${g.game_id}`, sub: true, row: r,
              label: <Link to={`/games/${g.game_id}`} className="text-indigo-300 hover:text-indigo-200">{g.season} Wk {g.week} {g.location === 'home' ? 'vs' : '@'} {g.opponent} →</Link>,
            })
          }
        }
      }
      return { rows: out, total: aggregatePlayerSplitRows(games.map(x => x.r)) }
    }

    let rows: Row[]
    if (mode === 'players') {
      let r = (focusData as PlayerSplit[]).filter(s => s.category === pCat && s.split_dim === dim)
      if (isCareer) r = aggregateCareerByValue(r); else r = r.filter(s => s.season === season)
      rows = r
    } else {
      rows = (focusData as TeamSplit[]).filter(s => s.side === tSide && s.split_dim === dim)
    }
    const trows: TRow[] = rows.map(r => ({ key: r.split_value, label: splitValueLabel(dim, r.split_value), row: r }))
    const total = mode === 'players' ? aggregatePlayerSplitRows(rows as PlayerSplit[]) : aggregateTeamSplitRows(rows as TeamSplit[])
    return { rows: trows, total }
  }

  // Per-entity section data for the side-by-side view: value→row map + total,
  // and for game-based dims the per-key game lists (for per-game expansion).
  type EntitySec = { map: Map<string, Row>; total: Row | null; groups?: Map<string, typeof games> }
  function entitySection(idx: number, dim: string): EntitySec {
    if (GAME_DIMS.has(dim)) {
      const gs = playerGames[idx] ?? []
      const groups = new Map<string, typeof games>()
      for (const x of gs) {
        const k = dim === 'season' ? String(x.g.season) : x.g.opponent
        ;(groups.get(k) ?? groups.set(k, []).get(k)!).push(x)
      }
      const map = new Map<string, Row>()
      for (const [k, grp] of groups) { const agg = aggregatePlayerSplitRows(grp.map(x => x.r)); if (agg) map.set(k, agg) }
      return { map, total: aggregatePlayerSplitRows(gs.map(x => x.r)), groups }
    }
    let rows: Row[]
    if (mode === 'players') {
      let r = (entityData[idx] as PlayerSplit[]).filter(s => s.category === pCat && s.split_dim === dim)
      if (isCareer) r = aggregateCareerByValue(r); else r = r.filter(s => s.season === season)
      rows = r
    } else {
      rows = (entityData[idx] as TeamSplit[]).filter(s => s.side === tSide && s.split_dim === dim)
    }
    const map = new Map<string, Row>(rows.map(r => [r.split_value, r]))
    const total = mode === 'players' ? aggregatePlayerSplitRows(rows as PlayerSplit[]) : aggregateTeamSplitRows(rows as TeamSplit[])
    return { map, total }
  }

  // "Where they stand out" — for a single focused player, the situational
  // splits whose headline efficiency (Y/A · Y/C · Y/R) deviates most from their
  // overall average. Pure client computation over the data already loaded.
  const notable = (() => {
    if (!single || mode !== 'players') return null
    const headlineKey = pCat === 'passing' ? 'ya' : pCat === 'rushing' ? 'ypc' : 'ypr'
    const unit = pCat === 'passing' ? 'att' : pCat === 'rushing' ? 'car' : 'tgt'
    const met = (metrics as Metric<PlayerSplit>[]).find(m => m.key === headlineKey)
    if (!met) return null
    const overall = entitySection(0, OVERALL_DIM).total as PlayerSplit | null
    const base = overall ? met.value(overall) : null
    const overallAtt = volume(overall)
    if (base == null || overallAtt <= 0) return null
    const minVol = Math.max(12, overallAtt * 0.1)
    type Cand = { kind: string; label: React.ReactNode; v: number; delta: number; vol: number }
    const cands: Cand[] = []
    for (const d of config.dims) {
      if (d.key === 'opponent' || d.key === 'opp_division') continue
      for (const [val, row] of entitySection(0, d.key).map) {
        const v = met.value(row); const vol = volume(row)
        if (v == null || vol < minVol) continue
        cands.push({ kind: d.label, label: splitValueLabel(d.key, val), v, delta: v - base, vol })
      }
    }
    // Best / worst opponent matchup (needs a few games to be meaningful).
    const byOpp = new Map<string, typeof games>()
    for (const x of games) (byOpp.get(x.g.opponent) ?? byOpp.set(x.g.opponent, []).get(x.g.opponent)!).push(x)
    for (const [opp, grp] of byOpp) {
      if (grp.length < 3) continue
      const agg = aggregatePlayerSplitRows(grp.map(x => x.r))
      const v = agg ? met.value(agg) : null; const vol = volume(agg)
      if (v == null || vol < minVol) continue
      cands.push({ kind: 'Opponent', v, delta: v - base, vol, label: <span className="inline-flex items-center gap-1"><img src={teamLogoUrl(opp)} className="w-4 h-4 object-contain" alt="" />vs {opp}</span> })
    }
    cands.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    return { met, base, unit, items: cands.slice(0, 6) }
  })()

  function addEntity(r: SearchResult) {
    if (r.type === 'team') setTeams(t => t.includes(r.id) ? t : [...t, r.id].slice(0, 6))
    else setPlayers(p => p.some(x => x.id === r.id) ? p : [...p, { id: r.id, name: r.name, headshot: r.headshot_url, sub: [r.position, r.team].filter(Boolean).join(' · ') }].slice(0, 6))
  }
  const isOpen = (k: string) => openSections.has(k) || (!openSections.has(`!${k}`) && DEFAULT_OPEN.includes(k))
  const toggleOpen = (k: string) => setOpenSections(s => { const n = new Set(s); const open = isOpen(k); n.delete(k); n.delete(`!${k}`); n.add(open ? `!${k}` : k); return n })
  const loading = mode === 'players' ? playerResults.some(r => r.isPending && r.fetchStatus !== 'idle') : teamResults.some(r => r.isPending && r.fetchStatus !== 'idle')
  const visibleDims = sectionDims.filter(d => !hidden.has(d.key))

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <Nav title="Splits Explorer" />
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-start justify-between gap-3 mb-1">
          <h1 className="text-xl font-bold text-white">Splits Explorer</h1>
          {entityCount > 0 && (
            <button onClick={() => { navigator.clipboard?.writeText(window.location.href); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
              className="shrink-0 inline-flex items-center gap-1.5 bg-gray-900 border border-gray-800 text-gray-300 text-xs font-semibold rounded-lg px-3 py-1.5 hover:border-gray-600 hover:text-white transition-colors">
              {copied ? '✓ Copied' : '🔗 Copy link'}
            </button>
          )}
        </div>
        <p className="text-sm text-gray-500 mb-5">Compare head-to-head, then explore every split at once for one entity — by season (down to each game), down, situation, opponent and more. Every view has a shareable link.</p>

        <div className="flex flex-wrap items-center gap-3 mb-3">
          <Seg<Mode> value={mode} options={[{ value: 'players', label: 'Players' }, { value: 'teams', label: 'Teams' }]}
            onChange={m => { setMode(m); setSituation(null); if (m === 'teams' && season === CAREER_SEASON) setSeason(CURRENT_NFL_SEASON) }} />
          <AddEntity mode={mode} onAdd={addEntity} />
        </div>

        {entityCount > 0 && <MatchupHeader entities={entityMeta} onRemove={k => mode === 'players' ? setPlayers(xs => xs.filter(x => x.id !== k)) : setTeams(xs => xs.filter(x => x !== k))} />}

        {entityCount === 0 ? (
          <div className="bg-gray-900 border border-gray-800 border-dashed rounded-xl px-6 py-16 text-center">
            <p className="text-gray-400 font-medium">Add {mode} to compare</p>
            <p className="text-gray-600 text-sm mt-1">Search above to add up to 6 {mode}.</p>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {mode === 'players'
                ? <Seg<PlayerCategory> value={pCat} options={(Object.keys(PLAYER_SPLIT_CONFIG) as PlayerCategory[]).map(c => ({ value: c, label: PLAYER_SPLIT_CONFIG[c].label }))} onChange={c => { setPCat(c); setSituation(null) }} />
                : <Seg<TeamSide> value={tSide} options={(Object.keys(TEAM_SPLIT_CONFIG) as TeamSide[]).map(s => ({ value: s, label: TEAM_SPLIT_CONFIG[s].label }))} onChange={s => { setTSide(s); setSituation(null) }} />}
              <select value={season} onChange={e => setSeason(Number(e.target.value))} className={selectCls}>
                {mode === 'players' && <option value={CAREER_SEASON}>Career</option>}
                {SEASONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            {/* Head-to-head summary with situation chips */}
            <div className="flex flex-wrap items-center gap-1.5 mb-2">
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mr-1">Compare on</span>
              <Chip active={!situation} onClick={() => setSituation(null)}>Overall</Chip>
              {situations.map(s => <Chip key={s.label} active={situation?.label === s.label} onClick={() => setSituation(s)}>{s.label}</Chip>)}
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-6">
              {summaryRows.every(r => r.row == null)
                ? <div className="py-8 text-center text-gray-600 text-sm">{loading ? 'Loading…' : 'No data.'}</div>
                : <StatTable firstCol={mode === 'players' ? 'Player' : 'Team'} rows={summaryRows} metrics={metrics} flip={flip} />}
            </div>

            {/* Where they stand out — auto-surfaced standout splits (single player) */}
            {notable && notable.items.length > 0 && (
              <div className="mb-6">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 mb-2">
                  <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">Where {entityMeta[0].label} stands out</span>
                  <span className="text-[11px] text-gray-600">biggest swings in {notable.met.label} vs {isCareer ? 'career' : season} avg of {notable.met.fmt(notable.base)}</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                  {notable.items.map((it, i) => {
                    const good = notable.met.higherIsBetter ? it.delta > 0 : it.delta < 0
                    return (
                      <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl px-3 py-2.5" style={{ boxShadow: `inset 0 2px 0 0 ${good ? 'rgba(16,185,129,0.7)' : 'rgba(244,63,94,0.7)'}` }}>
                        <div className="text-xs font-semibold text-gray-200 truncate flex items-center gap-1">{it.label}</div>
                        <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1.5">{it.kind}</div>
                        <div className="text-lg font-bold text-white tabular-nums leading-none">{notable.met.fmt(it.v)}</div>
                        <div className={`text-[11px] font-semibold tabular-nums mt-1 ${good ? 'text-emerald-400' : 'text-red-400'}`}>
                          {it.delta >= 0 ? '+' : '−'}{notable.met.fmt(Math.abs(it.delta))}<span className="text-gray-600 font-normal"> · {it.vol} {notable.unit}</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* All splits — single = traditional page; multiple = side-by-side */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">{single ? 'Splits for' : 'Splits side-by-side'}</span>
              {single
                ? <span className="text-sm font-bold text-white">{entityMeta[0].label}</span>
                : <Seg value={keyStatsOnly ? 'key' : 'all'} options={[{ value: 'key', label: 'Key stats' }, { value: 'all', label: 'All stats' }]} onChange={v => setKeyStatsOnly(v === 'key')} />}
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mb-3">
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mr-1">Show</span>
              {sectionDims.map(d => <Chip key={d.key} active={!hidden.has(d.key)} onClick={() => setHidden(h => { const n = new Set(h); n.has(d.key) ? n.delete(d.key) : n.add(d.key); return n })}>{d.label}</Chip>)}
            </div>

            <div className="space-y-3">
              {visibleDims.map(d => {
                const gameBased = GAME_DIMS.has(d.key)
                if (single) {
                  const { rows, total } = sectionData(d.key)
                  return (
                    <Section key={d.key} title={`By ${d.label}`} open={isOpen(d.key)} onToggle={() => toggleOpen(d.key)}>
                      {rows.length === 0
                        ? <div className="py-6 text-center text-gray-600 text-sm">{loading ? 'Loading…' : 'No data.'}</div>
                        : <StatTable firstCol={d.label} rows={rows} total={total} metrics={gameBased ? gameMetrics : metrics} flip={flip}
                            hasDefRk={d.key === 'opponent' && wantDef} naturalSort={!gameBased}
                            onToggleExpand={gameBased ? (k => setExpandedKeys(s => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n })) : undefined} />}
                    </Section>
                  )
                }
                // side-by-side
                const base = gameBased ? gameMetrics : metrics
                const keyList = gameBased ? GAME_KEY_KEYS[catOrSide] : KEY_KEYS[catOrSide]
                const km = keyStatsOnly ? base.filter(m => (keyList ?? []).includes(m.key)) : base
                const m = km.length ? km : base
                const secs = entityMeta.map((_, i) => entitySection(i, d.key))
                const agg = new Map<string, { ord: number; vol: number }>()
                for (const s of secs) for (const [k, row] of s.map) { const e = agg.get(k) ?? { ord: row.sort_order ?? 9999, vol: 0 }; e.vol += volume(row); agg.set(k, e) }
                let keys = [...agg.keys()]
                if (d.key === 'season') keys.sort((a, b) => Number(b) - Number(a))
                else if (d.key === 'opponent') keys.sort((a, b) => agg.get(b)!.vol - agg.get(a)!.vol || a.localeCompare(b))
                else keys.sort((a, b) => agg.get(a)!.ord - agg.get(b)!.ord)
                const keyLabel = (k: string) => d.key === 'season' ? k
                  : d.key === 'opponent' ? <span className="inline-flex items-center gap-1.5"><img src={teamLogoUrl(k)} className="w-5 h-5 object-contain" alt="" />{k}</span>
                  : splitValueLabel(d.key, k)
                return (
                  <Section key={d.key} title={`By ${d.label}`} open={isOpen(d.key)} onToggle={() => toggleOpen(d.key)}>
                    {keys.length === 0
                      ? <div className="py-6 text-center text-gray-600 text-sm">{loading ? 'Loading…' : 'No data.'}</div>
                      : <GroupedTable label={d.label} entities={entityMeta} metrics={m} keys={keys} keyLabel={keyLabel} sections={secs}
                          defRkFor={d.key === 'opponent' && wantDef ? (k => defRank.get(k)) : undefined}
                          expandable={gameBased} expandShowSeason={d.key === 'opponent'} expandedKeys={expandedKeys}
                          onToggleExpand={gameBased ? (k => setExpandedKeys(s => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n })) : undefined}
                          flip={flip} />}
                  </Section>
                )
              })}
            </div>
            <p className="text-[11px] text-gray-600 mt-3 px-1">
              {single ? 'Click a column to sort · ' : ''}▸ expands a season into its games (linked to the game page) · Season &amp; Opponent use official game-log totals; other splits are play-by-play · green = best{single ? ' in column' : ''} · regular season.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
