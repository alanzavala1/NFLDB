import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { Game, LeagueLeader, SearchResult, SeasonEntry, WeekGroup } from '../api'
import { teamLogoUrl, teamName } from '../utils/teams'
import Nav, { backBtnCls } from '../components/Nav'
import { PlayoffBracket } from '../components/PlayoffBracket'
import { PAST_AWARDS, SB_CHAMPS } from '../utils/awards'

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


function dayOfWeek(gameday: string): number {
  const [y, m, d] = gameday.split('-').map(Number)
  return new Date(y, m - 1, d).getDay()
}

function primetimeBadge(gameday: string, gametime: string | null): string | null {
  const dow = dayOfWeek(gameday)
  const hour = gametime ? parseInt(gametime.split(':')[0], 10) : 0
  if (dow === 4) return 'TNF'
  if (dow === 1) return 'MNF'
  if (dow === 0 && hour >= 20) return 'SNF'
  if (dow === 6) return 'SAT'
  return null
}

function formatTimeShort(t: string | null) {
  if (!t || t === 'TBD') return 'TBD'
  const [h, m] = t.split(':').map(Number)
  const ampm = h >= 12 ? 'PM' : 'AM'
  const hour = h % 12 || 12
  return `${hour}:${String(m).padStart(2, '0')} ${ampm}`
}

