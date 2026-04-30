import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../api'
import type { TeamProfile, TeamGame, TeamLeader, SeasonEntry } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'

const GAME_TYPE_LABELS: Record<string, string> = { WC: 'Wild Card', DIV: 'Divisional', CON: 'Conference', SB: 'Super Bowl' }
function weekLabel(week: number, gameType?: string | null) {
  if (gameType && GAME_TYPE_LABELS[gameType]) return GAME_TYPE_LABELS[gameType]
  return `Wk ${week}`
}

function gameResult(g: TeamGame, team: string): 'W' | 'L' | 'T' | null {
  const isAway = g.away_team === team
  const ts = isAway ? g.away_score : g.home_score
  const os = isAway ? g.home_score : g.away_score
  if (ts === null || os === null) return null
  return ts > os ? 'W' : ts < os ? 'L' : 'T'
}

function computeRecord(games: TeamGame[], team: string) {
  let w = 0, l = 0, t = 0
  for (const g of games) {
    const r = gameResult(g, team)
    if (r === 'W') w++; else if (r === 'L') l++; else if (r === 'T') t++
  }
  return { w, l, t, label: t > 0 ? `${w}-${l}-${t}` : `${w}-${l}` }
}

function sv(n: number | null | undefined) { return !n || n === 0 ? '—' : String(n) }
function pct(a: number, b: number) { return b === 0 ? '—' : (a / b * 100).toFixed(1) + '%' }
function avg(y: number, c: number) { return c === 0 ? '—' : (y / c).toFixed(1) }

// ── Schedule panel ──────────────────────────────────────────────────────────

function SchedulePanel({ profile }: { profile: TeamProfile }) {
  return (
    <div className="overflow-y-auto divide-y divide-gray-800/60 flex-1 min-h-0">
      {profile.games.map(g => {
        const isAway = g.away_team === profile.team
        const opponent = isAway ? g.home_team : g.away_team
        const teamScore = isAway ? g.away_score : g.home_score
        const oppScore = isAway ? g.home_score : g.away_score
        const result = gameResult(g, profile.team)
        const finished = teamScore !== null && oppScore !== null
        const resultColor = result === 'W' ? 'text-green-400' : result === 'L' ? 'text-red-400' : 'text-gray-400'
        return (
          <Link
            key={g.game_id}
            to={`/games/${g.game_id}`}
            className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800/50 transition-colors group"
          >
            <span className="text-xs text-gray-600 w-14 shrink-0">{weekLabel(g.week, (g as any).game_type)}</span>
            <img src={teamLogoUrl(opponent)} alt={opponent} className="w-5 h-5 object-contain shrink-0 opacity-60 group-hover:opacity-100 transition-opacity" />
            <span className="text-sm text-gray-400 flex-1 group-hover:text-white transition-colors">
              {isAway ? '@' : 'vs'} {opponent}
            </span>
            {finished ? (
              <>
                <span className={`text-xs font-bold w-4 text-center ${resultColor}`}>{result}</span>
                <span className="text-xs tabular-nums text-gray-500 w-12 text-right">{teamScore}–{oppScore}</span>
              </>
            ) : (
              <span className="text-xs text-gray-700 w-16 text-right">{g.gameday}</span>
            )}
          </Link>
        )
      })}
    </div>
  )
}

// ── Leaders panel ────────────────────────────────────────────────────────────

const LEADERS_PREVIEW = 3

