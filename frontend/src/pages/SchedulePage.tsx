import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

function HomeIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
      <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7A1 1 0 003 11h1v6a1 1 0 001 1h4v-4h2v4h4a1 1 0 001-1v-6h1a1 1 0 00.707-1.707l-7-7z" />
    </svg>
  )
}
import { api } from '../api'
import type { Game, SeasonEntry, WeekGroup } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl, CONFERENCES } from '../utils/teams'

const GAME_TYPE_LABELS: Record<string, string> = { WC: 'Wild Card', DIV: 'Divisional', CON: 'Conference', SB: 'Super Bowl' }

function IngestProgress({ season, onDone }: { season: number; onDone: () => void }) {
  const [lines, setLines] = useState<string[]>([])

  useEffect(() => {
    setLines([])
    const es = new EventSource(`/api/seasons/${season}/progress`)
    es.onmessage = (e) => {
      const text = e.data as string
      if (text.startsWith('__DONE__')) {
        es.close()
        onDone()
      } else if (text.startsWith('__ERROR__')) {
        setLines(prev => [...prev, text.replace('__ERROR__ ', 'Error: ')])
        es.close()
      } else if (text.trim()) {
        setLines(prev => [...prev, text])
      }
    }
    return () => es.close()
  }, [season])

  return (
    <div className="py-4 space-y-1.5">
      {lines.map((l, i) => (
        <p
          key={i}
          className="text-sm text-gray-400 font-mono animate-fade-in"
          style={{ animationDelay: `${i * 30}ms`, opacity: 0, animationFillMode: 'forwards' }}
        >
          {l}
        </p>
      ))}
      <p className="text-sm text-gray-600 font-mono animate-pulse">▌</p>
    </div>
  )
}

function weekLabel(week: number, gameType?: string | null) {
  if (gameType && GAME_TYPE_LABELS[gameType]) return GAME_TYPE_LABELS[gameType]
  return `Week ${week}`
}

function MiniGameRow({ game }: { game: Game }) {
  const navigate = useNavigate()
  const finished = game.away_score !== null && game.home_score !== null
  const awayWon = finished && game.away_score! > game.home_score!
  const homeWon = finished && game.home_score! > game.away_score!

  return (
    <div
      onClick={() => navigate(`/games/${game.game_id}`, { state: { fromWeek: game.week } })}
      className="flex items-center gap-2 py-1.5 px-3 rounded-lg hover:bg-gray-800 cursor-pointer transition-colors group"
    >
      {/* Away */}
      <Link to={`/teams/${game.away_team}`} onClick={e => e.stopPropagation()} className={`flex items-center gap-1.5 group/logo shrink-0 ${awayWon ? 'text-white' : 'text-gray-500'}`}>
        <img src={teamLogoUrl(game.away_team)} alt={game.away_team} className={`w-5 h-5 object-contain pointer-events-none transition-all group-hover/logo:scale-110 group-hover/logo:opacity-100 ${awayWon ? '' : 'opacity-40'}`} />
        <span className="text-xs font-medium w-7 group-hover/logo:text-indigo-400 transition-colors">{game.away_team}</span>
      </Link>

      {/* Score or @ */}
      <div className="flex-1 flex items-center justify-center gap-1">
        {finished ? (
          <>
            <span className={`text-sm font-bold tabular-nums ${awayWon ? 'text-indigo-400' : 'text-gray-500'}`}>{game.away_score}</span>
            <span className="text-gray-700 text-xs">–</span>
            <span className={`text-sm font-bold tabular-nums ${homeWon ? 'text-indigo-400' : 'text-gray-500'}`}>{game.home_score}</span>
          </>
        ) : (
          <span className="text-gray-700 text-xs">@</span>
        )}
      </div>

      {/* Home */}
      <Link to={`/teams/${game.home_team}`} onClick={e => e.stopPropagation()} className={`flex items-center gap-1.5 group/logo shrink-0 ${homeWon ? 'text-white' : 'text-gray-500'}`}>
        <span className="text-xs font-medium w-7 text-right group-hover/logo:text-indigo-400 transition-colors">{game.home_team}</span>
        <img src={teamLogoUrl(game.home_team)} alt={game.home_team} className={`w-5 h-5 object-contain pointer-events-none transition-all group-hover/logo:scale-110 group-hover/logo:opacity-100 ${homeWon ? '' : 'opacity-40'}`} />
      </Link>
    </div>
  )
}