function Chip({ label, tone }: { label: string; tone: 'indigo' | 'amber' | 'rose' | 'emerald' | 'gray' }) {
  const tones = {
    indigo:  'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
    amber:   'bg-amber-500/15 text-amber-300 border-amber-500/30',
    rose:    'bg-rose-500/15 text-rose-300 border-rose-500/30',
    emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    gray:    'bg-gray-700/40 text-gray-400 border-gray-600/40',
  }
  return <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border whitespace-nowrap ${tones[tone]}`}>{label}</span>
}

function formatSpread(game: Game): string | null {
  if (game.spread_line === null) return null
  if (game.spread_line === 0) return 'PICK'
  // nflfastR convention: spread_line > 0 means home is favored
  const fav = game.spread_line > 0 ? game.home_team : game.away_team
  return `${fav} -${Math.abs(game.spread_line)}`
}

function GameCard({ game }: { game: Game }) {
  const navigate = useNavigate()
  const finished = game.away_score !== null && game.home_score !== null
  const awayWon = finished && game.away_score! > game.home_score!
  const homeWon = finished && game.home_score! > game.away_score!
  const margin = finished ? Math.abs(game.away_score! - game.home_score!) : null
  const total = finished ? (game.away_score! + game.home_score!) : null
  const ptBadge = primetimeBadge(game.gameday, game.gametime)
  const spread = formatSpread(game)

  const rows = [
    { team: game.away_team, record: game.away_record, qb: game.away_qb_name, score: game.away_score, won: awayWon },
    { team: game.home_team, record: game.home_record, qb: game.home_qb_name, score: game.home_score, won: homeWon },
  ]

  return (
    <div
      onClick={() => navigate(`/games/${game.game_id}`, { state: { fromWeek: game.week } })}
      className="bg-gray-900 border border-gray-800 rounded-xl p-4 cursor-pointer hover:border-indigo-600 hover:bg-gray-900/80 transition-all"
    >
      {/* Top: chips left, time/final right */}
      <div className="flex items-center justify-between gap-2 mb-3 min-h-[20px]">
        <div className="flex items-center gap-1.5 flex-wrap">
          {ptBadge && <Chip label={ptBadge} tone="indigo" />}
          {game.div_game === 1 && <Chip label="DIV" tone="amber" />}
          {game.overtime === 1 && <Chip label="OT" tone="rose" />}
        </div>
        <span className="text-[11px] text-gray-500 font-medium shrink-0">
          {finished ? 'Final' : formatTimeShort(game.gametime)}
        </span>
      </div>

      {/* Teams */}
      <div className="space-y-2">
        {rows.map((t, i) => (
          <div key={i} className={`flex items-center gap-3 transition-opacity ${finished && !t.won ? 'opacity-55' : ''}`}>
            <Link
              to={`/teams/${t.team}`}
              onClick={e => e.stopPropagation()}
              className="shrink-0 transition-transform hover:scale-110"
              aria-label={`View ${t.team}`}
            >
              <img src={teamLogoUrl(t.team)} alt={t.team} className="w-10 h-10 object-contain" />
            </Link>
            <div className="flex-1 min-w-0">
              <Link
                to={`/teams/${t.team}`}
                onClick={e => e.stopPropagation()}
                className={`font-bold text-base leading-tight truncate inline-block hover:text-indigo-400 transition-colors ${t.won ? 'text-white' : 'text-gray-300'}`}
              >
                {t.team}
              </Link>
              <div className="text-[11px] text-gray-600 leading-tight truncate mt-0.5">
                {t.record && <span>{t.record}</span>}
                {!finished && t.qb && <span>{t.record ? ' · ' : ''}{t.qb}</span>}
              </div>
            </div>
            {finished && (
              <span className={`text-2xl font-black tabular-nums shrink-0 ${t.won ? 'text-white' : 'text-gray-500'}`}>{t.score}</span>
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="mt-3 pt-2.5 border-t border-gray-800/60 flex items-center justify-between text-[11px] gap-2">
        <span className="text-gray-600 truncate">{game.stadium ?? ''}</span>
        <span className="text-gray-500 shrink-0">
          {finished ? (
            <>
              <span className="text-gray-600">Margin </span>
              <span className="text-gray-300 font-semibold tabular-nums">{margin}</span>
              <span className="text-gray-700 mx-1.5">·</span>
              <span className="text-gray-600">Total </span>
              <span className="text-gray-300 font-semibold tabular-nums">{total}</span>
            </>
          ) : (
            <>
              {spread && <span className="text-gray-300 font-semibold">{spread}</span>}
              {spread && game.total_line !== null && <span className="text-gray-700 mx-1.5">·</span>}
              {game.total_line !== null && <span className="text-gray-300 font-semibold tabular-nums">O/U {game.total_line}</span>}
              {!spread && game.total_line === null && <span className="text-gray-700">—</span>}
            </>
          )}
        </span>
      </div>
    </div>
  )
}

function WeekHighlights({ games }: { games: Game[] }) {
  const navigate = useNavigate()
  const finished = games.filter(g => g.away_score !== null && g.home_score !== null)
  const upcoming = games.length - finished.length

  const totalPts = finished.reduce((s, g) => s + (g.away_score ?? 0) + (g.home_score ?? 0), 0)
  const margins = finished.map(g => Math.abs((g.away_score ?? 0) - (g.home_score ?? 0)))
  const avgMargin = margins.length ? margins.reduce((a, b) => a + b, 0) / margins.length : 0
  const otGames = finished.filter(g => g.overtime === 1).length
  const divGames = games.filter(g => g.div_game === 1).length

  const closest = finished.length
    ? [...finished].sort((a, b) => {
        const ma = Math.abs(a.away_score! - a.home_score!)
        const mb = Math.abs(b.away_score! - b.home_score!)
        if (ma !== mb) return ma - mb
        // Tiebreaker: higher combined score wins (more entertaining)
        return (b.away_score! + b.home_score!) - (a.away_score! + a.home_score!)
      })[0]
    : null
  const highest = finished.length
    ? [...finished].sort((a, b) =>
        (b.away_score! + b.home_score!) - (a.away_score! + a.home_score!))[0]
    : null
  const upset = finished
    .filter(g => g.spread_line !== null)
    .reduce<{ game: Game; mag: number; winner: string } | null>((best, g) => {
      const homeWon = g.home_score! > g.away_score!
      const sp = g.spread_line!
      // spread_line > 0 = home favored. Upset = underdog wins.
      let mag = 0
      let winner = ''
      if (homeWon && sp < 0)       { mag = -sp; winner = g.home_team }   // home was underdog
      else if (!homeWon && sp > 0) { mag = sp;  winner = g.away_team }   // away was underdog
      if (mag > (best?.mag ?? 0)) return { game: g, mag, winner }
      return best
    }, null)

  const kpis = [
    { label: 'Games',      value: upcoming > 0 ? `${finished.length}/${games.length}` : String(games.length) },
    { label: 'Total Pts',  value: finished.length ? totalPts.toLocaleString() : '—' },
    { label: 'Avg Margin', value: finished.length ? avgMargin.toFixed(1) : '—' },
    { label: 'OT',         value: finished.length ? String(otGames) : '—' },
    { label: 'Div Games',  value: String(divGames) },
  ]

  type Spotlight = { label: string; tone: 'indigo' | 'amber' | 'emerald' | 'rose'; game: Game; primary: string; sub: string }
  const spotlights: Spotlight[] = []
  if (closest) {
    const cMargin = Math.abs(closest.away_score! - closest.home_score!)
    spotlights.push({
      label: cMargin === 0 ? 'Tied Thriller' : 'Closest Game', tone: 'indigo', game: closest,
      primary: `${closest.away_team} ${closest.away_score} – ${closest.home_score} ${closest.home_team}`,
      sub: `${cMargin === 0 ? 'Tied' : `Margin ${cMargin}`}${closest.overtime === 1 ? ' · OT' : ''}`,
    })
  }
  if (upset && upset.mag >= 2.5) {
    spotlights.push({
      label: 'Biggest Upset', tone: 'amber', game: upset.game,
      primary: `${upset.winner} as +${upset.mag.toFixed(1)} underdog`,
      sub: `${upset.game.away_team} ${upset.game.away_score} – ${upset.game.home_score} ${upset.game.home_team}`,
    })
  }
  if (highest && highest.game_id !== closest?.game_id) {
    spotlights.push({
      label: 'Highest Scoring', tone: 'emerald', game: highest,
      primary: `${(highest.away_score! + highest.home_score!)} pts`,
      sub: `${highest.away_team} ${highest.away_score} – ${highest.home_score} ${highest.home_team}`,
    })
  }

  if (!finished.length && !spotlights.length) return null

  const toneClasses: Record<Spotlight['tone'], string> = {
    indigo:  'border-indigo-500/40 bg-indigo-500/5 hover:bg-indigo-500/10',
    amber:   'border-amber-500/40 bg-amber-500/5 hover:bg-amber-500/10',
    emerald: 'border-emerald-500/40 bg-emerald-500/5 hover:bg-emerald-500/10',
    rose:    'border-rose-500/40 bg-rose-500/5 hover:bg-rose-500/10',
  }
  const toneText: Record<Spotlight['tone'], string> = {
    indigo: 'text-indigo-300', amber: 'text-amber-300', emerald: 'text-emerald-300', rose: 'text-rose-300',
  }

  return (
    <div className="mb-6 space-y-4">
      {/* KPI strip */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
        <div className="grid grid-cols-5 gap-2">
          {kpis.map(k => (
            <div key={k.label} className="text-center">
              <div className="text-xl font-bold text-white tabular-nums leading-tight">{k.value}</div>
              <div className="text-[10px] text-gray-600 uppercase tracking-wider mt-0.5">{k.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Spotlights */}
      {spotlights.length > 0 && (
        <div className={`grid gap-3 ${spotlights.length === 1 ? 'grid-cols-1' : spotlights.length === 2 ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1 sm:grid-cols-3'}`}>
          {spotlights.map(s => (
            <button
              key={s.label}
              onClick={() => navigate(`/games/${s.game.game_id}`, { state: { fromWeek: s.game.week } })}
              className={`text-left border rounded-xl px-4 py-3 transition-colors ${toneClasses[s.tone]}`}
            >
              <div className="flex items-center gap-2 mb-2">
                <img src={teamLogoUrl(s.game.away_team)} className="w-5 h-5 object-contain opacity-70" alt="" />
                <img src={teamLogoUrl(s.game.home_team)} className="w-5 h-5 object-contain opacity-70" alt="" />
                <span className={`text-[10px] font-bold uppercase tracking-wider ml-auto ${toneText[s.tone]}`}>{s.label}</span>
              </div>
              <div className="text-sm font-bold text-white leading-tight">{s.primary}</div>
              <div className="text-[11px] text-gray-500 mt-1">{s.sub}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Home dashboard ───────────────────────────────────────────────────────────

function findCurrentWeek(schedule: WeekGroup[]): number | null {
  const inProgress = schedule.find(w =>
    w.games.some(g => g.away_score !== null) &&
    w.games.some(g => g.away_score === null)
  )
  if (inProgress) return inProgress.week
  const allComplete = schedule.filter(w => w.games.every(g => g.away_score !== null && g.home_score !== null))
  if (allComplete.length) return allComplete[allComplete.length - 1].week
  const firstUpcoming = schedule.find(w => w.games.every(g => g.away_score === null))
  return firstUpcoming?.week ?? null
}

function CurrentWeekSection({ schedule, season }: { schedule: WeekGroup[]; season: number }) {
  const navigate = useNavigate()
  const currentWeek = findCurrentWeek(schedule)
  if (currentWeek == null) return null
  const group = schedule.find(w => w.week === currentWeek)
  if (!group) return null

  const finished = group.games.filter(g => g.away_score !== null).length
  const total = group.games.length
  const status = finished === 0 ? 'Upcoming' : finished === total ? 'Final' : 'In Progress'
  const previewGames = group.games.slice(0, 6)
  const hidden = group.games.length - previewGames.length

  return (
    <section className="mb-10">
      <div className="flex items-end justify-between mb-5 flex-wrap gap-2">
        <div>
          <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">{status}</div>
          <h2 className="text-3xl font-black text-white tracking-tight leading-none mt-1">
            {weekLabel(currentWeek, group.games[0]?.game_type)}
          </h2>
        </div>
        <button
          onClick={() => navigate(`/?season=${season}&week=${currentWeek}`)}
          className="text-xs text-indigo-400 hover:text-indigo-300 font-bold uppercase tracking-wider"
        >
          View all {total} →
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {previewGames.map(g => <GameCard key={g.game_id} game={g} />)}
      </div>
      {hidden > 0 && (
        <button
          onClick={() => navigate(`/?season=${season}&week=${currentWeek}`)}
          className="block w-full text-center text-xs text-gray-500 hover:text-gray-300 mt-3 py-1"
        >
          +{hidden} more this week
        </button>
      )}
    </section>
  )
}

function WeekStoriesSection({ weekGames, seasonGames }: { weekGames: Game[]; seasonGames: Game[] }) {
  const navigate = useNavigate()
  const weekFinished = weekGames.filter(g => g.away_score !== null && g.home_score !== null)
  const seasonFinished = seasonGames.filter(g => g.away_score !== null && g.home_score !== null)
  // If the current week has fewer than 3 finished games (e.g. just the Super Bowl),
  // pull storylines from the whole season so they're not all the same matchup.
  const useSeasonScope = weekFinished.length < 3
  const finished = useSeasonScope ? seasonFinished : weekFinished
  if (finished.length === 0) return null

  const closest = [...finished].sort((a, b) => {
    const ma = Math.abs(a.away_score! - a.home_score!)
    const mb = Math.abs(b.away_score! - b.home_score!)
    if (ma !== mb) return ma - mb
    // Tiebreaker: higher combined score wins (more entertaining)
    return (b.away_score! + b.home_score!) - (a.away_score! + a.home_score!)
  })[0]
  const highest = [...finished].sort((a, b) =>
    (b.away_score! + b.home_score!) - (a.away_score! + a.home_score!)
  )[0]
  const upset = finished
    .filter(g => g.spread_line !== null)
    .reduce<{ game: Game; mag: number; winner: string } | null>((best, g) => {
      const homeWon = g.home_score! > g.away_score!
      const sp = g.spread_line!
      // spread_line > 0 = home favored. Upset = underdog wins.
      let mag = 0; let winner = ''
      if (homeWon && sp < 0)       { mag = -sp; winner = g.home_team }
      else if (!homeWon && sp > 0) { mag = sp;  winner = g.away_team }
      if (mag > (best?.mag ?? 0)) return { game: g, mag, winner }
      return best
    }, null)

  const wkLabel = (g: Game) => useSeasonScope ? `${weekLabel(g.week, g.game_type)} · ` : ''
  type Story = { label: string; tone: 'indigo' | 'emerald' | 'amber'; game: Game; primary: string; sub: string }
  const stories: Story[] = []
  if (closest) {
    const cMargin = Math.abs(closest.away_score! - closest.home_score!)
    stories.push({
      label: cMargin === 0 ? 'Tied Thriller' : 'Closest Game', tone: 'indigo', game: closest,
      primary: `${closest.away_team} ${closest.away_score} – ${closest.home_score} ${closest.home_team}`,
      sub: `${wkLabel(closest)}${cMargin === 0 ? 'Tied' : `Margin ${cMargin}`}${closest.overtime === 1 ? ' · OT' : ''}`,
    })
  }
  if (highest && highest.game_id !== closest?.game_id) {
    stories.push({
      label: 'Highest Scoring', tone: 'emerald', game: highest,
      primary: `${(highest.away_score! + highest.home_score!)} pts`,
      sub: `${wkLabel(highest)}${highest.away_team} ${highest.away_score} – ${highest.home_score} ${highest.home_team}`,
    })
  }
  if (upset && upset.mag >= 2.5 && upset.game.game_id !== closest?.game_id && upset.game.game_id !== highest?.game_id) {
    stories.push({
      label: 'Biggest Upset', tone: 'amber', game: upset.game,
      primary: `${upset.winner} (+${upset.mag.toFixed(1)})`,
      sub: `${wkLabel(upset.game)}${upset.game.away_team} ${upset.game.away_score} – ${upset.game.home_score} ${upset.game.home_team}`,
    })
  }
  if (!stories.length) return null

  const toneCls: Record<Story['tone'], string> = {
    indigo:  'border-indigo-500/40 bg-indigo-500/5 hover:bg-indigo-500/10',
    emerald: 'border-emerald-500/40 bg-emerald-500/5 hover:bg-emerald-500/10',
    amber:   'border-amber-500/40 bg-amber-500/5 hover:bg-amber-500/10',
  }
  const toneTxt: Record<Story['tone'], string> = { indigo: 'text-indigo-300', emerald: 'text-emerald-300', amber: 'text-amber-300' }

  return (
    <section className="mb-10">
      <div className="flex items-end justify-between mb-4">
        <h2 className="text-lg font-black text-white tracking-tight uppercase">
          {useSeasonScope ? 'Season Storylines' : 'Week Storylines'}
        </h2>
        {useSeasonScope && (
          <span className="text-[10px] text-gray-600 uppercase tracking-widest">From the whole season</span>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {stories.map(s => (
          <button
            key={s.label}
            onClick={() => navigate(`/games/${s.game.game_id}`, { state: { fromWeek: s.game.week } })}
            className={`text-left rounded-xl border px-4 py-3 transition-colors ${toneCls[s.tone]}`}
          >
            <div className="flex items-center gap-2 mb-2">
              <img src={teamLogoUrl(s.game.away_team)} className="w-5 h-5 object-contain opacity-70" alt="" />
              <img src={teamLogoUrl(s.game.home_team)} className="w-5 h-5 object-contain opacity-70" alt="" />
              <span className={`text-[10px] font-bold uppercase tracking-widest ml-auto ${toneTxt[s.tone]}`}>{s.label}</span>
            </div>
            <div className="text-sm font-bold text-white leading-tight">{s.primary}</div>
            <div className="text-[11px] text-gray-500 mt-1">{s.sub}</div>
          </button>
        ))}
      </div>
    </section>
  )
}

function TopLeadersStrip({ season }: { season: number }) {
  const [leaders, setLeaders] = useState<LeagueLeader[]>([])
  useEffect(() => {
    api.leaders(season).then(setLeaders).catch(() => {})
  }, [season])
  if (!leaders.length) return null

  const cats: Array<{
    label: string
    stat: string
    filter: (p: LeagueLeader) => boolean
    value: (p: LeagueLeader) => number
    display: (p: LeagueLeader) => string
  }> = [
    { label: 'Passing',   stat: 'YDS', filter: p => p.attempts >= 100, value: p => p.pass_yards, display: p => p.pass_yards.toLocaleString() },
    { label: 'Rushing',   stat: 'YDS', filter: p => p.carries >= 50,   value: p => p.rush_yards, display: p => p.rush_yards.toLocaleString() },
    { label: 'Receiving', stat: 'YDS', filter: p => p.targets >= 20,   value: p => p.rec_yards,  display: p => p.rec_yards.toLocaleString() },
    { label: 'Defense',   stat: 'TKL', filter: p => p.solo_tackles + p.assist_tackles >= 10, value: p => p.solo_tackles + p.assist_tackles, display: p => (p.solo_tackles + p.assist_tackles).toString() },
  ]

  // Compute tops once so we can skip the section entirely if no category qualifies
  const tops = cats.map(c => ({ cat: c, top: leaders.filter(c.filter).sort((a, b) => c.value(b) - c.value(a))[0] }))
  if (tops.every(t => !t.top)) return null

  return (
    <section className="mb-10">
      <div className="flex items-end justify-between mb-4">
        <h2 className="text-lg font-black text-white tracking-tight uppercase">Top of the League</h2>
        <Link to={`/leaders?season=${season}`} className="text-xs text-indigo-400 hover:text-indigo-300 font-bold uppercase tracking-wider">All leaders →</Link>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {tops.map(({ cat: c, top }) => {
          if (!top) return null
          return (
            <Link
              key={c.label}
              to={`/players/${top.player_id}`}
              className="bg-gray-900 border border-gray-800 rounded-xl p-3.5 hover:border-indigo-600 hover:bg-gray-900/70 transition-all"
            >
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2">{c.label}</div>
              <div className="flex items-center gap-2.5">
                {top.headshot_url
                  ? <img src={top.headshot_url} className="w-10 h-10 rounded-full object-cover object-top bg-gray-800 shrink-0" alt="" />
                  : <div className="w-10 h-10 rounded-full bg-gray-800 shrink-0" />
                }
                <div className="min-w-0">
                  <div className="text-sm font-bold text-white truncate">{top.player_name}</div>
                  <div className="text-[11px] text-gray-500 flex items-center gap-1">
                    {top.team && <img src={teamLogoUrl(top.team)} className="w-3 h-3 object-contain opacity-80" alt="" />}
                    <span>{top.team ?? '—'}{top.position ? ` · ${top.position}` : ''}</span>
                  </div>
                </div>
              </div>
              <div className="mt-2.5 flex items-baseline justify-between">
                <span className="text-xl font-black tabular-nums text-white">{c.display(top)}</span>
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-600">{c.stat}</span>
              </div>
            </Link>
          )
        })}
      </div>
    </section>
  )
}

function RecentResultsFeed({ schedule }: { schedule: WeekGroup[] }) {
  const navigate = useNavigate()
  const all = schedule
    .flatMap(w => w.games)
    .filter(g => g.away_score !== null && g.home_score !== null)
    .sort((a, b) => b.gameday.localeCompare(a.gameday))
    .slice(0, 6)
  if (!all.length) return null

  return (
    <section className="mb-10">
      <div className="flex items-end justify-between mb-4">
        <h2 className="text-lg font-black text-white tracking-tight uppercase">Recent Results</h2>
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden divide-y divide-gray-800/60">
        {all.map(g => {
          const awayWon = g.away_score! > g.home_score!
          const homeWon = g.home_score! > g.away_score!
          return (
            <button
              key={g.game_id}
              onClick={() => navigate(`/games/${g.game_id}`, { state: { fromWeek: g.week } })}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800/40 transition-colors text-left"
            >
              <span className="text-[10px] text-gray-600 uppercase tracking-wider w-14 shrink-0">{weekLabel(g.week, g.game_type).replace('Week ', 'Wk ')}</span>
              <div className="flex items-center gap-1.5 flex-1 min-w-0">
                <img src={teamLogoUrl(g.away_team)} className={`w-5 h-5 object-contain shrink-0 ${awayWon ? '' : 'opacity-50'}`} alt="" />
                <span className={`text-sm font-semibold w-9 ${awayWon ? 'text-white' : 'text-gray-500'}`}>{g.away_team}</span>
                <span className={`text-sm font-bold tabular-nums w-7 text-right ${awayWon ? 'text-white' : 'text-gray-500'}`}>{g.away_score}</span>
                <span className="text-gray-700 text-xs mx-0.5">–</span>
                <span className={`text-sm font-bold tabular-nums w-7 ${homeWon ? 'text-white' : 'text-gray-500'}`}>{g.home_score}</span>
                <span className={`text-sm font-semibold w-9 ${homeWon ? 'text-white' : 'text-gray-500'}`}>{g.home_team}</span>
                <img src={teamLogoUrl(g.home_team)} className={`w-5 h-5 object-contain shrink-0 ${homeWon ? '' : 'opacity-50'}`} alt="" />
              </div>
              <span className="text-[10px] text-gray-600 shrink-0">{g.gameday}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function QuickNavStrip({ season, current }: { season: number; current: 'home' | 'weeks' }) {
  const items: { label: string; to: string; active?: boolean }[] = [
    { label: 'Home',      to: `/?season=${season}`,            active: current === 'home' },
    { label: 'All Weeks', to: `/?season=${season}&view=weeks`, active: current === 'weeks' },
    { label: 'Standings', to: `/standings?season=${season}` },
    { label: 'Leaders',   to: `/leaders?season=${season}` },
  ]
  return (
    <div className="flex gap-2 mb-8 flex-wrap">
      {items.map(item => (
        <Link
          key={item.label}
          to={item.to}
          className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors ${
            item.active
              ? 'bg-indigo-600 text-white border border-indigo-500'
              : 'bg-gray-900 text-gray-300 border border-gray-800 hover:border-indigo-500 hover:text-white'
          }`}
        >
          {item.label}
        </Link>
      ))}
    </div>
  )
}

function JumpToWeek({ schedule, season }: { schedule: WeekGroup[]; season: number }) {
  const navigate = useNavigate()
  if (!schedule.length) return null
  return (
    <section className="mb-4">
      <div className="flex items-end justify-between mb-3">
        <h2 className="text-lg font-black text-white tracking-tight uppercase">Jump to Week</h2>
        <Link to={`/?season=${season}&view=weeks`} className="text-xs text-indigo-400 hover:text-indigo-300 font-bold uppercase tracking-wider">
          All weeks
        </Link>
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-3">
        <div className="flex flex-wrap gap-1.5">
          {schedule.map(w => {
            const label = weekLabel(w.week, w.games[0]?.game_type)
            const isPost = w.week >= 19
            return (
              <button
                key={w.week}
                onClick={() => navigate(`/?season=${season}&week=${w.week}`)}
                className={`text-sm font-bold rounded-md px-3 py-1.5 transition-colors ${
                  isPost
                    ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30 hover:bg-amber-500/20'
                    : 'bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700 hover:text-white'
                }`}
                title={label}
              >
                {label.startsWith('Week ') ? `Wk ${w.week}` : label}
              </button>
            )
          })}
        </div>
      </div>
    </section>
  )
}

function WeekTile({ group, season }: { group: WeekGroup; season: number }) {
  const navigate = useNavigate()
  const finished = group.games.filter(g => g.away_score !== null && g.home_score !== null).length
  const total = group.games.length
  const status = finished === 0 ? 'Upcoming' : finished === total ? 'Final' : 'In Progress'
  const statusCls =
    finished === 0 ? 'text-gray-500' :
    finished === total ? 'text-emerald-400' :
    'text-amber-400'
  const previewCount = 4
  const preview = group.games.slice(0, previewCount)
  const more = group.games.length - preview.length

  return (
    <button
      onClick={() => navigate(`/?season=${season}&week=${group.week}`)}
      className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3.5 hover:border-indigo-600 hover:bg-gray-900/70 transition-all text-left flex flex-col"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-base font-black text-white tracking-tight">{weekLabel(group.week, group.games[0]?.game_type)}</span>
        <span className={`text-[10px] font-bold uppercase tracking-widest ${statusCls}`}>{status}</span>
      </div>
      <div className="text-[11px] text-gray-500 mb-2.5">
        {total} {total === 1 ? 'game' : 'games'}{finished > 0 && finished < total ? ` (${finished} final)` : ''}
      </div>
      <div className="space-y-1.5 flex-1">
        {preview.map(g => {
          const awayWon = g.away_score !== null && g.home_score !== null && g.away_score > g.home_score
          const homeWon = g.away_score !== null && g.home_score !== null && g.home_score > g.away_score
          const done = g.away_score !== null && g.home_score !== null
          return (
            <div key={g.game_id} className="flex items-center gap-1.5 text-[11px]">
              <img src={teamLogoUrl(g.away_team)} alt="" className={`w-3.5 h-3.5 object-contain shrink-0 ${done && !awayWon ? 'opacity-50' : ''}`} />
              <span className={`w-8 font-semibold ${done && awayWon ? 'text-white' : 'text-gray-500'}`}>{g.away_team}</span>
              <span className="text-gray-700">@</span>
              <img src={teamLogoUrl(g.home_team)} alt="" className={`w-3.5 h-3.5 object-contain shrink-0 ${done && !homeWon ? 'opacity-50' : ''}`} />
              <span className={`w-8 font-semibold ${done && homeWon ? 'text-white' : 'text-gray-500'}`}>{g.home_team}</span>
              {done && (
                <span className="ml-auto tabular-nums text-gray-400 font-bold">
                  {g.away_score}-{g.home_score}
                </span>
              )}
            </div>
          )
        })}
        {more > 0 && <div className="text-[10px] text-gray-700">+{more} more</div>}
      </div>
    </button>
  )
}

function AllWeeksGrid({ schedule, season }: { schedule: WeekGroup[]; season: number }) {
  return (
    <section>
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-3xl font-black text-white tracking-tight leading-none">All Weeks</h2>
        <div className="flex-1 h-px bg-gray-800" />
        <span className="text-[10px] text-gray-500 uppercase tracking-widest">{schedule.length} weeks</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {schedule.map(g => <WeekTile key={g.week} group={g} season={season} />)}
      </div>
    </section>
  )
}

function SeasonAtAGlance({ schedule }: { schedule: WeekGroup[] }) {
  const all = schedule.flatMap(w => w.games)
  const finished = all.filter(g => g.away_score !== null && g.home_score !== null)
  if (!finished.length) return null
  const totalPoints = finished.reduce((s, g) => s + g.away_score! + g.home_score!, 0)
  const avgScore = totalPoints / finished.length
  const avgMargin = finished.reduce((s, g) => s + Math.abs(g.away_score! - g.home_score!), 0) / finished.length
  const ot = finished.filter(g => g.overtime === 1).length
  const upcoming = all.length - finished.length

  const kpis = [
    { label: 'Games Played', value: `${finished.length}${upcoming > 0 ? ` / ${all.length}` : ''}` },
    { label: 'Total Points', value: totalPoints.toLocaleString() },
    { label: 'Avg Combined', value: avgScore.toFixed(1) },
    { label: 'Avg Margin',   value: avgMargin.toFixed(1) },
    { label: 'Overtime',     value: String(ot) },
  ]

  return (
    <section className="mb-10">
      <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {kpis.map(k => (
            <div key={k.label} className="text-center">
              <div className="text-lg font-bold text-white tabular-nums leading-tight">{k.value}</div>
              <div className="text-[10px] text-gray-600 uppercase tracking-wider mt-0.5">{k.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function LastSeasonRecap({ season }: { season: number }) {
  const prev = season - 1
  const champ = SB_CHAMPS[prev]
  const awards = PAST_AWARDS[prev]
  if (!champ && !awards) return null

  const mvp  = awards?.find(a => a.award === 'MVP')
  const opoy = awards?.find(a => a.award === 'OPOY')
  const dpoy = awards?.find(a => a.award === 'DPOY')

  return (
    <section className="mb-10">
      <div className="flex items-end justify-between mb-4 flex-wrap gap-2">
        <div>
          <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Last Season Recap</div>
          <h2 className="text-2xl font-black text-white tracking-tight leading-none mt-1">
            {prev} Highlights
          </h2>
        </div>
        <Link to={`/leaders?season=${prev}`} className="text-xs text-indigo-400 hover:text-indigo-300 font-bold uppercase tracking-wider">
          View {prev} season →
        </Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {champ && (
          <div className="rounded-xl border border-yellow-500/40 bg-yellow-500/5 p-3.5">
            <div className="text-[10px] font-bold text-yellow-300 uppercase tracking-widest mb-2">Super Bowl Champion</div>
            <div className="flex items-center gap-3">
              <img src={teamLogoUrl(champ.team)} alt={champ.team} className="w-10 h-10 object-contain shrink-0" />
              <div className="min-w-0">
                <Link to={`/teams/${champ.team}`} className="text-base font-black text-white hover:text-indigo-400 transition-colors">
                  {champ.team}
                </Link>
                <div className="text-[11px] text-gray-500 mt-0.5">def. {champ.opponent} {champ.score}</div>
              </div>
            </div>
          </div>
        )}
        {[mvp, opoy, dpoy].map((a, i) => a ? (
          <div key={a.award} className="bg-gray-900 border border-gray-800 rounded-xl p-3.5">
            <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2">
              {a.award === 'MVP' ? 'MVP' : a.award === 'OPOY' ? 'Offensive POY' : 'Defensive POY'}
            </div>
            <div className="flex items-center gap-3">
              <img src={teamLogoUrl(a.team)} alt="" className="w-10 h-10 object-contain shrink-0 opacity-80" />
              <div className="min-w-0">
                <div className="text-sm font-bold text-white truncate">{a.player}</div>
                <div className="text-[11px] text-gray-500 mt-0.5">{a.team} · {a.pos}</div>
              </div>
            </div>
          </div>
        ) : <div key={i} className="hidden" />)}
      </div>
    </section>
  )
}

function HomeDashboard({ season, schedule }: { season: number; schedule: WeekGroup[] }) {
  const currentWeek = findCurrentWeek(schedule)
  const currentWeekGames = currentWeek != null ? schedule.find(w => w.week === currentWeek)?.games ?? [] : []
  const seasonGames = schedule.flatMap(w => w.games)
  const seasonFinished = seasonGames.filter(g => g.away_score !== null && g.home_score !== null).length
  const hasPlayoffs = seasonGames.some(g => g.game_type === 'WC' || g.game_type === 'DIV' || g.game_type === 'CON' || g.game_type === 'SB')
  // Early in the season (no real storylines yet), show a recap of the previous season for context
  const showRecap = seasonFinished < 3
  return (
    <>
      <QuickNavStrip season={season} current="home" />
      <CurrentWeekSection schedule={schedule} season={season} />
      {showRecap && <LastSeasonRecap season={season} />}
      {hasPlayoffs && <PlayoffBracket season={season} />}
      <WeekStoriesSection weekGames={currentWeekGames} seasonGames={seasonGames} />
      <TopLeadersStrip season={season} />
      <SeasonAtAGlance schedule={schedule} />
      <RecentResultsFeed schedule={schedule} />
      <JumpToWeek schedule={schedule} season={season} />
    </>
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

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const searchContainerRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    let cancelled = false
    const trimmed = query.trim()
    if (!trimmed) { setResults([]); setOpen(false); return }
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.search(trimmed)
        if (!cancelled) { setResults(res); setOpen(true) }
      } catch { if (!cancelled) setResults([]) }
    }, 300)
    return () => { cancelled = true; if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [query])

  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [])

  function dismiss() { setQuery(''); setResults([]); setOpen(false) }

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
      if (!seasons.some(s => s.status === 'loading' || s.status === 'queued')) clearInterval(interval)
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const currentSeasonEntry = seasons.find(s => s.season === season)
  const currentSeasonStatus = currentSeasonEntry?.status

  // Clear schedule data when season changes
  useEffect(() => {
    setSchedule([])
  }, [season])

  // Fetch schedule once season is confirmed loaded (or unknown — optimistic fetch)
  useEffect(() => {
    if (season === null) return
    if (currentSeasonStatus === 'loading' || currentSeasonStatus === 'queued' || currentSeasonStatus === 'available' || currentSeasonStatus === 'error') return
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
  const isSeasonLoading = currentSeasonStatus === 'loading' || currentSeasonStatus === 'queued'

  const weekTitle = selectedWeek !== null
    ? weekLabel(selectedWeek, selectedGroup?.games[0]?.game_type)
    : undefined

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav title={weekTitle} />
      <div className="max-w-5xl mx-auto px-4 py-10">

        {/* Home header */}
        {selectedWeek === null && (
          <div className="mb-10">
            <div className="flex items-center gap-4">
              {/* Brand */}
              <div className="shrink-0">
                <span className="text-4xl font-black tracking-tight leading-none">
                  <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
                </span>
              </div>

              {/* Search — inline, flex-1 */}
              <div ref={searchContainerRef} className="relative flex-1">
                <div className="relative">
                  <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none"
                    xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Escape' && setOpen(false)}
                    placeholder="Search players or teams…"
                    className="w-full bg-gray-900 border border-gray-800 hover:border-gray-700 focus:border-indigo-500 rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none transition-colors"
                  />
                </div>
                {open && (
                  <div className="absolute top-full mt-2 left-0 right-0 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                    {results.length === 0 ? (
                      <div className="px-4 py-3 text-sm text-gray-600">No results for "{query.trim()}"</div>
                    ) : results.map(r => r.type === 'team' ? (
                      <Link key={r.id} to={`/teams/${r.id}`} onClick={dismiss}
                        className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800 transition-colors">
                        <img src={teamLogoUrl(r.id)} className="w-7 h-7 object-contain shrink-0" alt="" />
                        <div>
                          <div className="text-sm font-semibold text-white">{teamName(r.id)}</div>
                          <div className="text-xs text-gray-500">{r.id}</div>
                        </div>
                      </Link>
                    ) : (
                      <Link key={r.id} to={`/players/${r.id}`} onClick={dismiss}
                        className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800 transition-colors">
                        {r.headshot_url
                          ? <img src={r.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                          : <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
                        }
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-white truncate">{r.name}</div>
                          <div className="text-xs text-gray-500">{[r.position, r.team].filter(Boolean).join(' · ')}</div>
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </div>

              {/* Season selector */}
              <div className="relative shrink-0">
                <select
                  value={season ?? ''}
                  onChange={e => handleSeasonChange(Number(e.target.value))}
                  disabled={seasons.length === 0}
                  className="appearance-none bg-gray-800 border border-gray-700 text-white text-sm rounded-lg pl-3 pr-8 py-2.5 focus:outline-none focus:border-indigo-500 disabled:opacity-50 cursor-pointer hover:border-gray-500 transition-colors"
                >
                  {seasons.length === 0 && <option value="">Loading…</option>}
                  {seasons.map(s => (
                    <option key={s.season} value={s.season} className="bg-gray-900">{s.season}</option>
                  ))}
                </select>
                <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">▾</span>
              </div>
            </div>
          </div>
        )}

        {/* Week view header */}
        {selectedWeek !== null && (
          <div className="mb-8">
            <button onClick={() => setSearchParams({ season: String(season) })} className={`${backBtnCls} mb-4`}>← Back</button>
            <h1 className="text-3xl font-bold text-white">
              {weekLabel(selectedWeek, selectedGroup?.games[0]?.game_type)}
            </h1>
            <p className="text-gray-500 text-sm mt-0.5">{season} NFL Season</p>
          </div>
        )}

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
            <div>
              <WeekHighlights games={selectedGroup.games} />
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
            </div>
          )
        })()}

        {/* Home dashboard / All Weeks */}
        {!isSeasonLoading && selectedWeek === null && (
          scheduleLoading
            ? <p className="text-gray-500">Loading schedule…</p>
            : schedule.length > 0 && season !== null
              ? (searchParams.get('view') === 'weeks'
                  ? <>
                      <QuickNavStrip season={season} current="weeks" />
                      <AllWeeksGrid schedule={schedule} season={season} />
                    </>
                  : <HomeDashboard season={season} schedule={schedule} />
                )
              : null
        )}

      </div>
    </div>
  )
}