interface LeaderRowProps {
  player: TeamLeader
  primary: { value: string; label: string }
  secondary: string
}
function LeaderRow({ player, primary, secondary }: LeaderRowProps) {
  return (
    <Link to={`/players/${player.player_id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800/50 transition-colors group">
      {player.headshot_url
        ? <img src={player.headshot_url} alt={player.player_name} className="w-8 h-8 rounded-full object-cover shrink-0 opacity-80 group-hover:opacity-100 transition-opacity" />
        : <div className="w-8 h-8 rounded-full bg-gray-800 shrink-0 flex items-center justify-center text-xs text-gray-600">#</div>
      }
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-gray-200 truncate group-hover:text-white transition-colors">{player.player_name}</div>
        <div className="text-xs text-gray-600">{player.position ?? '—'} · {player.games_played}G</div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-base font-bold text-white tabular-nums">{primary.value} <span className="text-xs font-normal text-gray-500">{primary.label}</span></div>
        <div className="text-xs text-gray-500 tabular-nums">{secondary}</div>
      </div>
    </Link>
  )
}

function LeaderSection({ title, rows }: { title: string; rows: React.ReactNode[] }) {
  if (!rows.length) return null
  return (
    <div>
      <div className="px-4 py-1.5 bg-gray-800/40 border-t border-gray-800">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">{title}</span>
      </div>
      {rows}
    </div>
  )
}

function LeadersPanel({ leaders, onViewFull }: { leaders: TeamLeader[]; onViewFull: () => void }) {
  const passers   = leaders.filter(p => p.attempts >= 50).sort((a, b) => b.pass_yards - a.pass_yards).slice(0, LEADERS_PREVIEW)
  const rushers   = leaders.filter(p => p.carries >= 20).sort((a, b) => b.rush_yards - a.rush_yards).slice(0, LEADERS_PREVIEW)
  const receivers = leaders.filter(p => p.targets >= 10).sort((a, b) => b.rec_yards - a.rec_yards).slice(0, LEADERS_PREVIEW)
  const defenders = leaders
    .filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
    .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles))
    .slice(0, LEADERS_PREVIEW)

  return (
    <div>
      <LeaderSection title="Passing" rows={passers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.pass_yards), label: 'YDS' }}
          secondary={`${sv(p.pass_tds)} TD · ${sv(p.interceptions_thrown)} INT · ${pct(p.completions, p.attempts)}`}
        />
      ))} />
      <LeaderSection title="Rushing" rows={rushers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.rush_yards), label: 'YDS' }}
          secondary={`${sv(p.carries)} CAR · ${avg(p.rush_yards, p.carries)} YPC · ${sv(p.rush_tds)} TD`}
        />
      ))} />
      <LeaderSection title="Receiving" rows={receivers.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.rec_yards), label: 'YDS' }}
          secondary={`${sv(p.receptions)}/${sv(p.targets)} REC · ${avg(p.rec_yards, p.receptions)} YPR · ${sv(p.rec_tds)} TD`}
        />
      ))} />
      <LeaderSection title="Defense" rows={defenders.map(p => (
        <LeaderRow key={p.player_id} player={p}
          primary={{ value: sv(p.solo_tackles + p.assist_tackles), label: 'TKL' }}
          secondary={`${sv(p.sacks)} SCK · ${sv(p.def_interceptions)} INT · ${sv(p.pass_breakups)} PBU`}
        />
      ))} />
      <button
        onClick={onViewFull}
        className="w-full text-xs text-indigo-400 hover:text-indigo-300 py-2.5 border-t border-gray-800 transition-colors font-medium"
      >
        Full season stats →
      </button>
    </div>
  )
}

// ── Full stats modal ─────────────────────────────────────────────────────────

function FullStatsTable({ title, headers, rows }: { title: string; headers: string[]; rows: React.ReactNode[] }) {
  if (!rows.length) return null
  return (
    <div className="mb-8">
      <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-3 px-1">{title}</h3>
      <div className="overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 text-xs bg-gray-800/60 border-b border-gray-800">
              {headers.map((h, i) => (
                <th key={h} className={`py-2.5 px-3 font-medium whitespace-nowrap ${i === 0 ? '' : 'text-right'}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
  )
}

function td(val: string | number, cls = '') {
  return <td className={`py-2 px-3 text-right tabular-nums text-gray-300 ${cls}`}>{val}</td>
}

function FullStatsModal({ profile, onClose }: { profile: TeamProfile; onClose: () => void }) {
  const { leaders } = profile
  const passers   = leaders.filter(p => p.attempts >= 1).sort((a, b) => b.pass_yards - a.pass_yards)
  const rushers   = leaders.filter(p => p.carries >= 1).sort((a, b) => b.rush_yards - a.rush_yards)
  const receivers = leaders.filter(p => p.targets >= 1).sort((a, b) => b.rec_yards - a.rec_yards)
  const defenders = leaders
    .filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
    .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles))

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function playerCell(p: TeamLeader) {
    return (
      <td className="py-2 px-3 whitespace-nowrap">
        <Link to={`/players/${p.player_id}`} onClick={onClose} className="text-indigo-400 hover:underline font-medium">
          {p.player_name}
        </Link>
      </td>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-gray-950">
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-900 shrink-0">
        <div className="flex items-center gap-4">
          <img src={teamLogoUrl(profile.team)} alt={profile.team} className="w-8 h-8 object-contain" />
          <div>
            <div className="text-white font-bold text-lg">{teamName(profile.team)} — {profile.season} Season Stats</div>
            <div className="text-gray-500 text-xs">All regular season and playoff games</div>
          </div>
        </div>
        <button onClick={onClose} className="flex items-center gap-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-500 rounded-lg px-4 py-2 transition-colors">
          <span className="text-base leading-none">✕</span> Close
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 max-w-6xl mx-auto w-full">
        <FullStatsTable
          title="Passing"
          headers={['Player', 'G', 'CMP', 'ATT', 'CMP%', 'YDS', 'YPA', 'TD', 'INT', 'SCK']}
          rows={passers.map(p => (
            <tr key={p.player_id} className="border-t border-gray-800/60 hover:bg-gray-800/30">
              {playerCell(p)}
              {td(p.games_played, 'text-gray-500')}
              {td(sv(p.completions))}
              {td(sv(p.attempts))}
              {td(pct(p.completions, p.attempts), 'text-gray-400')}
              {td(sv(p.pass_yards), 'font-semibold text-white')}
              {td(avg(p.pass_yards, p.attempts), 'text-gray-400')}
              {td(sv(p.pass_tds), 'text-green-400')}
              {td(sv(p.interceptions_thrown), 'text-red-400')}
              {td(sv(p.sacks_taken), 'text-gray-500')}
            </tr>
          ))}
        />

        <FullStatsTable
          title="Rushing"
          headers={['Player', 'G', 'CAR', 'YDS', 'YPC', 'TD', 'YDS/G']}
          rows={rushers.map(p => (
            <tr key={p.player_id} className="border-t border-gray-800/60 hover:bg-gray-800/30">
              {playerCell(p)}
              {td(p.games_played, 'text-gray-500')}
              {td(sv(p.carries))}
              {td(sv(p.rush_yards), 'font-semibold text-white')}
              {td(avg(p.rush_yards, p.carries), 'text-gray-400')}
              {td(sv(p.rush_tds), 'text-green-400')}
              {td(avg(p.rush_yards, p.games_played), 'text-gray-400')}
            </tr>
          ))}
        />

        <FullStatsTable
          title="Receiving"
          headers={['Player', 'G', 'TGT', 'REC', 'YDS', 'YPR', 'TD', 'YAC', 'CTH%', 'YDS/G']}
          rows={receivers.map(p => (
            <tr key={p.player_id} className="border-t border-gray-800/60 hover:bg-gray-800/30">
              {playerCell(p)}
              {td(p.games_played, 'text-gray-500')}
              {td(sv(p.targets), 'text-gray-400')}
              {td(sv(p.receptions))}
              {td(sv(p.rec_yards), 'font-semibold text-white')}
              {td(avg(p.rec_yards, p.receptions), 'text-gray-400')}
              {td(sv(p.rec_tds), 'text-green-400')}
              {td(sv(p.yac), 'text-gray-400')}
              {td(pct(p.receptions, p.targets), 'text-gray-400')}
              {td(avg(p.rec_yards, p.games_played), 'text-gray-400')}
            </tr>
          ))}
        />

        <FullStatsTable
          title="Defense"
          headers={['Player', 'G', 'TOT', 'SOLO', 'AST', 'TFL', 'SACK', 'QB HIT', 'INT', 'PBU', 'FF', 'FR']}
          rows={defenders.map(p => (
            <tr key={p.player_id} className="border-t border-gray-800/60 hover:bg-gray-800/30">
              {playerCell(p)}
              {td(p.games_played, 'text-gray-500')}
              {td(sv(p.solo_tackles + p.assist_tackles), 'font-semibold text-white')}
              {td(sv(p.solo_tackles))}
              {td(sv(p.assist_tackles), 'text-gray-400')}
              {td(sv(p.tackles_for_loss), 'text-gray-400')}
              {td(sv(p.sacks), 'text-yellow-400')}
              {td(sv(p.qb_hits), 'text-gray-400')}
              {td(sv(p.def_interceptions), 'text-indigo-400')}
              {td(sv(p.pass_breakups))}
              {td(sv(p.forced_fumbles), 'text-gray-400')}
              {td(sv(p.fumble_recoveries), 'text-gray-400')}
            </tr>
          ))}
        />
      </div>
    </div>
  )
}

