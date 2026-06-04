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
function StatTable({ firstCol, rows, metrics, flip, hasDefRk, defaultSort, naturalSort, onToggleExpand }: {
  firstCol: string
  rows: TRow[]
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

export default function SplitsPage() {
  const [mode, setMode] = useState<Mode>('players')
  const [players, setPlayers] = useState<PlayerEntity[]>([])
  const [teams, setTeams] = useState<string[]>([])
  const [pCat, setPCat] = useState<PlayerCategory>('passing')
  const [tSide, setTSide] = useState<TeamSide>('offense')
  const [season, setSeason] = useState<number>(CAREER_SEASON)
  const [situation, setSituation] = useState<Situation | null>(null)
  const [focusIdx, setFocusIdx] = useState(0)
  const [hidden, setHidden] = useState<Set<string>>(new Set())  // hidden section keys
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())
  const [expandedSeasons, setExpandedSeasons] = useState<Set<number>>(new Set())

  const playerResults = useQueries({ queries: players.map(p => ({ queryKey: ['player-splits', p.id] as const, queryFn: () => api.splits(p.id), staleTime: Infinity })) })
  const teamResults = useQueries({ queries: teams.map(t => ({ queryKey: ['team-splits', t, season] as const, queryFn: () => api.teamSplits(t, season), staleTime: Infinity })) })

  const config = mode === 'players' ? PLAYER_SPLIT_CONFIG[pCat] : TEAM_SPLIT_CONFIG[tSide]
  const metrics = config.metrics as Metric<Row>[]
  const situations: Situation[] = mode === 'players' ? PLAYER_SITUATIONS[pCat] : TEAM_SITUATIONS
  const isCareer = mode === 'players' && season === CAREER_SEASON
  const flip = (hib: boolean | undefined) => (mode === 'teams' && tSide === 'defense' && hib !== undefined) ? !hib : hib

  const entityData: Row[][] = mode === 'players' ? players.map((_, i) => (playerResults[i]?.data ?? []) as PlayerSplit[]) : teams.map((_, i) => (teamResults[i]?.data ?? []) as TeamSplit[])
  const entityMeta: EntityCard[] = mode === 'players' ? players.map((p, i) => ({ key: p.id, label: p.name, sub: p.sub, headshot: p.headshot, color: colorOf(i) })) : teams.map((t, i) => ({ key: t, label: teamName(t), sub: t, logo: teamLogoUrl(t), color: colorOf(i) }))
  const entityCount = entityMeta.length
  const effFocus = Math.min(focusIdx, Math.max(0, entityCount - 1))
  const focusData = entityData[effFocus] ?? []
  const focusKey = mode === 'players' ? players[effFocus]?.id : undefined

  // Focused player's game log (for per-game season expansion).
  const profile = useQuery({ queryKey: ['player', focusKey] as const, queryFn: () => api.player(focusKey!), enabled: mode === 'players' && !!focusKey, staleTime: Infinity })

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

  function dimRows(dim: string): TRow[] {
    if (dim === 'season') {
      // per-season aggregate of the focused player's plays, newest first
      const rows = (focusData as PlayerSplit[]).filter(s => s.category === pCat && s.split_dim === OVERALL_DIM)
      const bySeason = new Map<number, PlayerSplit[]>()
      for (const r of rows) (bySeason.get(r.season) ?? bySeason.set(r.season, []).get(r.season)!).push(r)
      const seasonsDesc = [...bySeason.keys()].sort((a, b) => b - a)
      const out: TRow[] = []
      const games = (profile.data?.games ?? []).filter(g => g.game_type === 'REG')
      for (const yr of seasonsDesc) {
        const agg = aggregatePlayerSplitRows(bySeason.get(yr)!)
        out.push({ key: `s${yr}`, label: <span className="font-bold">{yr}</span>, row: agg })
        if (expandedSeasons.has(yr)) {
          for (const g of games.filter(g => g.season === yr).sort((a, b) => a.week - b.week)) {
            const gr = gameToSplitRow(g, pCat)
            if ((gr.att ?? 0) > 0) out.push({ key: `g${g.game_id}`, sub: true, row: gr, label: `Wk ${g.week} ${g.location === 'home' ? 'vs' : '@'} ${g.opponent}` })
          }
        }
      }
      return out
    }
    let rows: Row[]
    if (mode === 'players') {
      let r = (focusData as PlayerSplit[]).filter(s => s.category === pCat && s.split_dim === dim)
      if (isCareer) r = aggregateCareerByValue(r); else r = r.filter(s => s.season === season)
      rows = r
    } else {
      rows = (focusData as TeamSplit[]).filter(s => s.side === tSide && s.split_dim === dim)
    }
    return rows.map(r => ({
      key: r.split_value,
      label: dim === 'opponent' ? <span className="inline-flex items-center gap-1.5"><img src={teamLogoUrl(r.split_value)} className="w-5 h-5 object-contain" alt="" />{r.split_value}</span> : splitValueLabel(dim, r.split_value),
      row: r,
      defRk: dim === 'opponent' && wantDef ? (defRank.get(r.split_value) ?? null) : undefined,
    }))
  }

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
        <h1 className="text-xl font-bold text-white mb-1">Splits Explorer</h1>
        <p className="text-sm text-gray-500 mb-5">Compare head-to-head, then explore every split at once for one entity — by season (down to each game), down, situation, opponent and more.</p>

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

            {/* All splits at once, for the focused entity */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">Splits for</span>
              {entityCount > 1
                ? <Seg value={effFocus} options={entityMeta.map((e, i) => ({ value: i, label: e.label }))} onChange={setFocusIdx} />
                : <span className="text-sm font-bold text-white">{entityMeta[0].label}</span>}
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mb-3">
              <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mr-1">Show</span>
              {sectionDims.map(d => <Chip key={d.key} active={!hidden.has(d.key)} onClick={() => setHidden(h => { const n = new Set(h); n.has(d.key) ? n.delete(d.key) : n.add(d.key); return n })}>{d.label}</Chip>)}
            </div>

            <div className="space-y-3">
              {visibleDims.map(d => {
                const rows = dimRows(d.key)
                return (
                  <Section key={d.key} title={`By ${d.label}`} open={isOpen(d.key)} onToggle={() => toggleOpen(d.key)}>
                    {rows.length === 0
                      ? <div className="py-6 text-center text-gray-600 text-sm">{loading ? 'Loading…' : 'No data.'}</div>
                      : <StatTable firstCol={d.label} rows={rows} metrics={metrics} flip={flip}
                          hasDefRk={d.key === 'opponent' && wantDef}
                          naturalSort={d.key !== 'season'}
                          onToggleExpand={d.key === 'season' ? (k => { const yr = Number(k.slice(1)); setExpandedSeasons(s => { const n = new Set(s); n.has(yr) ? n.delete(yr) : n.add(yr); return n }) }) : undefined} />}
                  </Section>
                )
              })}
            </div>
            <p className="text-[11px] text-gray-600 mt-3 px-1">Click any column to sort · click ▸ on a season to expand its games · green = best in column · regular season.</p>
          </>
        )}
      </div>
    </div>
  )
}
