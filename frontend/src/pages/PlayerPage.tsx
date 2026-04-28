import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api'
import type { PlayerProfile, PlayerGame, NgsStats, SnapTotals } from '../api'
import Nav from '../components/Nav'
import { teamLogoUrl } from '../utils/teams'

function weekLabel(week: number) { return `Week ${week}` }

function sumGames(games: PlayerGame[]) {
  const s = {
    attempts: 0, completions: 0, pass_yards: 0, pass_tds: 0, interceptions_thrown: 0,
    carries: 0, rush_yards: 0, rush_tds: 0,
    targets: 0, receptions: 0, rec_yards: 0, rec_tds: 0,
    solo_tackles: 0, assist_tackles: 0, sacks: 0, def_interceptions: 0, pass_breakups: 0,
  }
  for (const g of games) {
    for (const k of Object.keys(s) as (keyof typeof s)[]) {
      s[k] += (g as any)[k] ?? 0
    }
  }
  return s
}

type Totals = ReturnType<typeof sumGames>
type ColKind = 'trad' | 'ngs' | 'snap'
type Col = {
  key: string
  label: string
  kind: ColKind
  signed?: boolean
  cell: (t: Totals, games: number, n?: NgsStats, sn?: SnapTotals) => string | number | null
}

function pct(a: number, b: number) { return b > 0 ? (a / b * 100).toFixed(1) : null }
function ratio(y: number, a: number, dec = 1) { return a > 0 ? (y / a).toFixed(dec) : null }
function sfmt(x: number | undefined, dec = 1): string | null {
  if (x == null) return null
  return `${x >= 0 ? '+' : ''}${x.toFixed(dec)}`
}
function dfmt(x: number | undefined, dec = 1): string | null {
  if (x == null) return null
  return x.toFixed(dec)
}

