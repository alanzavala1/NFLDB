/**
 * Splits explorer — a standalone page to compare players (or teams) in a
 * traditional stat table, then slice by situation.
 *
 * One seamless table: rows are the entities you add (compare) OR, when you
 * pick a "Break down by", the values of that dimension for the focused entity
 * (e.g. one QB vs every opponent). Columns are the full stat line and are
 * click-to-sort. Situational splits are always-visible chips that condition
 * every row. On the opponent breakdown a Def Rk column (opponent's defensive
 * rank that season) is available and sortable.
 *
 * Backed by the materialized player_splits / team_splits tables, plus
 * team_season_analytics for the opponent defensive ranks.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { PlayerSplit, TeamSplit, SearchResult } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'
import {
  PLAYER_SPLIT_CONFIG, TEAM_SPLIT_CONFIG, PLAYER_SITUATIONS, TEAM_SITUATIONS,
  type PlayerCategory, type TeamSide, type Metric, type Situation,
  splitValueLabel, aggregateCareerByValue, aggregatePlayerSplitRows,
  aggregateTeamSplitRows, CAREER_SEASON, OVERALL_DIM,
} from '../splits'

type Mode = 'players' | 'teams'
type PlayerEntity = { id: string; name: string; headshot?: string | null; sub?: string }
type Row = PlayerSplit | TeamSplit
type EntityCard = { key: string; label: string; sub?: string; headshot?: string | null; logo?: string; color: string }
type Sort = { key: string; dir: 'asc' | 'desc' }

const SEASONS = Array.from({ length: CURRENT_NFL_SEASON - 1998 }, (_, i) => CURRENT_NFL_SEASON - i)
const ENTITY_COLORS = ['99,102,241', '20,184,166', '245,158,11', '56,189,248', '244,63,94', '168,85,247']
const colorOf = (i: number) => ENTITY_COLORS[i % ENTITY_COLORS.length]
const selectCls = 'bg-gray-900 border border-gray-800 text-gray-200 text-xs rounded-lg px-2.5 py-2 focus:outline-none focus:border-gray-600'

function Seg<T extends string | number>({ value, options, onChange }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex items-center gap-0.5 bg-gray-900 border border-gray-800 rounded-lg p-0.5 flex-wrap">
      {options.map(o => (
        <button key={String(o.value)} onClick={() => onChange(o.value)}
          className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
            value === o.value ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}>{o.label}</button>
      ))}
    </div>
  )
}

// Pill used for the always-visible split chips.
function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors ${
        active ? 'bg-indigo-600 border-indigo-500 text-white' : 'bg-gray-900 border-gray-800 text-gray-400 hover:text-white hover:border-gray-700'}`}>
      {children}
    </button>
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
      try {
        const res = await api.search(trimmed)
        if (!cancelled) setResults(res.filter(r => mode === 'players' ? r.type === 'player' : r.type === 'team'))
      } catch { if (!cancelled) setResults([]) }
    }, 250)
    return () => { cancelled = true }
  }, [q, mode])
  return (
    <div className="relative">
      <input value={q} onChange={e => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={mode === 'players' ? '+ Add player…' : '+ Add team…'}
        className="bg-gray-900 border border-gray-800 text-gray-200 text-sm rounded-lg px-3 py-2 w-52 focus:outline-none focus:border-gray-600 placeholder-gray-600" />
      {open && q.trim() && results.length > 0 && (
        <div className="absolute z-30 mt-1 w-64 max-h-72 overflow-y-auto bg-gray-900 border border-gray-700 rounded-lg shadow-2xl">
          {results.slice(0, 12).map(r => (
            <button key={r.id} onMouseDown={() => { onAdd(r); setQ(''); setResults([]) }}
              className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-gray-800 text-left">
              {r.type === 'team'
                ? <img src={teamLogoUrl(r.id)} className="w-6 h-6 object-contain shrink-0" alt="" />
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
        <div key={e.key} className="group relative flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-xl pl-3 pr-8 py-2.5 min-w-[150px]"
          style={{ boxShadow: `inset 0 2px 0 0 rgba(${e.color},0.9)` }}>
          {e.logo ? <img src={e.logo} className="w-10 h-10 object-contain shrink-0" alt="" />
            : e.headshot ? <img src={e.headshot} className="w-10 h-10 rounded-full object-cover object-top bg-gray-800 shrink-0" style={{ boxShadow: `0 0 0 2px rgba(${e.color},0.55)` }} alt="" />
              : <div className="w-10 h-10 rounded-full bg-gray-800 shrink-0" />}
          <div className="min-w-0">
            <div className="text-sm font-bold text-white truncate leading-tight">{e.label}</div>
            {e.sub && <div className="text-[11px] text-gray-500 truncate">{e.sub}</div>}
          </div>
          <button onClick={() => onRemove(e.key)} className="absolute top-1.5 right-1.5 w-5 h-5 flex items-center justify-center rounded text-gray-600 hover:text-red-400 hover:bg-gray-800">×</button>
          {i < entities.length - 1 && entities.length === 2 && (
            <span className="absolute -right-3 top-1/2 -translate-y-1/2 z-10 text-[10px] font-black text-gray-600">VS</span>
          )}
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

export default function SplitsPage() {
  const [mode, setMode] = useState<Mode>('players')
  const [players, setPlayers] = useState<PlayerEntity[]>([])
  const [teams, setTeams] = useState<string[]>([])
  const [pCat, setPCat] = useState<PlayerCategory>('passing')
  const [tSide, setTSide] = useState<TeamSide>('offense')
  const [season, setSeason] = useState<number>(CAREER_SEASON)
  const [situation, setSituation] = useState<Situation | null>(null)
  const [breakdown, setBreakdown] = useState<string | null>(null)
  const [focusIdx, setFocusIdx] = useState(0)
  const [sort, setSort] = useState<Sort | null>(null)

  const playerResults = useQueries({ queries: players.map(p => ({ queryKey: ['player-splits', p.id] as const, queryFn: () => api.splits(p.id), staleTime: Infinity })) })
  const teamResults = useQueries({ queries: teams.map(t => ({ queryKey: ['team-splits', t, season] as const, queryFn: () => api.teamSplits(t, season), staleTime: Infinity })) })

  const config = mode === 'players' ? PLAYER_SPLIT_CONFIG[pCat] : TEAM_SPLIT_CONFIG[tSide]
  const metrics = config.metrics as Metric<Row>[]
  const metricByKey = useMemo(() => Object.fromEntries(metrics.map(m => [m.key, m])), [metrics])
  const situations: Situation[] = mode === 'players' ? PLAYER_SITUATIONS[pCat] : TEAM_SITUATIONS
  const isCareer = mode === 'players' && season === CAREER_SEASON
  const canDefRk = mode === 'players' && breakdown === 'opponent' && !isCareer

  // Opponent defensive ranks for the season (for the Def Rk column / sort).
  const analytics = useQuery({ queryKey: ['team-analytics', season] as const, queryFn: () => api.teamAnalytics(season), enabled: canDefRk, staleTime: Infinity })
  const defRank = useMemo(() => {
    const m = new Map<string, number>()
    for (const t of analytics.data?.league ?? []) if (t.def_epa_play_rank != null) m.set(t.team, t.def_epa_play_rank)
    return m
  }, [analytics.data])

  const entityData: Row[][] = mode === 'players'
    ? players.map((_, i) => (playerResults[i]?.data ?? []) as PlayerSplit[])
    : teams.map((_, i) => (teamResults[i]?.data ?? []) as TeamSplit[])
  const entityMeta: EntityCard[] = mode === 'players'
    ? players.map((p, i) => ({ key: p.id, label: p.name, sub: p.sub, headshot: p.headshot, color: colorOf(i) }))
    : teams.map((t, i) => ({ key: t, label: teamName(t), sub: t, logo: teamLogoUrl(t), color: colorOf(i) }))
  const entityCount = entityMeta.length
  const effFocus = Math.min(focusIdx, Math.max(0, entityCount - 1))

  // One entity's row under the active situation (Overall when none).
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

  // The focused entity exploded into one row per value of `breakdown`.
  function breakdownRows(data: Row[], dim: string): Row[] {
    if (mode === 'players') {
      let rows = (data as PlayerSplit[]).filter(s => s.category === pCat && s.split_dim === dim)
      if (isCareer) return aggregateCareerByValue(rows)
      rows = rows.filter(s => s.season === season)
      return rows
    }
    return (data as TeamSplit[]).filter(s => s.side === tSide && s.split_dim === dim)
  }

  type TRow = { key: string; meta?: EntityCard; value?: string; row: Row | null; defRk?: number | null }
  const baseRows: TRow[] = breakdown
    ? breakdownRows(entityData[effFocus] ?? [], breakdown).map(r => ({ key: r.split_value, value: r.split_value, row: r, defRk: canDefRk ? (defRank.get(r.split_value) ?? null) : undefined }))
    : entityMeta.map((meta, i) => ({ key: meta.key, meta, row: situationRow(entityData[i]) }))

  // Sort.
  const rows = useMemo(() => {
    const arr = [...baseRows]
    const rowLabel = (r: TRow) => r.meta ? r.meta.label : splitValueLabel(breakdown ?? '', r.value ?? '')
    if (sort) {
      const val = (r: TRow): number | string | null =>
        sort.key === '__label' ? rowLabel(r)
          : sort.key === '__defrk' ? (r.defRk ?? null)
          : (r.row ? metricByKey[sort.key]?.value(r.row) ?? null : null)
      arr.sort((a, b) => {
        const av = val(a), bv = val(b)
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        const c = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number)
        return sort.dir === 'asc' ? c : -c
      })
    } else if (breakdown) {
      arr.sort((a, b) => ((a.row?.sort_order ?? 9999) - (b.row?.sort_order ?? 9999)) || ((((b.row as PlayerSplit)?.att ?? (b.row as TeamSplit)?.plays) ?? 0) - (((a.row as PlayerSplit)?.att ?? (a.row as TeamSplit)?.plays) ?? 0)))
    }
    return arr
  }, [baseRows, sort, breakdown, metricByKey])

  // Best in each metric column (across the visible rows).
  const colBest = useMemo(() => {
    const flip = (hib: boolean | undefined) => (mode === 'teams' && tSide === 'defense' && hib !== undefined) ? !hib : hib
    const m = new Map<string, Set<number>>()
    for (const met of metrics) m.set(met.key, bestSet(rows.map(r => r.row ? met.value(r.row) : null), flip(met.higherIsBetter)))
    return m
  }, [rows, metrics, mode, tSide])

  function clickSort(key: string, defaultDir: 'asc' | 'desc' = 'desc') {
    setSort(s => s && s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: defaultDir })
  }
  const sortArrow = (key: string) => sort?.key === key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''

  function addEntity(r: SearchResult) {
    if (r.type === 'team') setTeams(t => t.includes(r.id) ? t : [...t, r.id].slice(0, 6))
    else setPlayers(p => p.some(x => x.id === r.id) ? p : [...p, { id: r.id, name: r.name, headshot: r.headshot_url, sub: [r.position, r.team].filter(Boolean).join(' · ') }].slice(0, 6))
  }
  function resetSplits() { setSituation(null); setBreakdown(null); setSort(null) }

  const loading = mode === 'players' ? playerResults.some(r => r.isPending && r.fetchStatus !== 'idle') : teamResults.some(r => r.isPending && r.fetchStatus !== 'idle')
  const oppValues = mode === 'players' ? [...new Set(entityData.flat().filter((s): s is PlayerSplit => (s as PlayerSplit).category === pCat && s.split_dim === 'opponent').map(s => s.split_value))].sort() : []
  const firstColLabel = breakdown ? (config.dims.find(d => d.key === breakdown)?.label ?? 'Value') : (mode === 'players' ? 'Player' : 'Team')

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <Nav title="Splits Explorer" />
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <h1 className="text-xl font-bold text-white mb-1">Splits Explorer</h1>
        <p className="text-sm text-gray-500 mb-5">Compare players or teams head-to-head, slice by any situation, or break one down vs every opponent.</p>

        <div className="flex flex-wrap items-center gap-3 mb-3">
          <Seg<Mode> value={mode} options={[{ value: 'players', label: 'Players' }, { value: 'teams', label: 'Teams' }]}
            onChange={m => { setMode(m); resetSplits(); if (m === 'teams' && season === CAREER_SEASON) setSeason(CURRENT_NFL_SEASON) }} />
          <AddEntity mode={mode} onAdd={addEntity} />
        </div>

        {entityCount > 0 && (
          <MatchupHeader entities={entityMeta} onRemove={k => mode === 'players' ? setPlayers(xs => xs.filter(x => x.id !== k)) : setTeams(xs => xs.filter(x => x !== k))} />
        )}

        {entityCount === 0 ? (
          <div className="bg-gray-900 border border-gray-800 border-dashed rounded-xl px-6 py-16 text-center">
            <p className="text-gray-400 font-medium">Add {mode} to compare</p>
            <p className="text-gray-600 text-sm mt-1">Search above to add up to 6 {mode}.</p>
          </div>
        ) : (
          <>
            {/* Category/side + season */}
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {mode === 'players'
                ? <Seg<PlayerCategory> value={pCat} options={(Object.keys(PLAYER_SPLIT_CONFIG) as PlayerCategory[]).map(c => ({ value: c, label: PLAYER_SPLIT_CONFIG[c].label }))} onChange={c => { setPCat(c); resetSplits() }} />
                : <Seg<TeamSide> value={tSide} options={(Object.keys(TEAM_SPLIT_CONFIG) as TeamSide[]).map(s => ({ value: s, label: TEAM_SPLIT_CONFIG[s].label }))} onChange={s => { setTSide(s); resetSplits() }} />}
              <select value={season} onChange={e => setSeason(Number(e.target.value))} className={selectCls}>
                {mode === 'players' && <option value={CAREER_SEASON}>Career</option>}
                {SEASONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            {/* Splits — always visible. Situations condition all rows; Break down turns one entity into rows. */}
            <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-3 mb-5 space-y-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mr-1 w-20">Situation</span>
                <Chip active={!situation && !breakdown} onClick={() => { setSituation(null); setBreakdown(null) }}>Overall</Chip>
                {situations.map(s => (
                  <Chip key={s.label} active={!breakdown && situation?.label === s.label} onClick={() => { setSituation(s); setBreakdown(null) }}>{s.label}</Chip>
                ))}
                {mode === 'players' && oppValues.length > 0 && (
                  <select value={!breakdown && situation?.dim === 'opponent' ? situation.value : ''}
                    onChange={e => e.target.value ? (setSituation({ label: `vs ${e.target.value}`, dim: 'opponent', value: e.target.value }), setBreakdown(null)) : setSituation(null)}
                    className={`${selectCls} ${!breakdown && situation?.dim === 'opponent' ? 'border-indigo-500 text-white' : ''}`}>
                    <option value="">vs Team…</option>
                    {oppValues.map(t => <option key={t} value={t}>vs {t}</option>)}
                  </select>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mr-1 w-20">Break down</span>
                {config.dims.map(d => (
                  <Chip key={d.key} active={breakdown === d.key} onClick={() => { setBreakdown(breakdown === d.key ? null : d.key); setSituation(null); setSort(null) }}>{d.label}</Chip>
                ))}
              </div>
              {breakdown && entityCount > 1 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mr-1 w-20">Showing</span>
                  {entityMeta.map((e, i) => (
                    <Chip key={e.key} active={i === effFocus} onClick={() => setFocusIdx(i)}>{e.label}</Chip>
                  ))}
                </div>
              )}
            </div>

            {/* The table */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b-2 border-gray-800">
                      <th onClick={() => clickSort('__label', 'asc')}
                        className="py-2.5 pl-4 pr-3 text-[11px] font-bold text-gray-400 uppercase tracking-wider text-left whitespace-nowrap cursor-pointer hover:text-white select-none">
                        {firstColLabel}{sortArrow('__label')}
                      </th>
                      {canDefRk && (
                        <th onClick={() => clickSort('__defrk', 'asc')} className="py-2.5 px-3 text-[11px] font-bold text-amber-500/70 uppercase tracking-wider text-left whitespace-nowrap cursor-pointer hover:text-amber-300 select-none">Def Rk{sortArrow('__defrk')}</th>
                      )}
                      {metrics.map(m => (
                        <th key={m.key} onClick={() => clickSort(m.key)}
                          className="py-2.5 px-3 text-[11px] font-bold text-gray-500 uppercase tracking-wider text-left whitespace-nowrap cursor-pointer hover:text-white select-none">{m.label}{sortArrow(m.key)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 || rows.every(r => r.row == null) ? (
                      <tr><td colSpan={metrics.length + (canDefRk ? 2 : 1)} className="py-8 text-center text-gray-600 text-sm">{loading ? 'Loading…' : 'No data for this selection.'}</td></tr>
                    ) : rows.map(r => (
                      <tr key={r.key} className="border-t border-gray-800/50 hover:bg-gray-800/30">
                        <td className="py-2.5 pl-4 pr-3 whitespace-nowrap font-semibold text-white">
                          {r.meta ? (
                            <span className="inline-flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: `rgb(${r.meta.color})` }} />
                              {r.meta.headshot ? <img src={r.meta.headshot} className="w-6 h-6 rounded-full object-cover object-top bg-gray-800" alt="" /> : r.meta.logo ? <img src={r.meta.logo} className="w-6 h-6 object-contain" alt="" /> : null}
                              {r.meta.label}
                            </span>
                          ) : breakdown === 'opponent'
                            ? <span className="inline-flex items-center gap-1.5"><img src={teamLogoUrl(r.value ?? '')} className="w-5 h-5 object-contain" alt="" />{r.value}</span>
                            : splitValueLabel(breakdown ?? '', r.value ?? '')}
                        </td>
                        {canDefRk && (
                          <td className="py-2.5 px-3 whitespace-nowrap tabular-nums text-amber-200/80">{r.defRk != null ? `#${r.defRk}` : '—'}</td>
                        )}
                        {metrics.map(m => {
                          const v = r.row ? m.value(r.row) : null
                          const isBest = colBest.get(m.key)?.has(rows.indexOf(r))
                          return (
                            <td key={m.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums ${
                              v == null ? 'text-gray-700' : isBest ? 'text-emerald-300 font-bold bg-emerald-500/15' : 'text-gray-200'}`}>
                              {v == null ? '—' : m.fmt(v)}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="text-[11px] text-gray-600 mt-2 px-1">
              Click any column to sort. {canDefRk && 'Def Rk = opponent defense EPA rank that season (1 = best defense). '}
              {mode === 'teams' && tSide === 'defense' ? 'Defense: lower is better. ' : ''}Green = best in column · regular season.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
