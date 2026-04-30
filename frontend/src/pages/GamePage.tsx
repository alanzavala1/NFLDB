import { createContext, useContext, useEffect, useState } from 'react'
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api'
import type { GameDetail, PlayerStats } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'

interface GameCtx { gameId: string; season: number; week: number; awayTeam: string; homeTeam: string; fromWeek?: number }
const GameContext = createContext<GameCtx | null>(null)
function playerLink(playerId: string, ctx: GameCtx | null) {
  if (!ctx) return { to: `/players/${playerId}`, state: undefined }
  return { to: `/players/${playerId}`, state: { fromGame: ctx } }
}

const WEEK_LABELS: Record<number, string> = { 19: 'Wild Card', 20: 'Divisional', 21: 'Conference', 22: 'Super Bowl' }
function weekLabel(week: number) { return WEEK_LABELS[week] ?? `Week ${week}` }
function sv(n: number) { return n === 0 ? '—' : n % 1 === 0 ? String(n) : n.toFixed(1) }

// ── Stat row components ───────────────────────────────────────────────────────

function PassingRow({ p }: { p: PlayerStats }) {
  const ctx = useContext(GameContext)
  if (!p.attempts) return null
  const { to, state } = playerLink(p.player_id, ctx)
  return (
    <tr className="border-t border-gray-800 hover:bg-gray-900/50">
      <td className="py-2 px-3">
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium">{p.player_name}</Link>
        {p.jersey_number !== null && <span className="text-gray-600 text-xs ml-1">#{p.jersey_number}</span>}
      </td>
      <td className="py-2 px-3 text-right tabular-nums">{p.completions}/{p.attempts}</td>
      <td className="py-2 px-3 text-right tabular-nums">{sv(p.pass_yards)}</td>
      <td className="py-2 px-3 text-right tabular-nums">{p.pass_tds}</td>
      <td className="py-2 px-3 text-right tabular-nums">{p.interceptions_thrown}</td>
      <td className="py-2 px-3 text-right tabular-nums">{p.sacks_taken}</td>
      <td className="py-2 px-3 text-right tabular-nums text-gray-500">{sv(p.pass_epa)}</td>
    </tr>
  )
}

function RushingRow({ p }: { p: PlayerStats }) {
  const ctx = useContext(GameContext)
  if (!p.carries) return null
  const { to, state } = playerLink(p.player_id, ctx)
  return (
    <tr className="border-t border-gray-800 hover:bg-gray-900/50">
      <td className="py-2 px-3">
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium">{p.player_name}</Link>
      </td>
      <td className="py-2 px-3 text-right tabular-nums">{p.carries}</td>
      <td className="py-2 px-3 text-right tabular-nums">{sv(p.rush_yards)}</td>
      <td className="py-2 px-3 text-right tabular-nums">{p.rush_tds}</td>
      <td className="py-2 px-3 text-right tabular-nums text-gray-500">{sv(p.rush_epa)}</td>
    </tr>
  )
}

function ReceivingRow({ p }: { p: PlayerStats }) {
  const ctx = useContext(GameContext)
  if (!p.targets) return null
  const { to, state } = playerLink(p.player_id, ctx)
  return (
    <tr className="border-t border-gray-800 hover:bg-gray-900/50">
      <td className="py-2 px-3">
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium">{p.player_name}</Link>
      </td>
      <td className="py-2 px-3 text-right tabular-nums">{p.receptions}/{p.targets}</td>
      <td className="py-2 px-3 text-right tabular-nums">{sv(p.rec_yards)}</td>
      <td className="py-2 px-3 text-right tabular-nums">{p.rec_tds}</td>
      <td className="py-2 px-3 text-right tabular-nums">{sv(p.yac)}</td>
      <td className="py-2 px-3 text-right tabular-nums text-gray-500">{sv(p.rec_epa)}</td>
    </tr>
  )
}

function DefenseRow({ p }: { p: PlayerStats }) {
  const ctx = useContext(GameContext)
  const hasDefStats = p.solo_tackles || p.sacks || p.def_interceptions || p.pass_breakups || p.tackles_for_loss
  if (!hasDefStats) return null
  const { to, state } = playerLink(p.player_id, ctx)
  return (
    <tr className="border-t border-gray-800 hover:bg-gray-900/50">
      <td className="py-2 px-3">
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium">{p.player_name}</Link>
      </td>
      <td className="py-2 px-3 text-right tabular-nums">{sv(p.solo_tackles)}</td>
      <td className="py-2 px-3 text-right tabular-nums">{sv(p.assist_tackles)}</td>
      <td className="py-2 px-3 text-right tabular-nums">{sv(p.sacks)}</td>
      <td className="py-2 px-3 text-right tabular-nums">{p.tackles_for_loss}</td>
      <td className="py-2 px-3 text-right tabular-nums">{p.def_interceptions}</td>
      <td className="py-2 px-3 text-right tabular-nums">{p.pass_breakups}</td>
    </tr>
  )
}

function StatTable({ title, headers, players, Row }: {
  title: string
  headers: string[]
  players: PlayerStats[]
  Row: React.ComponentType<{ p: PlayerStats }>
}) {
  return (
    <div className="mb-6">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">{title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 text-xs">
              {headers.map(h => (
                <th key={h} className={`py-1 px-3 font-medium ${h !== 'Player' ? 'text-right' : ''}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>{players.map(p => <Row key={p.player_id} p={p} />)}</tbody>
        </table>
      </div>
    </div>
  )
}

// ── Quarter score breakdown ───────────────────────────────────────────────────

function QuarterScores({ game }: { game: GameDetail }) {
  const qs = game.quarter_scores
  if (!qs || qs.length === 0) return null

  const hasOT = qs.some(q => q.qtr >= 5)
  const quarters = [1, 2, 3, 4, ...(hasOT ? [5] : [])]
  const byQtr = Object.fromEntries(qs.map(q => [q.qtr, q]))
  const awayWon = (game.away_score ?? 0) > (game.home_score ?? 0)
  const homeWon = (game.home_score ?? 0) > (game.away_score ?? 0)

  const thCls = 'w-10 text-center text-xs font-medium text-gray-600 pb-1 px-2'
  const tdCls = 'text-center px-2 tabular-nums text-gray-400 text-sm'

  return (
    <div className="mt-5 pt-4 border-t border-gray-800/60 overflow-x-auto">
      <table className="mx-auto">
        <thead>
          <tr>
            <th className="w-16 pr-4" />
            {quarters.map(q => <th key={q} className={thCls}>{q <= 4 ? `Q${q}` : 'OT'}</th>)}
            <th className={`${thCls} text-gray-500 font-bold`}>T</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="text-right pr-4 font-bold text-gray-300 text-sm py-0.5">{game.away_team}</td>
            {quarters.map(q => <td key={q} className={tdCls}>{byQtr[q]?.away ?? '—'}</td>)}
            <td className={`${tdCls} font-bold ${awayWon ? 'text-white' : 'text-gray-500'}`}>{game.away_score ?? '—'}</td>
          </tr>
          <tr>
            <td className="text-right pr-4 font-bold text-gray-300 text-sm py-0.5">{game.home_team}</td>
            {quarters.map(q => <td key={q} className={tdCls}>{byQtr[q]?.home ?? '—'}</td>)}
            <td className={`${tdCls} font-bold ${homeWon ? 'text-white' : 'text-gray-500'}`}>{game.home_score ?? '—'}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

// ── Team stat comparison ──────────────────────────────────────────────────────

function teamTotals(players: PlayerStats[]) {
  const sum = (fn: (p: PlayerStats) => number) => players.reduce((a, p) => a + fn(p), 0)
  return {
    totalYds:    sum(p => p.pass_yards + p.rush_yards),
    passCmp:     sum(p => p.completions),
    passAtt:     sum(p => p.attempts),
    passYds:     sum(p => p.pass_yards),
    passTDs:     sum(p => p.pass_tds),
    ints:        sum(p => p.interceptions_thrown),
    sacksTaken:  sum(p => p.sacks_taken),
    rushCar:     sum(p => p.carries),
    rushYds:     sum(p => p.rush_yards),
    rushTDs:     sum(p => p.rush_tds),
    sacks:       sum(p => p.sacks),
    defInts:     sum(p => p.def_interceptions),
  }
}

function CompRow({ label, away, home, lowerIsBetter = false, neutral = false }: {
  label: string
  away: string | number
  home: string | number
  lowerIsBetter?: boolean
  neutral?: boolean
}) {
  const parse = (v: string | number) =>
    typeof v === 'number' ? v : parseFloat(String(v).replace(/[^\d.]/g, '')) || 0
  const awayN = parse(away)
  const homeN = parse(home)
  const awayBetter = !neutral && (lowerIsBetter ? awayN < homeN : awayN > homeN)
  const homeBetter = !neutral && (lowerIsBetter ? homeN < awayN : homeN > awayN)

  return (
    <div className="flex items-center py-2 border-b border-gray-800/40 last:border-0">
      <div className={`flex-1 text-right pr-6 tabular-nums text-sm ${awayBetter ? 'text-white font-semibold' : 'text-gray-500'}`}>
        {away}
      </div>
      <div className="w-36 text-center text-xs text-gray-600 shrink-0">{label}</div>
      <div className={`flex-1 text-left pl-6 tabular-nums text-sm ${homeBetter ? 'text-white font-semibold' : 'text-gray-500'}`}>
        {home}
      </div>
    </div>
  )
}

function CompSection({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="flex-1 h-px bg-gray-800/60" />
      <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest shrink-0">{label}</span>
      <div className="flex-1 h-px bg-gray-800/60" />
    </div>
  )
}

function TeamComparison({ game }: { game: GameDetail }) {
  const away = teamTotals(game.away)
  const home = teamTotals(game.home)
  if (!away.passAtt && !away.rushCar && !home.passAtt && !home.rushCar) return null

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
      <div className="flex items-center mb-3">
        <div className="flex-1 flex justify-end items-center gap-2 pr-6">
          <span className="font-bold text-white text-sm">{game.away_team}</span>
          <img src={teamLogoUrl(game.away_team)} alt={game.away_team} className="w-5 h-5 object-contain" />
        </div>
        <div className="w-36 text-center text-[10px] font-bold text-gray-600 uppercase tracking-widest shrink-0">Team Stats</div>
        <div className="flex-1 flex justify-start items-center gap-2 pl-6">
          <img src={teamLogoUrl(game.home_team)} alt={game.home_team} className="w-5 h-5 object-contain" />
          <span className="font-bold text-white text-sm">{game.home_team}</span>
        </div>
      </div>

      <CompRow label="Total Yards" away={away.totalYds} home={home.totalYds} />

      <CompSection label="Passing" />
      <CompRow label="Comp / Att" away={`${away.passCmp}/${away.passAtt}`} home={`${home.passCmp}/${home.passAtt}`} neutral />
      <CompRow label="Yards" away={away.passYds} home={home.passYds} />
      <CompRow label="Touchdowns" away={away.passTDs} home={home.passTDs} />
      <CompRow label="Interceptions" away={away.ints} home={home.ints} lowerIsBetter />
      <CompRow label="Sacks Taken" away={away.sacksTaken} home={home.sacksTaken} lowerIsBetter />

      <CompSection label="Rushing" />
      <CompRow label="Carries" away={away.rushCar} home={home.rushCar} neutral />
      <CompRow label="Yards" away={away.rushYds} home={home.rushYds} />
      <CompRow label="Touchdowns" away={away.rushTDs} home={home.rushTDs} />

      <CompSection label="Defense" />
      <CompRow label="Sacks" away={away.sacks} home={home.sacks} />
      <CompRow label="Interceptions" away={away.defInts} home={home.defInts} />
    </div>
  )
}

// ── Team player stats panel ───────────────────────────────────────────────────

function TeamBox({ team, players }: { team: string; players: PlayerStats[] }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-5">
        <img src={teamLogoUrl(team)} alt={team} className="w-6 h-6 object-contain" />
        <h2 className="text-white font-bold text-lg">
          <Link to={`/teams/${team}`} className="hover:text-indigo-400 transition-colors">{teamName(team)}</Link>
        </h2>
      </div>
      <StatTable title="Passing"   headers={['Player', 'C/ATT', 'YDS', 'TD', 'INT', 'SCK', 'EPA']}         players={players} Row={PassingRow}   />
      <StatTable title="Rushing"   headers={['Player', 'CAR', 'YDS', 'TD', 'EPA']}                          players={players} Row={RushingRow}   />
      <StatTable title="Receiving" headers={['Player', 'REC/TGT', 'YDS', 'TD', 'YAC', 'EPA']}              players={players} Row={ReceivingRow} />
      <StatTable title="Defense"   headers={['Player', 'SOLO', 'AST', 'SACK', 'TFL', 'INT', 'PBU']}        players={players} Row={DefenseRow}   />
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function GamePage() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const fromWeek: number | undefined = (location.state as any)?.fromWeek
  const fromPlayer: { playerId: string; playerName: string } | undefined = (location.state as any)?.fromPlayer
  const [game, setGame] = useState<GameDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTeam, setActiveTeam] = useState<'away' | 'home'>('away')

  useEffect(() => {
    if (!gameId) return
    api.game(gameId).then(setGame).finally(() => setLoading(false))
  }, [gameId])

  if (loading) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Loading...</p></div>
  if (!game) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Game not found.</p></div>

  const awayWon = game.away_score !== null && game.home_score !== null && game.away_score > game.home_score
  const homeWon = game.away_score !== null && game.home_score !== null && game.home_score > game.away_score
  const finished = game.away_score !== null

  const backTo = fromPlayer
    ? { to: `/players/${fromPlayer.playerId}`, state: { fromGame: (fromPlayer as any).fromGame } }
    : fromWeek !== undefined
      ? { to: `/?season=${game.season}&week=${fromWeek}`, state: undefined }
      : { to: `/?season=${game.season}`, state: undefined }

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8">

        {/* Breadcrumb */}
        <div className="flex items-center gap-2 mb-5">
          <button onClick={() => navigate('/?season=2025')} className="text-gray-500 hover:text-white transition-colors p-1 rounded-md hover:bg-gray-800" title="Home">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7A1 1 0 003 11h1v6a1 1 0 001 1h4v-4h2v4h4a1 1 0 001-1v-6h1a1 1 0 00.707-1.707l-7-7z" />
            </svg>
          </button>
          <span className="text-gray-700">/</span>
          {fromPlayer ? (
            <>
              <Link to={`/players/${fromPlayer.playerId}`} state={{ fromGame: (fromPlayer as any).fromGame }} className="text-gray-400 hover:text-white text-sm transition-colors">{fromPlayer.playerName}</Link>
              <span className="text-gray-700">/</span>
            </>
          ) : (
            <>
              <Link to={`/?season=${game.season}`} className="text-gray-400 hover:text-white text-sm transition-colors">{game.season}</Link>
              {fromWeek !== undefined && (
                <>
                  <span className="text-gray-700">/</span>
                  <Link to={`/?season=${game.season}&week=${fromWeek}`} className="text-gray-400 hover:text-white text-sm transition-colors">{weekLabel(fromWeek)}</Link>
                </>
              )}
              <span className="text-gray-700">/</span>
            </>
          )}
          <span className="text-gray-400 text-sm">{game.away_team} @ {game.home_team}</span>
          <Link to={backTo.to} state={backTo.state} className="ml-auto flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-2 transition-colors">
            ← Back
          </Link>
        </div>

        {/* Score card */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-6">
          <div className="text-gray-500 text-xs text-center mb-5">
            {weekLabel(game.week)} · {game.gameday} · {game.season} NFL Season
          </div>

          <div className="flex items-center justify-center gap-6 lg:gap-16">
            <Link to={`/teams/${game.away_team}`} className={`flex flex-col items-center gap-2 group/a min-w-0 ${awayWon ? '' : 'opacity-50'}`}>
              <img src={teamLogoUrl(game.away_team)} alt={game.away_team} className="w-14 h-14 lg:w-20 lg:h-20 object-contain pointer-events-none transition-transform group-hover/a:scale-105" />
              <span className="font-bold text-base lg:text-xl text-white group-hover/a:text-indigo-400 transition-colors">{teamName(game.away_team)}</span>
              {game.away_record && <span className="text-xs text-gray-500 -mt-1">{game.away_record}</span>}
            </Link>

            <div className="flex items-center gap-3 lg:gap-5 shrink-0">
              {finished ? (
                <>
                  <span className={`text-4xl lg:text-6xl font-bold tabular-nums ${awayWon ? 'text-white' : 'text-gray-500'}`}>{game.away_score}</span>
                  <span className="text-gray-700 text-xl lg:text-3xl">–</span>
                  <span className={`text-4xl lg:text-6xl font-bold tabular-nums ${homeWon ? 'text-white' : 'text-gray-500'}`}>{game.home_score}</span>
                </>
              ) : (
                <span className="text-gray-600 text-sm px-4">Upcoming</span>
              )}
            </div>

            <Link to={`/teams/${game.home_team}`} className={`flex flex-col items-center gap-2 group/h min-w-0 ${homeWon ? '' : 'opacity-50'}`}>
              <img src={teamLogoUrl(game.home_team)} alt={game.home_team} className="w-14 h-14 lg:w-20 lg:h-20 object-contain pointer-events-none transition-transform group-hover/h:scale-105" />
              <span className="font-bold text-base lg:text-xl text-white group-hover/h:text-indigo-400 transition-colors">{teamName(game.home_team)}</span>
              {game.home_record && <span className="text-xs text-gray-500 -mt-1">{game.home_record}</span>}
            </Link>
          </div>

          <QuarterScores game={game} />

          {(game.stadium || game.temp !== null || game.wind !== null || game.surface || game.roof) && (
            <div className="mt-4 pt-3 border-t border-gray-800/60 flex flex-wrap justify-center gap-3 text-xs text-gray-600">
              {game.stadium && <span>{game.stadium}</span>}
              {game.temp !== null && <span>{game.temp}°F</span>}
              {game.wind !== null && <span>{game.wind} mph wind</span>}
              {game.surface && <span className="capitalize">{game.surface}</span>}
              {game.roof && <span className="capitalize">{game.roof}</span>}
            </div>
          )}
        </div>

        {/* Team stat comparison */}
        <TeamComparison game={game} />

        {/* Player stats */}
        <GameContext.Provider value={{ gameId: game.game_id, season: game.season, week: game.week, awayTeam: game.away_team, homeTeam: game.home_team, fromWeek }}>

          {/* Mobile: team tabs */}
          <div className="flex gap-2 mb-4 lg:hidden">
            {(['away', 'home'] as const).map(side => {
              const t = side === 'away' ? game.away_team : game.home_team
              const active = activeTeam === side
              return (
                <button key={side} onClick={() => setActiveTeam(side)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg border text-sm font-semibold transition-colors
                    ${active ? 'bg-indigo-900/40 border-indigo-700 text-white' : 'border-gray-800 text-gray-500 hover:text-gray-300 hover:bg-gray-800/40'}`}
                >
                  <img src={teamLogoUrl(t)} alt={t} className="w-5 h-5 object-contain" />
                  {t}
                </button>
              )
            })}
          </div>
          <div className="lg:hidden">
            <TeamBox team={activeTeam === 'away' ? game.away_team : game.home_team}
                     players={activeTeam === 'away' ? game.away : game.home} />
          </div>

          {/* Desktop: side by side */}
          <div className="hidden lg:grid grid-cols-2 gap-6">
            <TeamBox team={game.away_team} players={game.away} />
            <TeamBox team={game.home_team} players={game.home} />
          </div>

        </GameContext.Provider>
      </div>
    </div>
  )
}
