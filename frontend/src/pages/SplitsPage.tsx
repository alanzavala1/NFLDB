/**
 * Splits explorer — a standalone page to compare players or teams across any
 * situational split. Pivot layout: selected entities are columns, the chosen
 * dimension's values are rows, one switchable metric per cell, best-in-row
 * shaded. Backed by the materialized player_splits / team_splits tables.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { PlayerSplit, TeamSplit, SearchResult } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'
import {
  PLAYER_SPLIT_CONFIG, TEAM_SPLIT_CONFIG, type PlayerCategory, type TeamSide,
  type Metric, splitValueLabel, aggregateCareerByValue, CAREER_SEASON,
} from '../splits'

type Mode = 'players' | 'teams'
type PlayerEntity = { id: string; name: string; headshot?: string | null; sub?: string }

const SEASONS = Array.from({ length: CURRENT_NFL_SEASON - 1998 }, (_, i) => CURRENT_NFL_SEASON - i)

// — segmented control —
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

// — inline entity adder (players or teams) via the search API —
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

// — the pivot cell colorer —
function bestSet(values: (number | null)[], higherIsBetter: boolean | undefined): Set<number> {
  if (higherIsBetter === undefined) return new Set()
  const present = values.map((v, i) => [v, i] as const).filter(([v]) => v != null) as [number, number][]
  if (present.length < 2) return new Set()
  const sorted = [...present].sort((a, b) => higherIsBetter ? b[0] - a[0] : a[0] - b[0])
  if (sorted[0][0] === sorted[sorted.length - 1][0]) return new Set()  // all equal
  const best = sorted[0][0]
  return new Set(present.filter(([v]) => v === best).map(([, i]) => i))
}

export default function SplitsPage() {
  const [mode, setMode] = useState<Mode>('players')
  const [players, setPlayers] = useState<PlayerEntity[]>([])
  const [teams, setTeams] = useState<string[]>([])
  const [pCat, setPCat] = useState<PlayerCategory>('passing')
  const [tSide, setTSide] = useState<TeamSide>('offense')
  const [dim, setDim] = useState<string>('pass_depth')
  const [metricKey, setMetricKey] = useState<string>('epa')
  // Players default to Career (always populated for any added player); teams
  // are season-specific and default to the most recent season.
  const [season, setSeason] = useState<number>(CAREER_SEASON)

  // Fetch each selected entity's splits. Both hooks run every render (empty
  // arrays when inactive) so hook order stays stable.
  const playerResults = useQueries({
    queries: players.map(p => ({
      queryKey: ['player-splits', p.id] as const,
      queryFn: () => api.splits(p.id),
      staleTime: Infinity,
    })),
  })
  const teamResults = useQueries({
    queries: teams.map(t => ({
      queryKey: ['team-splits', t, season] as const,
      queryFn: () => api.teamSplits(t, season),
      staleTime: Infinity,
    })),
  })

  const config = mode === 'players' ? PLAYER_SPLIT_CONFIG[pCat] : TEAM_SPLIT_CONFIG[tSide]
  const activeDim = config.dims.some(d => d.key === dim) ? dim : config.dims[0].key
  const metrics = config.metrics as Metric<PlayerSplit | TeamSplit>[]
  const metric = metrics.find(m => m.key === metricKey) ?? metrics[0]
  // Defense flips: lower EPA/yards/success allowed is better.
  const higherIsBetter = (mode === 'teams' && tSide === 'defense' && metric.higherIsBetter !== undefined)
    ? !metric.higherIsBetter : metric.higherIsBetter

  // Build the pivot: columns (entities) × rows (split values).
  type Col = { key: string; label: string; logo?: string; headshot?: string | null; rows: Map<string, PlayerSplit | TeamSplit> }
  const cols: Col[] = useMemo(() => {
    if (mode === 'players') {
      return players.map((p, i) => {
        const data = (playerResults[i]?.data ?? []) as PlayerSplit[]
        let dimRows = data.filter(s => s.category === pCat && s.split_dim === activeDim)
        if (season === CAREER_SEASON) dimRows = aggregateCareerByValue(dimRows)
        else dimRows = dimRows.filter(s => s.season === season)
        return { key: p.id, label: p.name, headshot: p.headshot, rows: new Map(dimRows.map(r => [r.split_value, r])) }
      })
    }
    return teams.map((t, i) => {
      const data = (teamResults[i]?.data ?? []) as TeamSplit[]
      const dimRows = data.filter(s => s.side === tSide && s.split_dim === activeDim)
      return { key: t, label: t, logo: teamLogoUrl(t), rows: new Map(dimRows.map(r => [r.split_value, r])) }
    })
  }, [mode, players, teams, playerResults, teamResults, pCat, tSide, activeDim, season])

  // Ordered union of split values across columns.
  const valueRows = useMemo(() => {
    const seen = new Map<string, number | null>()
    for (const c of cols) for (const [v, r] of c.rows) if (!seen.has(v)) seen.set(v, r.sort_order)
    return [...seen.entries()].sort((a, b) =>
      (a[1] ?? 9999) - (b[1] ?? 9999) || splitValueLabel(activeDim, a[0]).localeCompare(splitValueLabel(activeDim, b[0])))
      .map(([v]) => v)
  }, [cols, activeDim])

  const loading = mode === 'players' ? playerResults.some(r => r.isPending && r.fetchStatus !== 'idle')
                                     : teamResults.some(r => r.isPending && r.fetchStatus !== 'idle')
  const entityCount = mode === 'players' ? players.length : teams.length

  function addEntity(r: SearchResult) {
    if (r.type === 'team') setTeams(t => t.includes(r.id) ? t : [...t, r.id].slice(0, 6))
    else setPlayers(p => p.some(x => x.id === r.id) ? p : [...p, { id: r.id, name: r.name, headshot: r.headshot_url, sub: [r.position, r.team].filter(Boolean).join(' · ') }].slice(0, 6))
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <Nav title="Splits Explorer" />
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-baseline justify-between gap-3 mb-1">
          <h1 className="text-xl font-bold text-white">Splits Explorer</h1>
        </div>
        <p className="text-sm text-gray-500 mb-5">Compare players or teams across any situation. Add entities, pick a split and a metric — best in each row is highlighted.</p>

        {/* Mode + entity selection */}
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <Seg<Mode> value={mode} options={[{ value: 'players', label: 'Players' }, { value: 'teams', label: 'Teams' }]}
            onChange={m => {
              setMode(m)
              setDim(m === 'players' ? 'pass_depth' : 'game_script')
              setMetricKey('epa')
              // Teams have no Career view — fall back to the latest season.
              if (m === 'teams' && season === CAREER_SEASON) setSeason(CURRENT_NFL_SEASON)
            }} />
          <AddEntity mode={mode} onAdd={addEntity} />
        </div>

        {/* Selected entity chips */}
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
            {/* Controls */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {mode === 'players'
                ? <Seg<PlayerCategory> value={pCat} options={(Object.keys(PLAYER_SPLIT_CONFIG) as PlayerCategory[]).map(c => ({ value: c, label: PLAYER_SPLIT_CONFIG[c].label }))} onChange={c => { setPCat(c); setDim(PLAYER_SPLIT_CONFIG[c].dims[0].key); setMetricKey('epa') }} />
                : <Seg<TeamSide> value={tSide} options={(Object.keys(TEAM_SPLIT_CONFIG) as TeamSide[]).map(s => ({ value: s, label: TEAM_SPLIT_CONFIG[s].label }))} onChange={s => setTSide(s)} />}
              <select value={season} onChange={e => setSeason(Number(e.target.value))}
                className="bg-gray-900 border border-gray-800 text-gray-200 text-xs rounded-lg px-2.5 py-2 focus:outline-none focus:border-gray-600">
                {mode === 'players' && <option value={CAREER_SEASON}>Career</option>}
                {SEASONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <span className="text-[11px] font-bold text-gray-600 uppercase tracking-wider mr-1">Split</span>
              <Seg value={activeDim} options={config.dims.map(d => ({ value: d.key, label: d.label }))} onChange={setDim} />
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <span className="text-[11px] font-bold text-gray-600 uppercase tracking-wider mr-1">Metric</span>
              <Seg value={metric.key} options={metrics.map(m => ({ value: m.key, label: m.label }))} onChange={setMetricKey} />
            </div>

            {/* Pivot table */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="py-2.5 pl-4 pr-3 text-xs font-medium text-gray-500 text-left whitespace-nowrap">
                        {config.dims.find(d => d.key === activeDim)?.label}
                      </th>
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
                      <tr><td colSpan={cols.length + 1} className="py-8 text-center text-gray-600 text-sm">
                        {loading ? 'Loading…' : 'No data for this split / season.'}
                      </td></tr>
                    ) : valueRows.map(v => {
                      const cells = cols.map(c => {
                        const row = c.rows.get(v)
                        return row ? metric.value(row) : null
                      })
                      const best = bestSet(cells, higherIsBetter)
                      return (
                        <tr key={v} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                          <td className="py-2.5 pl-4 pr-3 whitespace-nowrap font-semibold text-white">
                            {activeDim === 'opponent'
                              ? <span className="inline-flex items-center gap-1.5"><img src={teamLogoUrl(v)} className="w-5 h-5 object-contain" alt="" />{v}</span>
                              : splitValueLabel(activeDim, v)}
                          </td>
                          {cells.map((val, i) => (
                            <td key={cols[i].key}
                              className={`py-2.5 px-3 whitespace-nowrap tabular-nums ${
                                val == null ? 'text-gray-700'
                                  : best.has(i) ? 'text-emerald-300 font-bold bg-emerald-500/10'
                                  : 'text-gray-200'}`}>
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
            <p className="text-[11px] text-gray-600 mt-2 px-1">
              {mode === 'teams' && tSide === 'defense' ? 'Defense: lower is better — green = best (stingiest) in row.' : 'Green = best in row.'}
              {' '}Regular season. Small-sample splits can be noisy — switch the metric to a volume stat to gauge sample size.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