// ── Season detail ────────────────────────────────────────────────────────────

function SeasonDetail({ profile }: { profile: TeamProfile }) {
  const [statsOpen, setStatsOpen] = useState(false)
  const { w, l, t, label } = computeRecord(profile.games, profile.team)
  const played = w + l + t

  return (
    <>
      {statsOpen && <FullStatsModal profile={profile} onClose={() => setStatsOpen(false)} />}
      <div className="flex flex-col">
        <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
          <div>
            <div className="text-white font-bold text-xl">{profile.season} Season</div>
            <div className="text-gray-500 text-sm">{played} games · {label}</div>
          </div>
          <button
            onClick={() => setStatsOpen(true)}
            className="text-sm text-indigo-400 hover:text-white bg-indigo-900/30 hover:bg-indigo-800/50 border border-indigo-700/50 rounded-lg px-4 py-2 transition-colors font-medium"
          >
            Full Stats
          </button>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-gray-800">
          <div className="flex flex-col">
            <div className="px-4 py-2 bg-gray-800/20 border-b border-gray-800 shrink-0">
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Schedule</span>
            </div>
            <SchedulePanel profile={profile} />
          </div>
          <div>
            <div className="px-4 py-2 bg-gray-800/20 border-b border-gray-800">
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Leaders</span>
            </div>
            <LeadersPanel leaders={profile.leaders} onViewFull={() => setStatsOpen(true)} />
          </div>
        </div>
      </div>
    </>
  )
}

