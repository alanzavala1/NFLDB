/**
 * Splits explorer — a standalone page to compare players or teams.
 *
 * Two views:
 *  - Compare (default): the full stat line, entities as columns and every stat
 *    as a row, with a single situational Filter (Overall, or a dimension+value
 *    like "Pass Depth → Deep" / "Opponent → DEN"). Direct head-to-head, then
 *    narrow to a situation.
 *  - By Split: a pivot — one metric across every value of a chosen dimension.
 *
 * Backed by the materialized player_splits / team_splits tables.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { PlayerSplit, TeamSplit, SearchResult } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'
import {
  PLAYER_SPLIT_CONFIG, TEAM_SPLIT_CONFIG, type PlayerCategory, type TeamSide,
  type Metric, splitValueLabel, aggregateCareerByValue, aggregatePlayerSplitRows,
  aggregateTeamSplitRows, CAREER_SEASON, OVERALL_DIM,
} from '../splits'

type Mode = 'players' | 'teams'
type View = 'compare' | 'split'
type PlayerEntity = { id: string; name: string; headshot?: string | null; sub?: string }
type Row = PlayerSplit | TeamSplit

const SEASONS = Array.from({ length: CURRENT_NFL_SEASON - 1998 }, (_, i) => CURRENT_NFL_SEASON - i)

function Seg<T extends string | number>({ value, options, onChange }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex items-center gap-0.5 bg-gray-900 border border-gray-800 rounded-lg p-0.5 flex-wrap">
      {options.map(o => (
        <button key={String(o.value)} onClick={() => onChange(o.value)}
          className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
            value === o.value ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

const selectCls = 'bg-gray-900 border border-gray-800 text-gray-200 text-xs rounded-lg px-2.5 py-2 focus:outline-none focus:border-gray-600'

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
      <input
        value={q}
        onChange={e => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={mode === 'players' ? '+ Add player…' : '+ Add team…'}
        className="bg-gray-900 border border-gray-800 text-gray-200 text-sm rounded-lg px-3 py-2 w-52 focus:outline-none focus:border-gray-600 placeholder-gray-600"
      />
      {open && q.trim() && results.length > 0 && (
        <div className="absolute z-30 mt-1 w-64 max-h-72 overflow-y-auto bg-gray-900 border border-gray-700 rounded-lg shadow-2xl">
          {results.slice(0, 12).map(r => (
            <button key={r.id} onMouseDown={() => { onAdd(r); setQ(''); setResults([]) }}
              className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-gray-800 text-left">
              {r.type === 'team'
                ? <img src={teamLogoUrl(r.id)} className="w-6 h-6 object-contain shrink-0" alt="" />
                : r.headshot_url
                  ? <img src={r.headshot_url} className="w-6 h-6 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                  : <div className="w-6 h-6 rounded-full bg-gray-800 shrink-0" />}
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

// Indices of the best (and tied-best) cells in a row, respecting direction.
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
  const [view, setView] = useState<View>('compare')
  const [players, setPlayers] = useState<PlayerEntity[]>([])
  const [teams, setTeams] = useState<string[]>([])
  const [pCat, setPCat] = useState<PlayerCategory>('passing')
  const [tSide, setTSide] = useState<TeamSide>('offense')
  const [season, setSeason] = useState<number>(CAREER_SEASON)  // players default to Career
  // Compare view: situational filter
  const [filterDim, setFilterDim] = useState<string>('overall')
  const [filterValue, setFilterValue] = useState<string | null>(null)
  // By-Split view: pivot controls
  const [splitDim, setSplitDim] = useState<string>('pass_depth')
  const [metricKey, setMetricKey] = useState<string>('epa')

  const playerResults = useQueries({
    queries: players.map(p => ({ queryKey: ['player-splits', p.id] as const, queryFn: () => api.splits(p.id), staleTime: Infinity })),
  })
  const teamResults = useQueries({
    queries: teams.map(t => ({ queryKey: ['team-splits', t, season] as const, queryFn: () => api.teamSplits(t, season), staleTime: Infinity })),
  })

  const config = mode === 'players' ? PLAYER_SPLIT_CONFIG[pCat] : TEAM_SPLIT_CONFIG[tSide]
  const metrics = config.metrics as Metric<Row>[]
  const catOrSide = mode === 'players' ? pCat : tSide
  const isCareer = mode === 'players' && season === CAREER_SEASON

  // Per-entity raw data.
  const entityData: Row[][] = mode === 'players'
    ? players.map((_, i) => (playerResults[i]?.data ?? []) as PlayerSplit[])
    : teams.map((_, i) => (teamResults[i]?.data ?? []) as TeamSplit[])

  const entityMeta = mode === 'players'
    ? players.map(p => ({ key: p.id, label: p.name, headshot: p.headshot as string | null | undefined, logo: undefined as string | undefined }))
    : teams.map(t => ({ key: t, label: t, headshot: undefined, logo: teamLogoUrl(t) }))

  // Resolve one entity's row for the Compare filter (Overall or a dim+value).
  function resolveRow(data: Row[]): Row | null {
    if (mode === 'players') {
      const rows = data as PlayerSplit[]
      const dimKey = filterDim === 'overall' ? OVERALL_DIM : filterDim
      let sel = rows.filter(s => s.category === pCat && s.split_dim === dimKey)
      if (filterDim !== 'overall') sel = sel.filter(s => s.split_value === filterValue)
      if (isCareer) return aggregatePlayerSplitRows(sel)
      sel = sel.filter(s => s.season === season)
      return filterDim === 'overall' ? aggregatePlayerSplitRows(sel) : (sel[0] ?? null)
    }
    const rows = data as TeamSplit[]
    const dimKey = filterDim === 'overall' ? OVERALL_DIM : filterDim
    let sel = rows.filter(s => s.side === tSide && s.split_dim === dimKey)
    if (filterDim !== 'overall') sel = sel.filter(s => s.split_value === filterValue)
    return filterDim === 'overall' ? aggregateTeamSplitRows(sel) : (sel[0] ?? null)
  }

  // Values available for the chosen filter dimension (union across entities).
  const filterValues = useMemo(() => {
    if (filterDim === 'overall') return []
    const seen = new Map<string, number | null>()
    for (const data of entityData) {
      for (const s of data as (PlayerSplit | TeamSplit)[]) {
        const matchCat = mode === 'players' ? (s as PlayerSplit).category === pCat : (s as TeamSplit).side === tSide
        if (matchCat && s.split_dim === filterDim && (!('season' in s) || isCareer || (s as PlayerSplit).season === season))
          if (!seen.has(s.split_value)) seen.set(s.split_value, s.sort_order)
      }
    }
    return [...seen.entries()]
      .sort((a, b) => (a[1] ?? 9999) - (b[1] ?? 9999) || splitValueLabel(filterDim, a[0]).localeCompare(splitValueLabel(filterDim, b[0])))
      .map(([v]) => v)
  }, [entityData, filterDim, mode, pCat, tSide, season, isCareer])

  const effFilterValue = filterDim === 'overall' ? null
    : (filterValue && filterValues.includes(filterValue) ? filterValue : (filterValues[0] ?? null))

  // Defense flips: lower allowed is better.
  const flip = (hib: boolean | undefined) =>
    (mode === 'teams' && tSide === 'defense' && hib !== undefined) ? !hib : hib

  const entityCount = mode === 'players' ? players.length : teams.length
  const loading = mode === 'players'
    ? playerResults.some(r => r.isPending && r.fetchStatus !== 'idle')
    : teamResults.some(r => r.isPending && r.fetchStatus !== 'idle')

  function addEntity(r: SearchResult) {
    if (r.type === 'team') setTeams(t => t.includes(r.id) ? t : [...t, r.id].slice(0, 6))
    else setPlayers(p => p.some(x => x.id === r.id) ? p : [...p, { id: r.id, name: r.name, headshot: r.headshot_url, sub: [r.position, r.team].filter(Boolean).join(' · ') }].slice(0, 6))
  }

  const filterLabel = filterDim === 'overall'
    ? 'Overall'
    : `${config.dims.find(d => d.key === filterDim)?.label}: ${effFilterValue ? splitValueLabel(filterDim, effFilterValue) : '—'}`

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <Nav title="Splits Explorer" />
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <h1 className="text-xl font-bold text-white mb-1">Splits Explorer</h1>
        <p className="text-sm text-gray-500 mb-5">Compare players or teams head-to-head, then filter to any situation. Best in each row is highlighted.</p>

        {/* Mode + add */}
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <Seg<Mode> value={mode} options={[{ value: 'players', label: 'Players' }, { value: 'teams', label: 'Teams' }]}
            onChange={m => {
              setMode(m); setFilterDim('overall'); setSplitDim(m === 'players' ? 'pass_depth' : 'game_script'); setMetricKey('epa')
              if (m === 'teams' && season === CAREER_SEASON) setSeason(CURRENT_NFL_SEASON)
            }} />
          <AddEntity mode={mode} onAdd={addEntity} />
        </div>

        {/* Chips */}
        {entityCount > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {mode === 'players'
              ? players.map(p => (
                <span key={p.id} className="inline-flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-lg pl-2 pr-1 py-1">
                  {p.headshot ? <img src={p.headshot} className="w-5 h-5 rounded-full object-cover object-top bg-gray-800" alt="" /> : <div className="w-5 h-5 rounded-full bg-gray-800" />}
                  <span className="text-sm text-gray-200">{p.name}</span>
                  <button onClick={() => setPlayers(xs => xs.filter(x => x.id !== p.id))} className="text-gray-600 hover:text-red-400 px-1">×</button>
                </span>
              ))
              : teams.map(t => (
                <span key={t} className="inline-flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-lg pl-2 pr-1 py-1">
                  <img src={teamLogoUrl(t)} className="w-5 h-5 object-contain" alt="" />
                  <span className="text-sm text-gray-200">{t}</span>
                  <button onClick={() => setTeams(xs => xs.filter(x => x !== t))} className="text-gray-600 hover:text-red-400 px-1">×</button>
                </span>
              ))}
          </div>
        )}

        {entityCount === 0 ? (
          <div className="bg-gray-900 border border-gray-800 border-dashed rounded-xl px-6 py-16 text-center">
            <p className="text-gray-400 font-medium">Add {mode} to compare</p>
            <p className="text-gray-600 text-sm mt-1">Use the search box above to add up to 6 {mode}.</p>
          </div>
        ) : (
          <>
            {/* Shared controls: category/side, season, view */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {mode === 'players'
                ? <Seg<PlayerCategory> value={pCat} options={(Object.keys(PLAYER_SPLIT_CONFIG) as PlayerCategory[]).map(c => ({ value: c, label: PLAYER_SPLIT_CONFIG[c].label }))} onChange={c => { setPCat(c); setSplitDim(PLAYER_SPLIT_CONFIG[c].dims[0].key); setFilterDim('overall'); setMetricKey('epa') }} />
                : <Seg<TeamSide> value={tSide} options={(Object.keys(TEAM_SPLIT_CONFIG) as TeamSide[]).map(s => ({ value: s, label: TEAM_SPLIT_CONFIG[s].label }))} onChange={s => setTSide(s)} />}
              <select value={season} onChange={e => setSeason(Number(e.target.value))} className={selectCls}>
                {mode === 'players' && <option value={CAREER_SEASON}>Career</option>}
                {SEASONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <div className="ml-auto">
                <Seg<View> value={view} options={[{ value: 'compare', label: 'Compare' }, { value: 'split', label: 'By Split' }]} onChange={setView} />
              </div>
            </div>

            {view === 'compare' ? (
              <>
                {/* Filter */}
                <div className="flex flex-wrap items-center gap-2 mb-4">
                  <span className="text-[11px] font-bold text-gray-600 uppercase tracking-wider mr-1">Filter</span>
                  <select value={filterDim} onChange={e => { setFilterDim(e.target.value); setFilterValue(null) }} className={selectCls}>
                    <option value="overall">Overall</option>
                    {config.dims.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
                  </select>
                  {filterDim !== 'overall' && (
                    <select value={effFilterValue ?? ''} onChange={e => setFilterValue(e.target.value)} className={selectCls}>
                      {filterValues.length === 0 && <option value="">—</option>}
                      {filterValues.map(v => <option key={v} value={v}>{splitValueLabel(filterDim, v)}</option>)}
                    </select>
                  )}
                </div>

                {/* Compare table: stats as rows, entities as columns */}
                <CompareTable
                  metrics={metrics}
                  cols={entityData.map((data, i) => ({ ...entityMeta[i], row: resolveRow(data) }))}
                  flip={flip}
                  loading={loading}
                  caption={filterLabel}
                />
              </>
            ) : (
              <SplitPivot
                mode={mode} catOrSide={catOrSide} season={season} isCareer={isCareer}
                config={config} metrics={metrics} flip={flip}
                entityData={entityData} entityMeta={entityMeta}
                splitDim={splitDim} setSplitDim={setSplitDim} metricKey={metricKey} setMetricKey={setMetricKey}
                loading={loading}
              />
            )}

            <p className="text-[11px] text-gray-600 mt-2 px-1">
              {mode === 'teams' && tSide === 'defense' ? 'Defense: lower is better — green = best (stingiest) in row. ' : 'Green = best in row. '}
              Regular season. A thin situation (e.g. one opponent in one season) is a small sample — switch to Career or pick a volume stat to gauge it.
            </p>
          </>
        )}
      </div>
    </div>
  )
}

// — Compare: full stat line, stats as rows —
function CompareTable({ metrics, cols, flip, loading, caption }: {
  metrics: Metric<Row>[]
  cols: { key: string; label: string; headshot?: string | null; logo?: string; row: Row | null }[]
  flip: (hib: boolean | undefined) => boolean | undefined
  loading: boolean
  caption: string
}) {
  const anyData = cols.some(c => c.row != null)
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="py-2.5 pl-4 pr-3 text-xs font-medium text-gray-500 text-left whitespace-nowrap">{caption}</th>
              {cols.map(c => (
                <th key={c.key} className="py-2.5 px-3 text-left whitespace-nowrap">
                  <div className="flex items-center gap-1.5">
                    {c.logo ? <img src={c.logo} className="w-5 h-5 object-contain" alt="" />
                      : c.headshot ? <img src={c.headshot} className="w-5 h-5 rounded-full object-cover object-top bg-gray-800" alt="" /> : null}
                    <span className="text-xs font-semibold text-gray-200">{c.label}</span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!anyData ? (
              <tr><td colSpan={cols.length + 1} className="py-8 text-center text-gray-600 text-sm">{loading ? 'Loading…' : 'No data for this filter / season.'}</td></tr>
            ) : metrics.map(m => {
              const vals = cols.map(c => c.row ? m.value(c.row) : null)
              const best = bestSet(vals, flip(m.higherIsBetter))
              return (
                <tr key={m.key} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                  <td className="py-2 pl-4 pr-3 whitespace-nowrap text-xs font-semibold text-gray-400 uppercase tracking-wider">{m.label}</td>
                  {vals.map((v, i) => (
                    <td key={cols[i].key} className={`py-2 px-3 whitespace-nowrap tabular-nums ${
                      v == null ? 'text-gray-700' : best.has(i) ? 'text-emerald-300 font-bold bg-emerald-500/10' : 'text-gray-200'}`}>
                      {v == null ? '—' : m.fmt(v)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// — By Split: pivot of one metric across a dimension's values —
function SplitPivot({ mode, catOrSide, season, isCareer, config, metrics, flip, entityData, entityMeta, splitDim, setSplitDim, metricKey, setMetricKey, loading }: {
  mode: Mode; catOrSide: string; season: number; isCareer: boolean
  config: { dims: { key: string; label: string }[] }
  metrics: Metric<Row>[]
  flip: (hib: boolean | undefined) => boolean | undefined
  entityData: Row[][]
  entityMeta: { key: string; label: string; headshot?: string | null; logo?: string }[]
  splitDim: string; setSplitDim: (s: string) => void
  metricKey: string; setMetricKey: (s: string) => void
  loading: boolean
}) {
  const activeDim = config.dims.some(d => d.key === splitDim) ? splitDim : config.dims[0].key
  const metric = metrics.find(m => m.key === metricKey) ?? metrics[0]

  // Per entity: value-map for the active dim.
  const cols = entityData.map((data, i) => {
    let rows: Row[]
    if (mode === 'players') {
      let r = (data as PlayerSplit[]).filter(s => s.category === catOrSide && s.split_dim === activeDim)
      if (isCareer) r = aggregateCareerByValue(r)
      else r = r.filter(s => s.season === season)
      rows = r
    } else {
      rows = (data as TeamSplit[]).filter(s => s.side === catOrSide && s.split_dim === activeDim)
    }
    return { ...entityMeta[i], map: new Map(rows.map(r => [r.split_value, r])) }
  })

  const valueRows = useMemo(() => {
    const seen = new Map<string, number | null>()
    for (const c of cols) for (const [v, r] of c.map) if (!seen.has(v)) seen.set(v, r.sort_order)
    return [...seen.entries()].sort((a, b) => (a[1] ?? 9999) - (b[1] ?? 9999) || splitValueLabel(activeDim, a[0]).localeCompare(splitValueLabel(activeDim, b[0]))).map(([v]) => v)
  }, [cols, activeDim])

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-[11px] font-bold text-gray-600 uppercase tracking-wider mr-1">Split</span>
        <Seg value={activeDim} options={config.dims.map(d => ({ value: d.key, label: d.label }))} onChange={setSplitDim} />
      </div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-[11px] font-bold text-gray-600 uppercase tracking-wider mr-1">Metric</span>
        <select value={metric.key} onChange={e => setMetricKey(e.target.value)} className={selectCls}>
          {metrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
        </select>
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="py-2.5 pl-4 pr-3 text-xs font-medium text-gray-500 text-left whitespace-nowrap">{config.dims.find(d => d.key === activeDim)?.label}</th>
                {cols.map(c => (
                  <th key={c.key} className="py-2.5 px-3 text-left whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      {c.logo ? <img src={c.logo} className="w-5 h-5 object-contain" alt="" />
                        : c.headshot ? <img src={c.headshot} className="w-5 h-5 rounded-full object-cover object-top bg-gray-800" alt="" /> : null}
                      <span className="text-xs font-semibold text-gray-200">{c.label}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {valueRows.length === 0 ? (
                <tr><td colSpan={cols.length + 1} className="py-8 text-center text-gray-600 text-sm">{loading ? 'Loading…' : 'No data for this split / season.'}</td></tr>
              ) : valueRows.map(v => {
                const cells = cols.map(c => { const row = c.map.get(v); return row ? metric.value(row) : null })
                const best = bestSet(cells, flip(metric.higherIsBetter))
                return (
                  <tr key={v} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                    <td className="py-2.5 pl-4 pr-3 whitespace-nowrap font-semibold text-white">
                      {activeDim === 'opponent'
                        ? <span className="inline-flex items-center gap-1.5"><img src={teamLogoUrl(v)} className="w-5 h-5 object-contain" alt="" />{v}</span>
                        : splitValueLabel(activeDim, v)}
                    </td>
                    {cells.map((val, i) => (
                      <td key={cols[i].key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums ${
                        val == null ? 'text-gray-700' : best.has(i) ? 'text-emerald-300 font-bold bg-emerald-500/10' : 'text-gray-200'}`}>
                        {val == null ? '—' : metric.fmt(val)}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