const QB_COLS: Col[] = [
  { key: 'g',    label: 'G',       kind: 'trad', cell: (_, g) => g },
  { key: 'cmp',  label: 'CMP',     kind: 'trad', cell: t => t.completions },
  { key: 'att',  label: 'ATT',     kind: 'trad', cell: t => t.attempts },
  { key: 'cpct', label: 'CMP%',    kind: 'trad', cell: t => pct(t.completions, t.attempts) },
  { key: 'yds',  label: 'YDS',     kind: 'trad', cell: t => t.pass_yards },
  { key: 'ya',   label: 'Y/A',     kind: 'trad', cell: t => ratio(t.pass_yards, t.attempts) },
  { key: 'td',   label: 'TD',      kind: 'trad', cell: t => t.pass_tds },
  { key: 'int',  label: 'INT',     kind: 'trad', cell: t => t.interceptions_thrown },
  { key: 'cpoe', label: 'CPOE',    kind: 'ngs', signed: true, cell: (_, __, n) => sfmt(n?.cpoe) },
  { key: 'ttt',  label: 'TTT',     kind: 'ngs', cell: (_, __, n) => n?.avg_time_to_throw != null ? `${n.avg_time_to_throw.toFixed(2)}s` : null },
  { key: 'adot', label: 'aDOT',    kind: 'ngs', cell: (_, __, n) => dfmt(n?.adot) },
  { key: 'cay',  label: 'CAY',     kind: 'ngs', cell: (_, __, n) => dfmt(n?.avg_completed_air_yards) },
  { key: 'agg',  label: 'AGG%',    kind: 'ngs', cell: (_, __, n) => n?.aggressiveness != null ? `${n.aggressiveness.toFixed(1)}%` : null },
  { key: 'xcmp', label: 'xCMP%',   kind: 'ngs', cell: (_, __, n) => n?.expected_cmp_pct != null ? `${n.expected_cmp_pct.toFixed(1)}%` : null },
  { key: 'rtg',  label: 'NGS RTG', kind: 'ngs', cell: (_, __, n) => dfmt(n?.ngs_passer_rating) },
  { key: 'snp',  label: 'SNP',     kind: 'snap', cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',    kind: 'snap', cell: (_, __, _n, sn) => sn ? `${sn.avg_offense_pct.toFixed(0)}%` : null },
]

const RB_COLS: Col[] = [
  { key: 'g',    label: 'G',       kind: 'trad', cell: (_, g) => g },
  { key: 'car',  label: 'CAR',     kind: 'trad', cell: t => t.carries },
  { key: 'ryds', label: 'YDS',     kind: 'trad', cell: t => t.rush_yards },
  { key: 'ypc',  label: 'Y/C',     kind: 'trad', cell: t => ratio(t.rush_yards, t.carries) },
  { key: 'rtd',  label: 'TD',      kind: 'trad', cell: t => t.rush_tds },
  { key: 'tgt',  label: 'TGT',     kind: 'trad', cell: t => t.targets },
  { key: 'rec',  label: 'REC',     kind: 'trad', cell: t => t.receptions },
  { key: 'rcy',  label: 'REC YDS', kind: 'trad', cell: t => t.rec_yards },
  { key: 'rct',  label: 'REC TD',  kind: 'trad', cell: t => t.rec_tds },
  { key: 'ryoe', label: 'RYOE',    kind: 'ngs', signed: true, cell: (_, __, n) => sfmt(n?.rush_yoe) },
  { key: 'ryoa', label: 'RYOE/A',  kind: 'ngs', signed: true, cell: (_, __, n) => sfmt(n?.rush_yoe_per_att, 2) },
  { key: 'eff',  label: 'EFF%',    kind: 'ngs', cell: (_, __, n) => n?.rush_efficiency != null ? `${n.rush_efficiency.toFixed(1)}%` : null },
  { key: 'tlos', label: 'T-LOS',   kind: 'ngs', cell: (_, __, n) => n?.avg_time_to_los != null ? `${n.avg_time_to_los.toFixed(2)}s` : null },
  { key: 'vs8',  label: 'VS 8+%',  kind: 'ngs', cell: (_, __, n) => n?.pct_vs_8_defenders != null ? `${n.pct_vs_8_defenders.toFixed(1)}%` : null },
  { key: 'snp',  label: 'SNP',     kind: 'snap', cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',    kind: 'snap', cell: (_, __, _n, sn) => sn ? `${sn.avg_offense_pct.toFixed(0)}%` : null },
]

const WR_COLS: Col[] = [
  { key: 'g',    label: 'G',         kind: 'trad', cell: (_, g) => g },
  { key: 'tgt',  label: 'TGT',       kind: 'trad', cell: t => t.targets },
  { key: 'rec',  label: 'REC',       kind: 'trad', cell: t => t.receptions },
  { key: 'yds',  label: 'YDS',       kind: 'trad', cell: t => t.rec_yards },
  { key: 'ypr',  label: 'Y/R',       kind: 'trad', cell: t => ratio(t.rec_yards, t.receptions) },
  { key: 'td',   label: 'TD',        kind: 'trad', cell: t => t.rec_tds },
  { key: 'cpct', label: 'CTH%',      kind: 'trad', cell: t => pct(t.receptions, t.targets) },
  { key: 'car',  label: 'CAR',       kind: 'trad', cell: t => t.carries > 0 ? t.carries : null },
  { key: 'ryd',  label: 'RUSH YDS',  kind: 'trad', cell: t => t.carries > 0 ? t.rush_yards : null },
  { key: 'sep',  label: 'SEP',       kind: 'ngs', cell: (_, __, n) => dfmt(n?.avg_separation) },
  { key: 'cush', label: 'CUSH',      kind: 'ngs', cell: (_, __, n) => dfmt(n?.avg_cushion) },
  { key: 'tgd',  label: 'TGT DEPTH', kind: 'ngs', cell: (_, __, n) => dfmt(n?.avg_target_depth) },
  { key: 'yac',  label: 'YAC+',      kind: 'ngs', signed: true, cell: (_, __, n) => sfmt(n?.avg_yac_above_exp) },
  { key: 'aysh', label: 'AY SH%',    kind: 'ngs', cell: (_, __, n) => n?.air_yards_share != null ? `${n.air_yards_share.toFixed(1)}%` : null },
  { key: 'ngsc', label: 'NGS CTH%',  kind: 'ngs', cell: (_, __, n) => n?.catch_pct != null ? `${n.catch_pct.toFixed(1)}%` : null },
  { key: 'snp',  label: 'SNP',       kind: 'snap', cell: (_, __, _n, sn) => sn ? sn.offense_snaps : null },
  { key: 'spct', label: 'SNP%',      kind: 'snap', cell: (_, __, _n, sn) => sn ? `${sn.avg_offense_pct.toFixed(0)}%` : null },
]

const DEF_COLS: Col[] = [
  { key: 'g',    label: 'G',    kind: 'trad', cell: (_, g) => g },
  { key: 'solo', label: 'SOLO', kind: 'trad', cell: t => t.solo_tackles },
  { key: 'ast',  label: 'AST',  kind: 'trad', cell: t => t.assist_tackles },
  { key: 'tot',  label: 'TOT',  kind: 'trad', cell: t => t.solo_tackles + t.assist_tackles },
  { key: 'sck',  label: 'SCK',  kind: 'trad', cell: t => t.sacks },
  { key: 'int',  label: 'INT',  kind: 'trad', cell: t => t.def_interceptions },
  { key: 'pbu',  label: 'PBU',  kind: 'trad', cell: t => t.pass_breakups },
  { key: 'snp',  label: 'SNP',  kind: 'snap', cell: (_, __, _n, sn) => sn ? (sn.defense_snaps > 0 ? sn.defense_snaps : sn.st_snaps) : null },
  { key: 'spct', label: 'SNP%', kind: 'snap', cell: (_, __, _n, sn) => sn ? (sn.defense_snaps > 0 ? `${sn.avg_defense_pct.toFixed(0)}%` : `${sn.avg_st_pct.toFixed(0)}%`) : null },
]

function detectPos(t: Totals) {
  if (t.attempts > 10) return 'QB'
  if (t.carries > 20 && t.targets < t.carries * 0.7) return 'RB'
  if (t.targets > 20) return 'WR'
  return 'DEF'
}

function CareerTable({ seasons, bySeason, ngs, snapTotals }: {
  seasons: number[]
  bySeason: Record<number, PlayerGame[]>
  ngs: Record<number, NgsStats>
  snapTotals: Record<number, SnapTotals>
}) {
  const allTotals = sumGames(seasons.flatMap(s => bySeason[s]))
  const pos = detectPos(allTotals)
  const allCols = pos === 'QB' ? QB_COLS : pos === 'RB' ? RB_COLS : pos === 'WR' ? WR_COLS : DEF_COLS

  const hasNgs = Object.keys(ngs).length > 0
  const hasSnaps = Object.keys(snapTotals).length > 0
  const cols = allCols.filter(c => !(c.kind === 'ngs' && !hasNgs) && !(c.kind === 'snap' && !hasSnaps))

  const ngsCount = cols.filter(c => c.kind === 'ngs').length
  const snapCount = cols.filter(c => c.kind === 'snap').length
  const tradCount = cols.filter(c => c.kind === 'trad').length

  // Career totals row
  const careerT = sumGames(seasons.flatMap(s => bySeason[s]))
  const careerGames = seasons.reduce((acc, s) => acc + bySeason[s].length, 0)

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-left'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-6">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800/50">
              <th colSpan={2} />
              {tradCount > 0 && <th colSpan={tradCount} className="py-1 text-center text-[10px] font-semibold text-gray-600 uppercase tracking-widest">Traditional</th>}
              {ngsCount > 0 && <th colSpan={ngsCount} className="py-1 text-center text-[10px] font-semibold text-indigo-400 uppercase tracking-widest bg-indigo-950/25">Next Gen Stats</th>}
              {snapCount > 0 && <th colSpan={snapCount} className="py-1 text-center text-[10px] font-semibold text-gray-700 uppercase tracking-widest">Snaps</th>}
            </tr>
            <tr className="border-b border-gray-800">
              <th className={`${thBase} text-gray-500 pl-4`}>Season</th>
              <th className={`${thBase} text-gray-500`}>Team</th>
              {cols.map(c => (
                <th key={c.key} className={`${thBase} ${c.kind === 'ngs' ? 'text-indigo-300/50 bg-indigo-950/10' : c.kind === 'snap' ? 'text-gray-700' : 'text-gray-500'}`}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {seasons.map(s => {
              const games = bySeason[s]
              const t = sumGames(games)
              const n = ngs[s] as NgsStats | undefined
              const sn = snapTotals[s] as SnapTotals | undefined
              const teams = [...new Set(games.map(g => g.team))]
              return (
                <tr key={s} className="border-t border-gray-800/60 hover:bg-gray-800/30">
                  <td className="py-2.5 pl-4 pr-3 font-bold text-white whitespace-nowrap">{s}</td>
                  <td className="py-2.5 px-3">
                    <div className="flex items-center gap-1.5">
                      <div className="flex items-center -space-x-1">
                        {teams.map(t => (
                          <img key={t} src={teamLogoUrl(t)} alt={t} className="w-5 h-5 object-contain ring-1 ring-gray-900 rounded-full bg-gray-900" />
                        ))}
                      </div>
                      <span className="text-gray-400 text-xs">{teams.join(' / ')}</span>
                    </div>
                  </td>
                  {cols.map(c => {
                    const raw = c.cell(t, games.length, n, sn)
                    const isNull = raw === null || raw === undefined
                    const strVal = isNull ? null : String(raw)
                    const isPos = c.signed && !isNull && strVal!.startsWith('+')
                    const isNeg = c.signed && !isNull && strVal!.startsWith('-')
                    return (
                      <td key={c.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums ${c.kind === 'ngs' ? 'bg-indigo-950/10' : ''} ${isNull ? 'text-gray-700' : isPos ? 'text-emerald-400 font-semibold' : isNeg ? 'text-red-400 font-semibold' : c.kind === 'ngs' ? 'text-gray-200' : 'text-gray-300'}`}>
                        {isNull ? '—' : strVal}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
            {/* Career totals */}
            {seasons.length > 1 && (
              <tr className="border-t-2 border-gray-700 bg-gray-800/40">
                <td className="py-2.5 pl-4 pr-3 text-xs font-bold text-gray-400 uppercase tracking-wider whitespace-nowrap">Career</td>
                <td className="py-2.5 px-3 text-gray-600 text-xs">{careerGames} G</td>
                {cols.map(c => {
                  const raw = c.kind === 'trad' ? c.cell(careerT, careerGames, undefined, undefined) : null
                  const isNull = raw === null || raw === undefined
                  return (
                    <td key={c.key} className={`py-2.5 px-3 whitespace-nowrap tabular-nums font-medium ${c.kind === 'ngs' ? 'bg-indigo-950/10 text-gray-700' : isNull ? 'text-gray-700' : 'text-gray-200'}`}>
                      {isNull ? '—' : String(raw)}
                    </td>
                  )
                })}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function gameStatCols(g: PlayerGame): { label: string; val: string | number }[] {
  if (g.attempts > 0) return [
    { label: 'C/ATT', val: `${g.completions}/${g.attempts}` },
    { label: 'YDS', val: g.pass_yards },
    { label: 'TD', val: g.pass_tds },
    { label: 'INT', val: g.interceptions_thrown },
  ]
  if (g.carries > 0 && g.receptions === 0) return [
    { label: 'CAR', val: g.carries },
    { label: 'YDS', val: g.rush_yards },
    { label: 'TD', val: g.rush_tds },
  ]
  if (g.targets > 0 || g.carries > 0) return [
    { label: 'REC/TGT', val: `${g.receptions}/${g.targets}` },
    { label: 'YDS', val: g.rec_yards },
    { label: 'TD', val: g.rec_tds },
    ...(g.carries > 0 ? [{ label: 'RUSH', val: g.rush_yards }] : []),
  ]
  return [
    { label: 'SOLO', val: g.solo_tackles },
    { label: 'SACK', val: g.sacks },
    { label: 'INT', val: g.def_interceptions },
  ]
}

function resultBadge(result: PlayerGame['result']) {
  if (!result) return <span className="text-gray-600 text-xs font-bold">—</span>
  const styles = { W: 'text-green-400', L: 'text-red-400', T: 'text-gray-400' }
  return <span className={`text-xs font-bold ${styles[result]}`}>{result}</span>
}

function GameLog({ season, games, playerId, playerName, fromGame, defaultOpen = false }: {
  season: number; games: PlayerGame[]; playerId: string; playerName: string; fromGame?: any; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const seasonTeams = [...new Set(games.map(g => g.team))]
  const wins = games.filter(g => g.result === 'W').length
  const losses = games.filter(g => g.result === 'L').length
  const ties = games.filter(g => g.result === 'T').length
  const record = ties > 0 ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-3 hover:bg-gray-800/50 transition-colors text-left"
      >
        <div className="flex items-center -space-x-1.5">
          {seasonTeams.map(t => (
            <img key={t} src={teamLogoUrl(t)} alt={t} className="w-6 h-6 object-contain ring-1 ring-gray-900 rounded-full bg-gray-900" />
          ))}
        </div>
        <span className="font-semibold text-white">{season}</span>
        <span className="text-gray-500 text-xs">{seasonTeams.join(' / ')} · {record} · {games.length} games</span>
        <span className="ml-auto text-gray-600 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="overflow-x-auto border-t border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-600 text-xs border-b border-gray-800">
                <th className="py-2 px-4 font-medium">Wk</th>
                <th className="py-2 px-4 font-medium">Opponent</th>
                <th className="py-2 px-4 font-medium">Result</th>
                <th className="py-2 px-4 font-medium" colSpan={4}>Stats</th>
              </tr>
            </thead>
            <tbody>
              {games.map(g => {
                const stats = gameStatCols(g)
                const score = g.away_score !== null ? `${g.away_score}–${g.home_score}` : null
                return (
                  <tr key={g.game_id} className="border-t border-gray-800/60 hover:bg-gray-800/40">
                    <td className="py-2 px-4 text-gray-500 text-xs">{weekLabel(g.week)}</td>
                    <td className="py-2 px-4">
                      <div className="flex items-center gap-1.5">
                        <img src={teamLogoUrl(g.opponent)} alt={g.opponent} className="w-5 h-5 object-contain opacity-70" />
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
                        {score && <span className="text-gray-600 text-xs">{score}</span>}
                      </div>
                    </td>
                    {stats.map(s => (
                      <td key={s.label} className="py-2 px-4">
                        <div className="text-gray-500 text-xs">{s.label}</div>
                        <div className="font-medium text-sm">{s.val || '—'}</div>
                      </td>
                    ))}
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

export default function PlayerPage() {
  const { playerId } = useParams<{ playerId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const fromGame = (location.state as any)?.fromGame
  const [player, setPlayer] = useState<PlayerProfile | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!playerId) return
    api.player(playerId).then(setPlayer).finally(() => setLoading(false))
  }, [playerId])

  if (loading) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Loading...</p></div>
  if (!player) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Player not found.</p></div>

  const bySeason = player.games.reduce<Record<number, PlayerGame[]>>((acc, g) => {
    ;(acc[g.season] ??= []).push(g)
    return acc
  }, {})
  const seasons = Object.keys(bySeason).map(Number).sort((a, b) => b - a)

  // Derive team info from game data (authoritative — roster field lags behind trades)
  const recentGames = seasons.length > 0 ? bySeason[seasons[0]] : []
  // Unique teams in chronological order (so traded-to team appears last = current)
  const recentTeams = [...new Set(recentGames.map(g => g.team))]
  const currentTeam = recentGames[recentGames.length - 1]?.team ?? player.team

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav />
      <div className="max-w-6xl mx-auto px-4 py-8">

        {/* Breadcrumb */}
        <div className="flex items-center gap-2 mb-5">
          <button onClick={() => navigate('/?season=2025')} className="text-gray-500 hover:text-white transition-colors p-1 rounded-md hover:bg-gray-800" title="Home">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7A1 1 0 003 11h1v6a1 1 0 001 1h4v-4h2v4h4a1 1 0 001-1v-6h1a1 1 0 00.707-1.707l-7-7z" />
            </svg>
          </button>
          {fromGame && (
            <>
              <span className="text-gray-700">/</span>
              <Link to={`/?season=${fromGame.season}`} className="text-gray-400 hover:text-white text-sm transition-colors">{fromGame.season}</Link>
              {fromGame.fromWeek !== undefined && (
                <>
                  <span className="text-gray-700">/</span>
                  <Link to={`/?season=${fromGame.season}&week=${fromGame.fromWeek}`} className="text-gray-400 hover:text-white text-sm transition-colors">{weekLabel(fromGame.fromWeek)}</Link>
                </>
              )}
              <span className="text-gray-700">/</span>
              <Link to={`/games/${fromGame.gameId}`} state={{ fromWeek: fromGame.fromWeek }} className="text-gray-400 hover:text-white text-sm transition-colors">{fromGame.awayTeam} @ {fromGame.homeTeam}</Link>
            </>
          )}
          <span className="text-gray-700">/</span>
          <span className="text-gray-400 text-sm">{player.player_name}</span>
          {fromGame ? (
            <Link
              to={`/games/${fromGame.gameId}`}
              state={{ fromWeek: fromGame.fromWeek }}
              className="ml-auto flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-2 transition-colors"
            >
              ← Back
            </Link>
          ) : (
            <button
              onClick={() => navigate(-1)}
              className="ml-auto flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg px-3 py-2 transition-colors"
            >
              ← Back
            </button>
          )}
        </div>

        {/* Profile header */}
        <div className="flex items-center gap-5 mb-8">
          {player.headshot_url
            ? <img src={player.headshot_url} alt={player.player_name} className="w-20 h-20 rounded-full object-cover bg-gray-800 shrink-0" />
            : <div className="w-20 h-20 rounded-full bg-gray-800 shrink-0" />
          }
          <div className="flex-1 min-w-0">
            <h1 className="text-3xl font-bold text-white leading-tight">{player.player_name}</h1>
            <div className="text-gray-400 mt-1 flex flex-wrap items-center gap-x-1">
              {player.position}
              {recentTeams.length > 0 && (
                <>
                  <span className="mx-1">·</span>
                  {recentTeams.map((t, i) => (
                    <span key={t} className="flex items-center gap-1">
                      {i > 0 && <span className="text-gray-600 mx-0.5">/</span>}
                      <Link to={`/teams/${t}`} className="hover:text-indigo-400 transition-colors">{t}</Link>
                    </span>
                  ))}
                </>
              )}
              {player.jersey_number !== null && currentTeam ? ` · #${player.jersey_number}` : ''}
            </div>
            <div className="flex flex-wrap gap-3 mt-2 text-sm text-gray-600">
              {player.height && <span>{player.height}</span>}
              {player.weight && <span>{player.weight} lbs</span>}
              {player.age && <span>Age {player.age}</span>}
              {player.college && <span>{player.college}</span>}
              {player.entry_year && <span>Since {player.entry_year}</span>}
            </div>
          </div>
        </div>

        {/* Career stats table */}
        <CareerTable
          seasons={seasons}
          bySeason={bySeason}
          ngs={player.ngs ?? {}}
          snapTotals={player.snap_totals ?? {}}
        />

        {/* Game logs */}
        <div className="text-xs font-semibold text-gray-600 uppercase tracking-widest mb-3">Game Log</div>
        <div className="space-y-2">
          {seasons.map((s, i) => (
            <GameLog key={s} season={s} games={bySeason[s]} playerId={player.player_id} playerName={player.player_name} fromGame={fromGame} defaultOpen={i === 0} />
          ))}
        </div>

      </div>
    </div>
  )
}
