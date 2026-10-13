import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { PlayerGame } from '../../types'
import type { GameOrigin } from '../../types/navigation'
import { teamLogoUrl } from '../../utils/teams'
import { passerRating, pct, ratio, sfmt } from './stats'

function resultBadge(result: PlayerGame['result']) {
  if (!result) return <span className="text-ink-dim text-xs font-bold">—</span>
  const cls = { W: 'text-green-400', L: 'text-data-loss', T: 'text-ink-mid' }
  return <span className={`text-xs font-bold ${cls[result]}`}>{result}</span>
}

type GameCol = { label: string; cell: (g: PlayerGame) => string | number | null; highlight?: boolean }

function getGameCols(pos: string): GameCol[] {
  if (pos === 'QB') return [
    { label: 'C/ATT', cell: g => g.attempts > 0 ? `${g.completions}/${g.attempts}` : null },
    { label: 'YDS',   cell: g => g.attempts > 0 ? g.pass_yards : null, highlight: true },
    { label: 'TD',    cell: g => g.attempts > 0 ? g.pass_tds : null },
    { label: 'INT',   cell: g => g.attempts > 0 ? g.interceptions_thrown : null },
    { label: 'RATE',  cell: g => g.attempts > 0 ? passerRating(g.completions, g.attempts, g.pass_yards, g.pass_tds, g.interceptions_thrown) : null },
    { label: 'EPA',   cell: g => g.attempts > 0 ? sfmt(g.pass_epa, 1) : null },
  ]
  if (pos === 'RB') return [
    { label: 'CAR',     cell: g => g.carries > 0 ? g.carries : null },
    { label: 'YDS',     cell: g => g.rush_yards, highlight: true },
    { label: 'Y/C',     cell: g => g.carries > 0 ? ratio(g.rush_yards, g.carries) : null },
    { label: 'TD',      cell: g => g.rush_tds > 0 ? g.rush_tds : null },
    { label: 'TGT',     cell: g => g.targets > 0 ? g.targets : null },
    { label: 'REC',     cell: g => g.targets > 0 ? g.receptions : null },
    { label: 'REC YDS', cell: g => g.receptions > 0 ? g.rec_yards : null },
    { label: 'EPA',     cell: g => sfmt(g.rush_epa, 1) },
  ]
  if (pos === 'WR' || pos === 'TE') return [
    { label: 'TGT', cell: g => g.targets },
    { label: 'REC', cell: g => g.receptions },
    { label: 'YDS', cell: g => g.rec_yards, highlight: true },
    { label: 'Y/R', cell: g => g.receptions > 0 ? ratio(g.rec_yards, g.receptions) : null },
    { label: 'TD',  cell: g => g.rec_tds > 0 ? g.rec_tds : null },
    { label: 'EPA', cell: g => sfmt(g.rec_epa, 1) },
  ]
  if (pos === 'K') return [
    { label: 'FG',   cell: g => g.fg_att > 0 ? `${g.fg_made}/${g.fg_att}` : null, highlight: true },
    { label: 'FG%',  cell: g => g.fg_att > 0 ? pct(g.fg_made, g.fg_att) : null },
    { label: 'XP',   cell: g => g.xp_att > 0 ? `${g.xp_made}/${g.xp_att}` : null },
    { label: 'PTS',  cell: g => (g.fg_made * 3 + g.xp_made) > 0 ? g.fg_made * 3 + g.xp_made : null },
  ]
  if (pos === 'P') return [
    { label: 'PUNTS', cell: g => g.punts > 0 ? g.punts : null, highlight: true },
    { label: 'YDS',   cell: g => g.punts > 0 ? g.punt_yards : null },
    { label: 'AVG',   cell: g => g.punts > 0 ? ratio(g.punt_yards, g.punts) : null },
  ]
  if (pos === 'OL') return []
  return [
    { label: 'TOT',  cell: g => g.solo_tackles + g.assist_tackles, highlight: true },
    { label: 'SOLO', cell: g => g.solo_tackles },
    { label: 'AST',  cell: g => g.assist_tackles },
    { label: 'SACK', cell: g => g.sacks > 0 ? g.sacks : null },
    { label: 'INT',  cell: g => g.def_interceptions > 0 ? g.def_interceptions : null },
    { label: 'PBU',  cell: g => g.pass_breakups > 0 ? g.pass_breakups : null },
  ]
}