function WeekCard({ group, onExpand }: { group: WeekGroup; onExpand: () => void }) {
  const preview = group.games.slice(0, 5)
  const rest = group.games.length - preview.length

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <button
        onClick={onExpand}
        className="w-full flex items-center justify-between px-4 py-3 border-b border-gray-800 hover:bg-gray-800/60 transition-colors"
      >
        <span className="font-semibold text-white">{weekLabel(group.week, group.games[0]?.game_type)}</span>
        <span className="text-xs text-gray-500">{group.games.length} games ›</span>
      </button>
      <div className="py-1.5 px-0">
        {preview.map(g => <MiniGameRow key={g.game_id} game={g} />)}
        {rest > 0 && (
          <button onClick={onExpand} className="w-full text-xs text-gray-600 hover:text-gray-400 py-2 transition-colors">
            +{rest} more
          </button>
        )}
      </div>
    </div>
  )
}

function GameCard({ game }: { game: Game }) {
  const navigate = useNavigate()
  const finished = game.away_score !== null && game.home_score !== null
  const awayWon = finished && game.away_score! > game.home_score!
  const homeWon = finished && game.home_score! > game.away_score!

  return (
    <div
      onClick={() => navigate(`/games/${game.game_id}`, { state: { fromWeek: game.week } })}
      className="bg-gray-900 border border-gray-800 rounded-xl p-4 cursor-pointer hover:border-indigo-600 transition-colors"
    >
      <div className="text-xs text-gray-500 mb-3">{game.stadium ?? ''}{game.gametime ? ` · ${game.gametime}` : ''}</div>
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1">
          <Link to={`/teams/${game.away_team}`} onClick={e => e.stopPropagation()} className={`inline-flex items-center gap-3 group/logo ${awayWon ? 'text-white' : 'text-gray-400'}`}>
            <img src={teamLogoUrl(game.away_team)} alt={game.away_team} className={`w-10 h-10 object-contain pointer-events-none transition-all group-hover/logo:scale-110 group-hover/logo:opacity-100 ${awayWon ? '' : 'opacity-50'}`} />
            <div>
              <div className="font-bold text-lg leading-tight group-hover/logo:text-indigo-400 transition-colors">{game.away_team}</div>
              {game.away_record && <div className="text-xs text-gray-500">{game.away_record}</div>}
            </div>
          </Link>
          {finished && <div className={`text-2xl font-bold mt-0.5 ${awayWon ? 'text-indigo-400' : 'text-gray-500'}`}>{game.away_score}</div>}
        </div>
        <span className="text-gray-700 text-xs">@</span>
        <div className="flex-1 flex justify-end">
          <Link to={`/teams/${game.home_team}`} onClick={e => e.stopPropagation()} className={`inline-flex items-center gap-3 group/logo ${homeWon ? 'text-white' : 'text-gray-400'}`}>
            <div className="text-right">
              <div className="font-bold text-lg leading-tight group-hover/logo:text-indigo-400 transition-colors">{game.home_team}</div>
              {game.home_record && <div className="text-xs text-gray-500">{game.home_record}</div>}
              {finished && <div className={`text-2xl font-bold mt-0.5 ${homeWon ? 'text-indigo-400' : 'text-gray-500'}`}>{game.home_score}</div>}
            </div>
            <img src={teamLogoUrl(game.home_team)} alt={game.home_team} className={`w-10 h-10 object-contain pointer-events-none transition-all group-hover/logo:scale-110 group-hover/logo:opacity-100 ${homeWon ? '' : 'opacity-50'}`} />
          </Link>
        </div>
      </div>
    </div>
  )
}

type TeamRecord = { w: number; l: number; t: number }

function computeStandings(schedule: WeekGroup[]): Record<string, TeamRecord> {
  const records: Record<string, TeamRecord> = {}
  for (const group of schedule) {
    for (const g of group.games) {
      if (g.away_score === null || g.home_score === null) continue
      records[g.away_team] ??= { w: 0, l: 0, t: 0 }
      records[g.home_team] ??= { w: 0, l: 0, t: 0 }
      if (g.away_score > g.home_score) { records[g.away_team].w++; records[g.home_team].l++ }
      else if (g.home_score > g.away_score) { records[g.home_team].w++; records[g.away_team].l++ }
      else { records[g.away_team].t++; records[g.home_team].t++ }
    }
  }
  return records
}

function winPct(r: TeamRecord) {
  const played = r.w + r.l + r.t
  return played === 0 ? 0 : (r.w + r.t * 0.5) / played
}

