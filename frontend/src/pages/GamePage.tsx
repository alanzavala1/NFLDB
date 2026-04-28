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

function statVal(n: number) {
  return n === 0 ? '—' : n % 1 === 0 ? n : n.toFixed(1)
}

function PassingRow({ p }: { p: PlayerStats }) {
  const ctx = useContext(GameContext)
  if (!p.attempts) return null
  const { to, state } = playerLink(p.player_id, ctx)
  return (
    <tr className="border-t border-gray-800 hover:bg-gray-900/50">
      <td className="py-2 px-3">
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium">
          {p.player_name}
        </Link>
        {p.jersey_number !== null && <span className="text-gray-600 text-xs ml-1">#{p.jersey_number}</span>}
      </td>
      <td className="py-2 px-3 text-right">{p.completions}/{p.attempts}</td>
      <td className="py-2 px-3 text-right">{statVal(p.pass_yards)}</td>
      <td className="py-2 px-3 text-right">{p.pass_tds}</td>
      <td className="py-2 px-3 text-right">{p.interceptions_thrown}</td>
      <td className="py-2 px-3 text-right">{p.sacks_taken}</td>
      <td className="py-2 px-3 text-right text-gray-500">{statVal(p.pass_epa)}</td>
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
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium">
          {p.player_name}
        </Link>
      </td>
      <td className="py-2 px-3 text-right">{p.carries}</td>
      <td className="py-2 px-3 text-right">{statVal(p.rush_yards)}</td>
      <td className="py-2 px-3 text-right">{p.rush_tds}</td>
      <td className="py-2 px-3 text-right text-gray-500">{statVal(p.rush_epa)}</td>
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
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium">
          {p.player_name}
        </Link>
      </td>
      <td className="py-2 px-3 text-right">{p.receptions}/{p.targets}</td>
      <td className="py-2 px-3 text-right">{statVal(p.rec_yards)}</td>
      <td className="py-2 px-3 text-right">{p.rec_tds}</td>
      <td className="py-2 px-3 text-right">{statVal(p.yac)}</td>
      <td className="py-2 px-3 text-right text-gray-500">{statVal(p.rec_epa)}</td>
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
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium">
          {p.player_name}
        </Link>
      </td>
      <td className="py-2 px-3 text-right">{statVal(p.solo_tackles)}</td>
      <td className="py-2 px-3 text-right">{statVal(p.assist_tackles)}</td>
      <td className="py-2 px-3 text-right">{statVal(p.sacks)}</td>
      <td className="py-2 px-3 text-right">{p.tackles_for_loss}</td>
      <td className="py-2 px-3 text-right">{p.def_interceptions}</td>
      <td className="py-2 px-3 text-right">{p.pass_breakups}</td>
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
          <tbody>
            {players.map(p => <Row key={p.player_id} p={p} />)}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TeamBox({ label, team, players }: { label: string; team: string; players: PlayerStats[] }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <h2 className="text-white font-bold text-xl mb-5">
        <Link to={`/teams/${team}`} className="hover:text-indigo-400 transition-colors">{label}</Link>
      </h2>
      <StatTable
        title="Passing"
        headers={['Player', 'C/ATT', 'YDS', 'TD', 'INT', 'SCK', 'EPA']}
        players={players}
        Row={PassingRow}
      />
      <StatTable
        title="Rushing"
        headers={['Player', 'CAR', 'YDS', 'TD', 'EPA']}
        players={players}
        Row={RushingRow}
      />
      <StatTable
        title="Receiving"
        headers={['Player', 'REC/TGT', 'YDS', 'TD', 'YAC', 'EPA']}
        players={players}
        Row={ReceivingRow}
      />
      <StatTable
        title="Defense"
        headers={['Player', 'SOLO', 'AST', 'SACK', 'TFL', 'INT', 'PBU']}
        players={players}
        Row={DefenseRow}
      />
    </div>
  )
}

export default function GamePage() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const fromWeek: number | undefined = (location.state as any)?.fromWeek
  const fromPlayer: { playerId: string; playerName: string } | undefined = (location.state as any)?.fromPlayer
  const [game, setGame] = useState<GameDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!gameId) return
    api.game(gameId).then(setGame).finally(() => setLoading(false))
  }, [gameId])

  if (loading) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Loading...</p></div>
  if (!game) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Game not found.</p></div>

  const awayWon = game.away_score !== null && game.home_score !== null && game.away_score > game.home_score
  const homeWon = game.away_score !== null && game.home_score !== null && game.home_score > game.away_score

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="mb-8">
          {/* Nav row */}
          <div className="flex items-center gap-2 mb-5">
            <button
              onClick={() => navigate('/?season=2025')}
              className="text-gray-500 hover:text-white transition-colors p-1 rounded-md hover:bg-gray-800"
              title="Home"
            >
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
            <span className="text-gray-400 text-sm">{teamName(game.away_team)} @ {teamName(game.home_team)}</span>
            <Link
              to={fromPlayer ? `/players/${fromPlayer.playerId}` : fromWeek !== undefined ? `/?season=${game.season}&week=${fromWeek}` : `/?season=${game.season}`}
              state={fromPlayer ? { fromGame: (fromPlayer as any).fromGame } : undefined}
              className="ml-auto flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-2 transition-colors"
            >
              ← Back
            </Link>
          </div>

          {/* Title row */}
          <div className="flex items-end gap-4">
            <div>
              <h1 className="text-3xl font-bold text-white">{teamName(game.away_team)} @ {teamName(game.home_team)}</h1>
              <p className="text-gray-500 text-sm mt-0.5">
                {game.gameday} · {fromWeek !== undefined ? weekLabel(fromWeek) : `Week ${game.week}`} · {game.season} NFL Season
              </p>
            </div>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-8 text-center">
          <div className="text-gray-500 text-sm mb-4">{game.gameday} · {game.stadium}</div>
          <div className="flex items-center justify-center gap-8">
            <Link to={`/teams/${game.away_team}`} className={`flex flex-col items-center gap-2 group/logo ${awayWon ? 'text-white' : 'text-gray-400'}`}>
              <img src={teamLogoUrl(game.away_team)} alt={game.away_team} className={`w-16 h-16 object-contain pointer-events-none transition-all group-hover/logo:scale-110 group-hover/logo:opacity-100 ${awayWon ? '' : 'opacity-40'}`} />
              <div className="font-bold text-xl group-hover/logo:text-indigo-400 transition-colors">{teamName(game.away_team)}</div>
              {game.away_record && <div className="text-xs text-gray-500 -mt-1">{game.away_record}</div>}
            </Link>
            <div className="flex gap-4 items-center">
              {game.away_score !== null && (
                <>
                  <span className={`text-5xl font-bold ${awayWon ? 'text-indigo-400' : 'text-gray-500'}`}>{game.away_score}</span>
                  <span className="text-gray-600 text-2xl">–</span>
                  <span className={`text-5xl font-bold ${homeWon ? 'text-indigo-400' : 'text-gray-500'}`}>{game.home_score}</span>
                </>
              )}
            </div>
            <Link to={`/teams/${game.home_team}`} className={`flex flex-col items-center gap-2 group/logo ${homeWon ? 'text-white' : 'text-gray-400'}`}>
              <img src={teamLogoUrl(game.home_team)} alt={game.home_team} className={`w-16 h-16 object-contain pointer-events-none transition-all group-hover/logo:scale-110 group-hover/logo:opacity-100 ${homeWon ? '' : 'opacity-40'}`} />
              <div className="font-bold text-xl group-hover/logo:text-indigo-400 transition-colors">{teamName(game.home_team)}</div>
              {game.home_record && <div className="text-xs text-gray-500 -mt-1">{game.home_record}</div>}
            </Link>
          </div>
          {(game.temp !== null || game.wind !== null || game.surface) && (
            <div className="mt-4 text-xs text-gray-600 flex justify-center gap-4">
              {game.temp !== null && <span>{game.temp}°F</span>}
              {game.wind !== null && <span>{game.wind} mph wind</span>}
              {game.surface && <span>{game.surface}</span>}
              {game.roof && <span>{game.roof}</span>}
            </div>
          )}
        </div>

        <GameContext.Provider value={{ gameId: game.game_id, season: game.season, week: game.week, awayTeam: game.away_team, homeTeam: game.home_team, fromWeek }}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <TeamBox label={teamName(game.away_team)} team={game.away_team} players={game.away} />
            <TeamBox label={teamName(game.home_team)} team={game.home_team} players={game.home} />
          </div>
        </GameContext.Provider>
      </div>
    </div>
  )
}