// ── Season sidebar ───────────────────────────────────────────────────────────

type SeasonStatus = SeasonEntry['status']

function StatusDot({ status }: { status: SeasonStatus }) {
  if (status === 'loading')
    return <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse shrink-0" />
  if (status === 'queued')
    return <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-600 animate-pulse shrink-0" />
  return null
}

function SeasonSidebar({
  profiles, selected, onSelect, seasonStatuses, onQueueSeason,
}: {
  profiles: TeamProfile[]
  selected: number
  onSelect: (season: number) => void
  seasonStatuses: Record<number, SeasonStatus>
  onQueueSeason: (year: number) => void
}) {
  const team = profiles[0]?.team ?? ''
  const profileMap = Object.fromEntries(profiles.map(p => [p.season, p]))

  // Seasons to show: all loaded + queued/loading, sorted newest first
  const inFlight = Object.entries(seasonStatuses)
    .filter(([, s]) => s === 'loading' || s === 'queued')
    .map(([y]) => Number(y))
  const loadedYears = profiles.map(p => p.season)
  const visibleYears = [...new Set([...loadedYears, ...inFlight])].sort((a, b) => b - a)

  // Next available year to queue (oldest loaded - 1, if not already loading)
  const oldest = Math.min(...loadedYears, ...inFlight)
  const nextAvailable = oldest > 1999 ? oldest - 1 : null
  const nextStatus = nextAvailable ? seasonStatuses[nextAvailable] : null
  const canLoadMore = nextAvailable && (!nextStatus || nextStatus === 'available' || nextStatus === 'error')

  return (
    <div className="flex flex-col border border-gray-800 rounded-xl overflow-hidden bg-gray-900 shrink-0 lg:w-40">
      <div className="px-4 py-2.5 border-b border-gray-800 bg-gray-800/40">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Seasons</span>
      </div>
      <div className="overflow-y-auto">
        {visibleYears.map(year => {
          const profile = profileMap[year]
          const status = seasonStatuses[year] ?? (profile ? 'loaded' : 'available')
          const active = year === selected
          const inProgress = status === 'loading' || status === 'queued'
          const rec = profile ? computeRecord(profile.games, team) : null

          return (
            <button
              key={year}
              onClick={() => profile ? onSelect(year) : undefined}
              disabled={inProgress && !profile}
              className={`w-full text-left px-4 py-3 border-b border-gray-800/60 transition-colors
                ${active ? 'bg-indigo-900/30 border-l-2 border-l-indigo-500' : 'hover:bg-gray-800/60'}
                ${inProgress && !profile ? 'cursor-default' : ''}`}
            >
              <div className="flex items-center gap-1.5">
                <StatusDot status={status} />
                <span className={`text-sm font-bold ${active ? 'text-indigo-300' : inProgress ? 'text-gray-400' : 'text-gray-300'}`}>
                  {year}
                </span>
              </div>
              <div className="text-xs text-gray-600 mt-0.5">
                {inProgress ? (status === 'loading' ? 'Loading…' : 'Queued') : rec ? rec.label : ''}
              </div>
            </button>
          )
        })}
      </div>
      {canLoadMore && (
        <button
          onClick={() => onQueueSeason(nextAvailable!)}
          className="text-xs text-gray-600 hover:text-gray-300 py-2.5 border-t border-gray-800 transition-colors"
        >
          + {nextAvailable}
        </button>
      )}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

const CURRENT_SEASON = 2025
const FIRST_SEASON = 1999
const INITIAL_SEASONS = 3
const AUTO_QUEUE = 2  // queue this many unloaded seasons beyond initial fetch

export default function TeamPage() {
  const { teamAbbrev } = useParams<{ teamAbbrev: string }>()
  const navigate = useNavigate()
  const [profiles, setProfiles] = useState<TeamProfile[]>([])
  const [selectedSeason, setSelectedSeason] = useState<number>(CURRENT_SEASON)
  const [initialLoading, setInitialLoading] = useState(true)
  const [seasonStatuses, setSeasonStatuses] = useState<Record<number, SeasonStatus>>({})

  // Load initial seasons + global season list on mount
  useEffect(() => {
    if (!teamAbbrev) return
    let cancelled = false
    setProfiles([])
    setInitialLoading(true)

    const years = Array.from({ length: INITIAL_SEASONS }, (_, i) => CURRENT_SEASON - i)

    Promise.all([
      ...years.map(y => api.team(teamAbbrev, y).catch(() => null)),
      api.seasons(),
    ]).then(results => {
      if (cancelled) return
      const allSeasons = results.pop() as SeasonEntry[]
      const fetched = (results as (TeamProfile | null)[]).filter(Boolean) as TeamProfile[]
      const statuses = Object.fromEntries(allSeasons.map(s => [s.season, s.status])) as Record<number, SeasonStatus>

      setProfiles(fetched.sort((a, b) => b.season - a.season))
      setSeasonStatuses(statuses)
      setSelectedSeason(fetched[0]?.season ?? CURRENT_SEASON)
      setInitialLoading(false)

      // Auto-queue a couple more recent seasons that aren't loaded yet
      let queued = 0
      for (let y = CURRENT_SEASON - INITIAL_SEASONS; y >= FIRST_SEASON && queued < AUTO_QUEUE; y--) {
        if (statuses[y] === 'available' || statuses[y] === 'error') {
          api.loadSeason(y)
          statuses[y] = 'queued'
          queued++
        }
      }
      if (queued > 0) setSeasonStatuses({ ...statuses })
    })

    return () => { cancelled = true }
  }, [teamAbbrev])

  // Poll while any season is in-flight; fetch team profile when one completes
  useEffect(() => {
    const anyInFlight = Object.values(seasonStatuses).some(s => s === 'loading' || s === 'queued')
    if (!anyInFlight || !teamAbbrev) return

    const loadedYears = new Set(profiles.map(p => p.season))

    const interval = setInterval(async () => {
      const allSeasons = await api.seasons().catch(() => [] as SeasonEntry[])
      const updated = Object.fromEntries(allSeasons.map(s => [s.season, s.status])) as Record<number, SeasonStatus>
      setSeasonStatuses(updated)

      // Fetch team profile for any season that just finished loading
      const newlyLoaded = allSeasons.filter(s => !loadedYears.has(s.season) && s.status === 'loaded')
      for (const s of newlyLoaded) {
        api.team(teamAbbrev, s.season)
          .then(p => setProfiles(prev => [...prev.filter(x => x.season !== p.season), p].sort((a, b) => b.season - a.season)))
          .catch(() => {})
      }

      if (!allSeasons.some(s => s.status === 'loading' || s.status === 'queued')) {
        clearInterval(interval)
      }
    }, 4000)

    return () => clearInterval(interval)
  }, [teamAbbrev, seasonStatuses])

  function handleQueueSeason(year: number) {
    api.loadSeason(year).catch(() => {})
    setSeasonStatuses(prev => ({ ...prev, [year]: 'queued' }))
  }

  if (initialLoading) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Loading...</p></div>
  if (!profiles.length || !teamAbbrev) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Team not found.</p></div>

  const allGames = profiles.flatMap(p => p.games)
  const allTime = computeRecord(allGames, teamAbbrev)
  const activeProfile = profiles.find(p => p.season === selectedSeason) ?? profiles[0]

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">

        <div className="flex items-center gap-2 mb-5">
          <button onClick={() => navigate('/?season=2025')} className="text-gray-500 hover:text-white transition-colors p-1 rounded-md hover:bg-gray-800" title="Home">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7A1 1 0 003 11h1v6a1 1 0 001 1h4v-4h2v4h4a1 1 0 001-1v-6h1a1 1 0 00.707-1.707l-7-7z" />
            </svg>
          </button>
          <span className="text-gray-700">/</span>
          <span className="text-gray-400 text-sm">{teamName(teamAbbrev)}</span>
          <button onClick={() => navigate(-1)} className="ml-auto flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-2 transition-colors">
            ← Back
          </button>
        </div>

        <div className="flex items-center gap-5 mb-8">
          <img src={teamLogoUrl(teamAbbrev)} alt={teamAbbrev} className="w-20 h-20 object-contain shrink-0" />
          <div>
            <h1 className="text-3xl font-bold text-white leading-tight">{teamName(teamAbbrev)}</h1>
            <div className="text-gray-400 mt-1">
              {profiles.length} season{profiles.length !== 1 ? 's' : ''} loaded ·{' '}
              <span className="text-white font-semibold">{allTime.label}</span>
              <span className="text-gray-600 text-xs ml-2">{allTime.w + allTime.l + allTime.t} games</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col lg:flex-row gap-4 items-start">
          <SeasonSidebar
            profiles={profiles}
            selected={activeProfile.season}
            onSelect={setSelectedSeason}
            seasonStatuses={seasonStatuses}
            onQueueSeason={handleQueueSeason}
          />
          <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <SeasonDetail profile={activeProfile} />
          </div>
        </div>

      </div>
    </div>
  )
}