function DivisionCard({ conf, div, teams, records }: { conf: string; div: string; teams: string[]; records: Record<string, TeamRecord> }) {
  const sorted = [...teams].sort((a, b) => {
    const ra = records[a] ?? { w: 0, l: 0, t: 0 }
    const rb = records[b] ?? { w: 0, l: 0, t: 0 }
    return winPct(rb) - winPct(ra)
  })
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-bold text-white uppercase tracking-wider">{conf} {div}</span>
        <div className="flex gap-4 text-xs text-gray-600 font-medium">
          <span className="w-6 text-center">W</span>
          <span className="w-6 text-center">L</span>
          <span className="w-8 text-center">PCT</span>
        </div>
      </div>
      <div className="divide-y divide-gray-800/60">
        {sorted.map((team, i) => {
          const r = records[team] ?? { w: 0, l: 0, t: 0 }
          const pct = winPct(r)
          const isLeader = i === 0
          return (
            <Link key={team} to={`/teams/${team}`} className={`flex items-center gap-2 px-4 py-2 hover:bg-gray-800/50 transition-colors ${isLeader ? 'bg-gray-800/30' : ''}`}>
              <span className={`text-xs font-bold w-4 shrink-0 ${isLeader ? 'text-indigo-400' : 'text-gray-700'}`}>{i + 1}</span>
              <img src={teamLogoUrl(team)} alt={team} className="w-6 h-6 object-contain shrink-0" />
              <span className={`flex-1 text-sm ${isLeader ? 'text-white font-medium' : 'text-gray-400'}`}>{team}</span>
              <div className="flex gap-4 text-xs tabular-nums">
                <span className="w-6 text-center text-gray-300">{r.w}</span>
                <span className="w-6 text-center text-gray-500">{r.l}</span>
                <span className="w-8 text-center text-gray-500">{pct.toFixed(3).replace(/^0/, '')}</span>
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}

function Standings({ schedule }: { schedule: WeekGroup[] }) {
  const records = computeStandings(schedule)
  return (
    <div className="mb-2">
      <h2 className="text-lg font-bold text-white mb-4">Standings</h2>
      {Object.entries(CONFERENCES).map(([conf, divisions]) => (
        <div key={conf} className="mb-5">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-sm font-bold text-indigo-400 uppercase tracking-widest">{conf}</span>
            <div className="flex-1 h-px bg-gray-800" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {Object.entries(divisions).map(([div, teams]) => (
              <DivisionCard key={div} conf={conf} div={div} teams={teams} records={records} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function SchedulePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [seasons, setSeasons] = useState<SeasonEntry[]>([])
  const [season, setSeason] = useState<number | null>(() => {
    const s = searchParams.get('season')
    return s ? Number(s) : null
  })
  const [schedule, setSchedule] = useState<WeekGroup[]>([])
  const [scheduleLoading, setScheduleLoading] = useState(false)
  const [selectedWeek, setSelectedWeek] = useState<number | null>(() => {
    const w = searchParams.get('week')
    return w ? Number(w) : null
  })

  // Sync season + week whenever URL params change
  useEffect(() => {
    const s = searchParams.get('season')
    const w = searchParams.get('week')
    if (s) setSeason(Number(s))
    setSelectedWeek(w ? Number(w) : null)
  }, [searchParams.toString()])

  // Poll seasons until nothing is loading
  useEffect(() => {
    function fetchSeasons() {
      api.seasons().then(updated => {
        setSeasons(updated)
        setSeason(prev => {
          if (prev !== null) return prev
          const first = updated.find(s => s.status === 'loaded')
          return first ? first.season : null
        })
      }).catch(() => {})
    }
    fetchSeasons()
    const interval = setInterval(() => {
      fetchSeasons()
      if (!seasons.some(s => s.status === 'loading')) clearInterval(interval)
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const currentSeasonStatus = seasons.find(s => s.season === season)?.status

  // Clear schedule data when season changes
  useEffect(() => {
    setSchedule([])
  }, [season])

  // Fetch schedule once season is confirmed loaded (or unknown — optimistic fetch)
  useEffect(() => {
    if (season === null) return
    if (currentSeasonStatus === 'loading' || currentSeasonStatus === 'available' || currentSeasonStatus === 'error') return
    setScheduleLoading(true)
    api.schedule(season)
      .then(setSchedule)
      .catch(() => setSchedule([]))
      .finally(() => setScheduleLoading(false))
  }, [season, currentSeasonStatus])

  function handleSeasonChange(year: number) {
    const entry = seasons.find(s => s.season === year)
    if (!entry || entry.status === 'available' || entry.status === 'error') {
      api.loadSeason(year).then(() => {
        setSeasons(prev => prev.map(s => s.season === year ? { ...s, status: 'loading' } : s))
      }).catch(() => {})
    }
    setSeason(year)
    setSearchParams({ season: String(year) })
  }

  const selectedGroup = schedule.find(g => g.week === selectedWeek)
  const isSeasonLoading = currentSeasonStatus === 'loading'

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8">

        {/* Header */}
        <div className="mb-8">
          {/* Nav row */}
          <div className="flex items-center gap-2 mb-5">
            <button
              onClick={() => navigate('/?season=2025')}
              className="text-gray-500 hover:text-white transition-colors p-1 rounded-md hover:bg-gray-800"
              title="Home"
            >
              <HomeIcon />
            </button>
            <span className="text-gray-700">/</span>
            <span className="text-gray-400 text-sm">{season}</span>
            {selectedWeek !== null && (
              <>
                <span className="text-gray-700">/</span>
                <span className="text-gray-400 text-sm">{weekLabel(selectedWeek, selectedGroup?.games[0]?.game_type)}</span>
              </>
            )}
            {selectedWeek !== null && (
              <button
                onClick={() => setSearchParams({ season: String(season) })}
                className="ml-auto flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-2 transition-colors"
              >
                ← Back
              </button>
            )}
          </div>

          {/* Title row */}
          <div className="flex items-end justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">
                {selectedWeek !== null ? weekLabel(selectedWeek, selectedGroup?.games[0]?.game_type) : `${season} Season`}
              </h1>
              <p className="text-gray-500 text-sm mt-0.5">
                {selectedWeek !== null ? `${season} NFL Season` : 'Select a week to view games'}
              </p>
            </div>

            {selectedWeek === null && (
              <div className="relative">
                <select
                  value={season ?? ''}
                  onChange={e => handleSeasonChange(Number(e.target.value))}
                  disabled={seasons.length === 0}
                  className="appearance-none bg-gray-800 border border-gray-700 text-white text-sm rounded-lg pl-3 pr-8 py-2 focus:outline-none focus:border-indigo-500 disabled:opacity-50 cursor-pointer hover:border-gray-500 transition-colors"
                >
                  {seasons.length === 0 && <option value="">Loading…</option>}
                  {seasons.map(s => (
                    <option key={s.season} value={s.season} className="bg-gray-900">{s.season}</option>
                  ))}
                </select>
                <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">▾</span>
              </div>
            )}
          </div>
        </div>

        {/* Loading state */}
        {isSeasonLoading && season !== null && (
          <IngestProgress
            season={season}
            onDone={() => {
              api.seasons().then(setSeasons)
              api.schedule(season).then(setSchedule).catch(() => setSchedule([]))
            }}
          />
        )}

        {/* Week detail view */}
        {!isSeasonLoading && selectedWeek !== null && selectedGroup && (() => {
          const byTime: Record<string, Game[]> = {}
          for (const g of selectedGroup.games) {
            const slot = g.gametime ?? 'TBD'
            ;(byTime[slot] ??= []).push(g)
          }
          const formatTime = (t: string) => {
            if (t === 'TBD') return 'TBD'
            const [h, m] = t.split(':').map(Number)
            const ampm = h >= 12 ? 'PM' : 'AM'
            const hour = h % 12 || 12
            return `${hour}:${String(m).padStart(2, '0')} ${ampm} ET`
          }
          return (
            <div className="space-y-6">
              {Object.entries(byTime).map(([slot, games]) => (
                <div key={slot}>
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-sm font-semibold text-gray-400">{formatTime(slot)}</span>
                    <div className="flex-1 h-px bg-gray-800" />
                    <span className="text-xs text-gray-600">{games.length} game{games.length > 1 ? 's' : ''}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {games.map(g => <GameCard key={g.game_id} game={g} />)}
                  </div>
                </div>
              ))}
            </div>
          )
        })()}

        {/* Season overview */}
        {!isSeasonLoading && selectedWeek === null && (
          scheduleLoading
            ? <p className="text-gray-500">Loading schedule…</p>
            : <>
                {schedule.length > 0 && <Standings schedule={schedule} />}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-8">
                  {schedule.map(group => (
                    <WeekCard key={group.week} group={group} onExpand={() => setSearchParams({ season: String(season), week: String(group.week) })} />
                  ))}
                </div>
              </>
        )}

      </div>
    </div>
  )
}