export default function GameLog({ season, games, pos, playerId, playerName, fromGame, defaultOpen = false }: {
  season: number; games: PlayerGame[]; pos: string
  playerId: string; playerName: string; fromGame?: GameOrigin; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const seasonTeams = [...new Set(games.map(g => g.team))]
  const wins = games.filter(g => g.result === 'W').length
  const losses = games.filter(g => g.result === 'L').length
  const ties = games.filter(g => g.result === 'T').length
  const record = ties > 0 ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`
  const gameCols = getGameCols(pos)

  return (
    <div className="bg-surface-card border border-surface-line rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-3 hover:bg-surface-raise/50 transition-colors text-left"
      >
        <div className="flex -space-x-1.5">
          {seasonTeams.map(t => (
            <img key={t} src={teamLogoUrl(t)} alt={t} className="w-6 h-6 object-contain ring-1 ring-surface-line rounded-full bg-surface-card" />
          ))}
        </div>
        <span className="font-semibold text-ink">{season}</span>
        <span className="text-ink-dim text-xs">{seasonTeams.join('/')} · {record} · {games.length}G</span>
        <span className="ml-auto text-ink-dim text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="overflow-x-auto border-t border-surface-line">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-line">
                <th className="py-2 px-4 text-xs font-medium text-ink-dim text-left">Wk</th>
                <th className="py-2 px-4 text-xs font-medium text-ink-dim text-left">Opponent</th>
                <th className="py-2 px-4 text-xs font-medium text-ink-dim text-left">Result</th>
                {gameCols.map(c => (
                  <th key={c.label} className="py-2 px-4 text-xs font-medium text-ink-dim text-left">{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {games.map(g => {
                const score = g.away_score !== null ? `${g.away_score}–${g.home_score}` : null
                return (
                  <tr key={g.game_id} className="border-t border-surface-line/60 hover:bg-surface-raise/40">
                    <td className="py-2 px-4 text-xs tabular-nums whitespace-nowrap">
                      {g.game_type === 'REG'
                        ? <span className="text-ink-dim">Wk {g.week}</span>
                        : <span className="text-ink-dim font-bold">{g.game_type}</span>
                      }
                    </td>
                    <td className="py-2 px-4">
                      <div className="flex items-center gap-1.5">
                        <img src={teamLogoUrl(g.opponent)} alt={g.opponent} className="w-5 h-5 object-contain opacity-60" />
                        <Link
                          to={`/games/${g.game_id}`}
                          state={{ fromPlayer: { playerId, playerName, fromGame } }}
                          className="text-indigo-400 hover:underline text-sm"
                        >
                          {g.location === 'away' ? '@' : 'vs'} {g.opponent}
                        </Link>
                      </div>
                    </td>
                    <td className="py-2 px-4">
                      <div className="flex items-center gap-1.5">
                        {resultBadge(g.result)}
                        {score && <span className="text-ink-dim text-xs">{score}</span>}
                      </div>
                    </td>
                    {gameCols.map(c => {
                      const val = c.cell(g)
                      const isNull = val === null || val === undefined
                      const strVal = isNull ? null : String(val)
                      const isSigned = c.label === 'EPA'
                      const isPos = isSigned && strVal?.startsWith('+')
                      const isNeg = isSigned && strVal?.startsWith('-')
                      return (
                        <td key={c.label} className={`py-2 px-4 tabular-nums text-sm whitespace-nowrap
                          ${isNull ? 'text-ink-dim' : isPos ? 'text-data-win' : isNeg ? 'text-data-loss' : c.highlight ? 'text-ink font-semibold' : 'text-ink-mid'}`}>
                          {isNull ? '—' : strVal}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
