import React, { createContext, useContext, useEffect, useState } from 'react'
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine, ReferenceArea, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api } from '../api'
import type { GameDetail, PlayerStats, WinProbPlay } from '../api'
import Nav, { backBtnCls } from '../components/Nav'
import type { Crumb } from '../components/Nav'
import { teamLogoUrl, teamName } from '../utils/teams'

interface GameCtx { gameId: string; season: number; week: number; awayTeam: string; homeTeam: string; fromWeek?: number }
const GameContext = createContext<GameCtx | null>(null)

function playerLink(playerId: string, ctx: GameCtx | null) {
  if (!ctx) return { to: `/players/${playerId}`, state: undefined }
  return { to: `/players/${playerId}`, state: { fromGame: ctx } }
}

const WEEK_LABELS: Record<number, string> = { 19: 'Wild Card', 20: 'Divisional', 21: 'Conference', 22: 'Super Bowl' }
function weekLabel(w: number) { return WEEK_LABELS[w] ?? `Week ${w}` }
function sv(n: number) { return n === 0 ? '—' : n % 1 === 0 ? String(n) : n.toFixed(1) }
function ypa(y: number, a: number) { return a === 0 ? '—' : (y / a).toFixed(1) }

// ── Card 1: Scoreboard ────────────────────────────────────────────────────────

function formatGameday(s: string | null) {
  if (!s) return 'TBD'
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function Scoreboard({ game }: { game: GameDetail }) {
  const awayWon = game.away_score !== null && game.home_score !== null && game.away_score > game.home_score
  const homeWon = game.away_score !== null && game.home_score !== null && game.home_score > game.away_score
  const isFinal = game.away_score !== null

  const qs = game.quarter_scores ?? []
  const hasOT = qs.some(q => q.qtr >= 5)
  const quarters = [1, 2, 3, 4, ...(hasOT ? [5] : [])]
  const byQtr = Object.fromEntries(qs.map(q => [q.qtr, q]))

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-4">
      {/* Strip */}
      <div className="px-4 py-2 border-b border-gray-800/60 text-center">
        <span className="text-xs text-gray-500 uppercase tracking-wider font-medium">
          {weekLabel(game.week)} · {formatGameday(game.gameday)} · {game.season} Season
        </span>
      </div>

      {/* Teams + score */}
      <div className="flex items-center px-6 py-6 gap-2">
        <Link to={`/teams/${game.away_team}`}
          className={`flex flex-col items-center gap-2 group flex-1 transition-opacity ${awayWon || !isFinal ? '' : 'opacity-50 hover:opacity-75'}`}>
          <img src={teamLogoUrl(game.away_team)} alt={game.away_team}
            className="w-16 h-16 object-contain group-hover:scale-105 transition-transform" />
          <div className="text-center">
            <div className="font-bold text-white text-sm group-hover:text-indigo-400 transition-colors leading-tight">
              {teamName(game.away_team)}
            </div>
            {game.away_record && <div className="text-xs text-gray-600 mt-0.5">{game.away_record}</div>}
          </div>
        </Link>

        <div className="flex flex-col items-center gap-1 shrink-0 px-3">
          {isFinal && <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">Final</span>}
          {isFinal ? (
            <div className="flex items-center gap-3">
              <span className={`text-5xl font-black tabular-nums ${awayWon ? 'text-white' : 'text-gray-600'}`}>
                {game.away_score}
              </span>
              <span className="text-gray-700 text-2xl font-thin">·</span>
              <span className={`text-5xl font-black tabular-nums ${homeWon ? 'text-white' : 'text-gray-600'}`}>
                {game.home_score}
              </span>
            </div>
          ) : (
            <span className="text-gray-600 text-sm">Upcoming</span>
          )}
        </div>

        <Link to={`/teams/${game.home_team}`}
          className={`flex flex-col items-center gap-2 group flex-1 transition-opacity ${homeWon || !isFinal ? '' : 'opacity-50 hover:opacity-75'}`}>
          <img src={teamLogoUrl(game.home_team)} alt={game.home_team}
            className="w-16 h-16 object-contain group-hover:scale-105 transition-transform" />
          <div className="text-center">
            <div className="font-bold text-white text-sm group-hover:text-indigo-400 transition-colors leading-tight">
              {teamName(game.home_team)}
            </div>
            {game.home_record && <div className="text-xs text-gray-600 mt-0.5">{game.home_record}</div>}
          </div>
        </Link>
      </div>

      {/* Quarter breakdown */}
      {qs.length > 0 && (
        <div className="mx-4 mb-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="pb-2 pl-3 pr-2 text-left w-20" />
                {quarters.map(q => (
                  <th key={q} className="pb-2 px-4 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    {q <= 4 ? `Q${q}` : 'OT'}
                  </th>
                ))}
                <th className="pb-2 px-4 text-center text-xs font-bold text-gray-400 uppercase tracking-wider border-l border-gray-800">
                  Final
                </th>
              </tr>
            </thead>
            <tbody>
              {[
                { team: game.away_team, won: awayWon, total: game.away_score, key: 'away' as const },
                { team: game.home_team, won: homeWon, total: game.home_score, key: 'home' as const },
              ].map(({ team, won, total, key }) => (
                <tr key={team} className="border-t border-gray-800/40">
                  <td className="py-3 pl-3 pr-2">
                    <div className="flex items-center gap-2">
                      <img src={teamLogoUrl(team)} className="w-5 h-5 object-contain" alt="" />
                      <span className="font-bold text-gray-300 text-sm">{team}</span>
                    </div>
                  </td>
                  {quarters.map(q => (
                    <td key={q} className="py-3 px-4 text-center tabular-nums text-gray-400 text-base">
                      {byQtr[q]?.[key] ?? '—'}
                    </td>
                  ))}
                  <td className={`py-3 px-4 text-center tabular-nums text-lg font-black border-l border-gray-800 ${won ? 'text-white' : 'text-gray-600'}`}>
                    {total ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Venue */}
      {(game.stadium || game.temp !== null || game.wind !== null || game.surface || game.roof) && (
        <div className="px-4 py-2.5 border-t border-gray-800/60 flex flex-wrap justify-center gap-x-3 gap-y-0.5 text-xs text-gray-600">
          {game.stadium && <span>{game.stadium}</span>}
          {game.temp !== null && <span>{game.temp}°F</span>}
          {game.wind !== null && game.wind > 0 && <span>{game.wind} mph wind</span>}
          {game.surface && <span className="capitalize">{game.surface}</span>}
          {game.roof && <span className="capitalize">{game.roof}</span>}
        </div>
      )}
    </div>
  )
}

// ── Card 2: Team stats (away | label | home) ──────────────────────────────────

function teamTotals(players: PlayerStats[]) {
  const sum = (fn: (p: PlayerStats) => number) => players.reduce((a, p) => a + fn(p), 0)
  return {
    totalYds:   sum(p => p.pass_yards + p.rush_yards),
    passCmp:    sum(p => p.completions),
    passAtt:    sum(p => p.attempts),
    passYds:    sum(p => p.pass_yards),
    passTDs:    sum(p => p.pass_tds),
    ints:       sum(p => p.interceptions_thrown),
    sacksTaken: sum(p => p.sacks_taken),
    rushCar:    sum(p => p.carries),
    rushYds:    sum(p => p.rush_yards),
    rushTDs:    sum(p => p.rush_tds),
    sacks:      sum(p => p.sacks),
    defInts:    sum(p => p.def_interceptions),
  }
}

function BoxScore({ game }: { game: GameDetail }) {
  const A = teamTotals(game.away)
  const H = teamTotals(game.home)
  if (!A.passAtt && !A.rushCar && !H.passAtt && !H.rushCar) return null

  function StatBar({ label, a, h, lo = false, neutral = false }: {
    label: string; a: string | number; h: string | number; lo?: boolean; neutral?: boolean
  }) {
    const av = typeof a === 'number' ? a : parseFloat(String(a)) || 0
    const hv = typeof h === 'number' ? h : parseFloat(String(h)) || 0
    const total = av + hv
    const aPct = total > 0 ? (av / total) * 100 : 50
    const hPct = total > 0 ? (hv / total) * 100 : 50
    const aWon = !neutral && av !== hv && (lo ? av < hv : av > hv)
    const hWon = !neutral && av !== hv && (lo ? hv < av : hv > av)
    return (
      <div className="px-5 py-2.5">
        <div className="flex items-baseline justify-between gap-3 mb-1.5">
          <span className={`text-base font-bold tabular-nums w-20 text-right ${aWon ? 'text-white' : 'text-gray-500'}`}>{a}</span>
          <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider text-center">{label}</span>
          <span className={`text-base font-bold tabular-nums w-20 text-left ${hWon ? 'text-white' : 'text-gray-500'}`}>{h}</span>
        </div>
        {!neutral && total > 0 && (
          <div className="relative h-1 rounded-full bg-gray-800/60 overflow-hidden flex">
            <div className={`h-full ${aWon ? 'bg-rose-400' : 'bg-rose-400/30'}`} style={{ width: `${aPct}%` }} />
            <div className={`h-full ${hWon ? 'bg-indigo-400' : 'bg-indigo-400/30'}`} style={{ width: `${hPct}%` }} />
          </div>
        )}
      </div>
    )
  }

  function SectionDivider({ label }: { label: string }) {
    return (
      <div className="px-5 pt-3 pb-1 text-center text-[10px] font-bold text-gray-500 uppercase tracking-widest border-t border-gray-800/40 mt-1">
        {label}
      </div>
    )
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-4">
      {/* Header */}
      <div className="flex items-center border-b border-gray-800 bg-gray-800/40">
        <div className="flex-1 flex items-center justify-end gap-2 px-5 py-3">
          <span className="font-bold text-white text-sm">{game.away_team}</span>
          <img src={teamLogoUrl(game.away_team)} className="w-6 h-6 object-contain" alt="" />
        </div>
        <div className="w-28 text-center text-[10px] font-bold text-gray-500 uppercase tracking-widest shrink-0">
          Team Stats
        </div>
        <div className="flex-1 flex items-center justify-start gap-2 px-5 py-3">
          <img src={teamLogoUrl(game.home_team)} className="w-6 h-6 object-contain" alt="" />
          <span className="font-bold text-white text-sm">{game.home_team}</span>
        </div>
      </div>

      <div className="pb-3">
        <StatBar label="Total Yards"   a={A.totalYds} h={H.totalYds} />
        <SectionDivider label="Passing" />
        <StatBar label="Comp / Att"    a={`${A.passCmp}/${A.passAtt}`} h={`${H.passCmp}/${H.passAtt}`} neutral />
        <StatBar label="Yards"         a={A.passYds}    h={H.passYds} />
        <StatBar label="Touchdowns"    a={A.passTDs}    h={H.passTDs} />
        <StatBar label="Interceptions" a={A.ints}       h={H.ints}       lo />
        <StatBar label="Sacks Taken"   a={A.sacksTaken} h={H.sacksTaken} lo />
        <SectionDivider label="Rushing" />
        <StatBar label="Carries"       a={A.rushCar}  h={H.rushCar}  neutral />
        <StatBar label="Yards"         a={A.rushYds}  h={H.rushYds} />
        <StatBar label="Touchdowns"    a={A.rushTDs}  h={H.rushTDs} />
        <SectionDivider label="Defense" />
        <StatBar label="Sacks"         a={A.sacks}   h={H.sacks} />
        <StatBar label="Interceptions" a={A.defInts} h={H.defInts} />
      </div>
    </div>
  )
}

// ── Card 3: Game Leaders ──────────────────────────────────────────────────────

function GameLeaders({ game }: { game: GameDetail }) {
  const ctx = useContext(GameContext)
  type Leader = { player: PlayerStats; stat: string; sub: string } | null

  function top(
    players: PlayerStats[],
    filter: (p: PlayerStats) => boolean,
    sortVal: (p: PlayerStats) => number,
    statFn: (p: PlayerStats) => string,
    subFn: (p: PlayerStats) => string,
  ): Leader {
    const p = [...players].filter(filter).sort((a, b) => sortVal(b) - sortVal(a))[0]
    return p ? { player: p, stat: statFn(p), sub: subFn(p) } : null
  }

  const categories = [
    {
      label: 'Passing Yds',
      away: top(game.away, p => p.attempts > 0, p => p.pass_yards,
        p => sv(p.pass_yards),
        p => `${p.completions}/${p.attempts}, ${p.pass_tds} TD${p.interceptions_thrown ? `, ${p.interceptions_thrown} INT` : ''}`),
      home: top(game.home, p => p.attempts > 0, p => p.pass_yards,
        p => sv(p.pass_yards),
        p => `${p.completions}/${p.attempts}, ${p.pass_tds} TD${p.interceptions_thrown ? `, ${p.interceptions_thrown} INT` : ''}`),
    },
    {
      label: 'Rushing Yds',
      away: top(game.away, p => p.carries > 0, p => p.rush_yards,
        p => sv(p.rush_yards),
        p => `${p.carries} CAR${p.rush_tds ? `, ${p.rush_tds} TD` : ''}`),
      home: top(game.home, p => p.carries > 0, p => p.rush_yards,
        p => sv(p.rush_yards),
        p => `${p.carries} CAR${p.rush_tds ? `, ${p.rush_tds} TD` : ''}`),
    },
    {
      label: 'Receiving Yds',
      away: top(game.away, p => p.targets > 0, p => p.rec_yards,
        p => sv(p.rec_yards),
        p => `${p.receptions}/${p.targets} TGT${p.rec_tds ? `, ${p.rec_tds} TD` : ''}`),
      home: top(game.home, p => p.targets > 0, p => p.rec_yards,
        p => sv(p.rec_yards),
        p => `${p.receptions}/${p.targets} TGT${p.rec_tds ? `, ${p.rec_tds} TD` : ''}`),
    },
    {
      label: 'Tackles',
      away: top(game.away, p => p.solo_tackles + p.assist_tackles > 0,
        p => p.solo_tackles + p.assist_tackles,
        p => sv(p.solo_tackles + p.assist_tackles),
        p => `${p.solo_tackles} SOLO${p.sacks ? `, ${sv(p.sacks)} SCK` : ''}`),
      home: top(game.home, p => p.solo_tackles + p.assist_tackles > 0,
        p => p.solo_tackles + p.assist_tackles,
        p => sv(p.solo_tackles + p.assist_tackles),
        p => `${p.solo_tackles} SOLO${p.sacks ? `, ${sv(p.sacks)} SCK` : ''}`),
    },
  ]

  if (categories.every(c => !c.away && !c.home)) return null

  function Side({ leader, align }: { leader: Leader; align: 'left' | 'right' }) {
    if (!leader) return <div className="flex-1" />
    const { to, state } = playerLink(leader.player.player_id, ctx)
    const rev = align === 'right'
    return (
      <div className={`flex-1 flex items-center gap-3 min-w-0 ${rev ? 'flex-row-reverse' : ''}`}>
        {leader.player.headshot_url
          ? <img src={leader.player.headshot_url} alt="" className="w-12 h-12 rounded-full object-cover object-top shrink-0 bg-gray-800" />
          : <div className="w-12 h-12 rounded-full bg-gray-800 shrink-0" />
        }
        <div className={`min-w-0 ${rev ? 'text-right' : ''}`}>
          <div className="text-xl font-black text-white tabular-nums leading-none">{leader.stat}</div>
          <Link to={to} state={state} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight block truncate mt-0.5">
            {leader.player.player_name}
          </Link>
          <div className="text-[11px] text-gray-500 mt-0.5">{leader.sub}</div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-4">
      <div className="px-4 py-2.5 border-b border-gray-800 bg-gray-800/40">
        <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">Game Leaders</span>
      </div>
      <div className="divide-y divide-gray-800/40">
        {categories.map(({ label, away, home }) => (away || home) && (
          <div key={label} className="flex items-center gap-3 px-4 py-3">
            <Side leader={away} align="left" />
            <div className="shrink-0 w-32 text-center">
              <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider">{label}</span>
            </div>
            <Side leader={home} align="right" />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Card 4: Player stats (conventional sheet, no tabs) ────────────────────────

function TeamDivider({ team }: { team: string }) {
  return (
    <tr className="bg-gray-800/40 border-t border-gray-800/60">
      <td colSpan={20} className="px-4 py-2">
        <div className="flex items-center gap-2.5">
          <img src={teamLogoUrl(team)} className="w-6 h-6 object-contain" alt="" />
          <span className="text-sm font-bold text-white">{team}</span>
          <span className="text-xs text-gray-600">·</span>
          <span className="text-xs text-gray-500">{teamName(team)}</span>
        </div>
      </td>
    </tr>
  )
}

function PlayerStats({ game }: { game: GameDetail }) {
  const ctx = useContext(GameContext)

  function PLink({ p }: { p: PlayerStats }) {
    const { to, state } = playerLink(p.player_id, ctx)
    return (
      <td className="py-2 px-4 whitespace-nowrap">
        <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium text-sm">
          {p.player_name}
        </Link>
        {p.jersey_number !== null && <span className="text-gray-700 text-xs ml-1">#{p.jersey_number}</span>}
      </td>
    )
  }

  const TH = (label: string) => (
    <th key={label} className="py-2.5 px-3 text-right text-xs font-semibold text-gray-600 whitespace-nowrap">{label}</th>
  )
  const THL = (label: string) => (
    <th key={label} className="py-2.5 px-4 text-left text-xs font-semibold text-gray-600 whitespace-nowrap">{label}</th>
  )
  const TD = (val: string | number, dim = false) => {
    const empty = val === 0 || val === '0'
    return (
      <td className={`py-2 px-3 text-right tabular-nums text-sm whitespace-nowrap
        ${empty ? 'text-gray-700' : dim ? 'text-gray-500' : 'text-gray-300'}`}>
        {empty ? '—' : val}
      </td>
    )
  }

  const rowCls = 'border-t border-gray-800/40 hover:bg-gray-800/30'

  const passers   = { away: game.away.filter(p => p.attempts > 0), home: game.home.filter(p => p.attempts > 0) }
  const rushers   = { away: [...game.away].filter(p => p.carries > 0).sort((a, b) => b.rush_yards - a.rush_yards),
                      home: [...game.home].filter(p => p.carries > 0).sort((a, b) => b.rush_yards - a.rush_yards) }
  const receivers = { away: [...game.away].filter(p => p.targets > 0).sort((a, b) => b.rec_yards - a.rec_yards),
                      home: [...game.home].filter(p => p.targets > 0).sort((a, b) => b.rec_yards - a.rec_yards) }
  const defenders = { away: [...game.away].filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
                               .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles)),
                      home: [...game.home].filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
                               .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles)) }

  function Section({ title, headers, children }: { title: string; headers: React.ReactNode[]; children: React.ReactNode }) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-4 py-2.5 bg-gray-800/50 border-b border-gray-800">
          <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">{title}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800/60 bg-gray-800/20">{headers}</tr>
            </thead>
            <tbody>{children}</tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">

      {/* Passing */}
      {(passers.away.length > 0 || passers.home.length > 0) && (
        <Section title="Passing" headers={[THL('Player'), TH('C/ATT'), TH('YDS'), TH('Y/A'), TH('TD'), TH('INT'), TH('SCK'), TH('EPA')]}>
          {([{ team: game.away_team, list: passers.away }, { team: game.home_team, list: passers.home }] as const).map(({ team, list }) =>
            list.length === 0 ? null : (
              <React.Fragment key={team}>
                <TeamDivider team={team} />
                {list.map(p => (
                  <tr key={p.player_id} className={rowCls}>
                    <PLink p={p} />
                    {TD(`${p.completions}/${p.attempts}`)}
                    {TD(sv(p.pass_yards))}
                    {TD(ypa(p.pass_yards, p.attempts), true)}
                    {TD(p.pass_tds)}
                    {TD(p.interceptions_thrown)}
                    {TD(p.sacks_taken)}
                    {TD(sv(p.pass_epa), true)}
                  </tr>
                ))}
              </React.Fragment>
            )
          )}
        </Section>
      )}

      {/* Rushing */}
      {(rushers.away.length > 0 || rushers.home.length > 0) && (
        <Section title="Rushing" headers={[THL('Player'), TH('CAR'), TH('YDS'), TH('Y/C'), TH('TD'), TH('EPA')]}>
          {([{ team: game.away_team, list: rushers.away }, { team: game.home_team, list: rushers.home }] as const).map(({ team, list }) =>
            list.length === 0 ? null : (
              <React.Fragment key={team}>
                <TeamDivider team={team} />
                {list.map(p => (
                  <tr key={p.player_id} className={rowCls}>
                    <PLink p={p} />
                    {TD(p.carries)}
                    {TD(sv(p.rush_yards))}
                    {TD(ypa(p.rush_yards, p.carries), true)}
                    {TD(p.rush_tds)}
                    {TD(sv(p.rush_epa), true)}
                  </tr>
                ))}
              </React.Fragment>
            )
          )}
        </Section>
      )}

      {/* Receiving */}
      {(receivers.away.length > 0 || receivers.home.length > 0) && (
        <Section title="Receiving" headers={[THL('Player'), TH('REC/TGT'), TH('YDS'), TH('Y/R'), TH('TD'), TH('YAC'), TH('EPA')]}>
          {([{ team: game.away_team, list: receivers.away }, { team: game.home_team, list: receivers.home }] as const).map(({ team, list }) =>
            list.length === 0 ? null : (
              <React.Fragment key={team}>
                <TeamDivider team={team} />
                {list.map(p => (
                  <tr key={p.player_id} className={rowCls}>
                    <PLink p={p} />
                    {TD(`${p.receptions}/${p.targets}`)}
                    {TD(sv(p.rec_yards))}
                    {TD(ypa(p.rec_yards, p.receptions), true)}
                    {TD(p.rec_tds)}
                    {TD(sv(p.yac), true)}
                    {TD(sv(p.rec_epa), true)}
                  </tr>
                ))}
              </React.Fragment>
            )
          )}
        </Section>
      )}

      {/* Defense */}
      {(defenders.away.length > 0 || defenders.home.length > 0) && (
        <Section title="Defense" headers={[THL('Player'), TH('TOT'), TH('SOLO'), TH('AST'), TH('SACK'), TH('TFL'), TH('INT'), TH('PBU')]}>
          {([{ team: game.away_team, list: defenders.away }, { team: game.home_team, list: defenders.home }] as const).map(({ team, list }) =>
            list.length === 0 ? null : (
              <React.Fragment key={team}>
                <TeamDivider team={team} />
                {list.map(p => (
                  <tr key={p.player_id} className={rowCls}>
                    <PLink p={p} />
                    {TD(sv(p.solo_tackles + p.assist_tackles))}
                    {TD(sv(p.solo_tackles))}
                    {TD(sv(p.assist_tackles), true)}
                    {TD(sv(p.sacks))}
                    {TD(sv(p.tackles_for_loss), true)}
                    {TD(p.def_interceptions)}
                    {TD(p.pass_breakups)}
                  </tr>
                ))}
              </React.Fragment>
            )
          )}
        </Section>
      )}

    </div>
  )
}

// ── Win probability chart ─────────────────────────────────────────────────────

function fmtRemaining(rem: number): string {
  if (rem < 0) {
    const elapsedOT = -rem
    const min = Math.floor((600 - elapsedOT) / 60)
    const sec = (600 - elapsedOT) % 60
    return `OT ${Math.max(0, min)}:${Math.max(0, sec).toString().padStart(2, '0')}`
  }
  const qtr = rem > 2700 ? 1 : rem > 1800 ? 2 : rem > 900 ? 3 : 4
  const secInQtr = rem - (qtr === 1 ? 2700 : qtr === 2 ? 1800 : qtr === 3 ? 900 : 0)
  const min = Math.floor(secInQtr / 60)
  const sec = secInQtr % 60
  return `Q${qtr} ${min}:${sec.toString().padStart(2, '0')}`
}

// ── Key plays (scoring + turnovers) ───────────────────────────────────────────

type KeyPlayKind = 'td' | 'fg' | 'int' | 'fum'
interface KeyPlayItem {
  qtr: number
  rem: number
  team: string | null
  desc: string | null
  kind: KeyPlayKind
  wpSwing: number  // points of WP added for the offense
}

function detectKeyPlays(plays: WinProbPlay[]): KeyPlayItem[] {
  const out: KeyPlayItem[] = []
  for (let i = 0; i < plays.length; i++) {
    const p = plays[i]
    const prevHomeWp = i > 0 ? plays[i - 1].home_wp : 0.5
    const homeSwing = (p.home_wp - prevHomeWp) * 100
    if (p.touchdown === 1) {
      out.push({ qtr: p.qtr, rem: p.game_seconds_remaining, team: p.posteam, desc: p.desc, kind: 'td', wpSwing: homeSwing })
    } else if (/field goal is good/i.test(p.desc ?? '')) {
      out.push({ qtr: p.qtr, rem: p.game_seconds_remaining, team: p.posteam, desc: p.desc, kind: 'fg', wpSwing: homeSwing })
    }
    if (p.interception === 1) {
      out.push({ qtr: p.qtr, rem: p.game_seconds_remaining, team: p.posteam, desc: p.desc, kind: 'int', wpSwing: homeSwing })
    } else if (p.fumble_lost === 1) {
      out.push({ qtr: p.qtr, rem: p.game_seconds_remaining, team: p.posteam, desc: p.desc, kind: 'fum', wpSwing: homeSwing })
    }
  }
  return out.sort((a, b) => b.rem - a.rem)
}

const KIND_META: Record<KeyPlayKind, { label: string; color: string; bg: string }> = {
  td:  { label: 'TD',  color: 'text-emerald-300', bg: 'bg-emerald-500/15 border-emerald-500/30' },
  fg:  { label: 'FG',  color: 'text-amber-300',   bg: 'bg-amber-500/15 border-amber-500/30' },
  int: { label: 'INT', color: 'text-rose-300',    bg: 'bg-rose-500/15 border-rose-500/30' },
  fum: { label: 'FUM', color: 'text-rose-300',    bg: 'bg-rose-500/15 border-rose-500/30' },
}

function KeyPlays({ game }: { game: GameDetail }) {
  const plays = detectKeyPlays(game.win_prob ?? [])
  if (!plays.length) return null
  const homeTeam = game.home_team
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-4">
      <div className="px-4 py-2.5 border-b border-gray-800 bg-gray-800/40 flex items-center justify-between">
        <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">Key Plays</span>
        <span className="text-[10px] text-gray-600 uppercase tracking-wider">{plays.length} events</span>
      </div>
      <div className="divide-y divide-gray-800/40 max-h-96 overflow-y-auto">
        {plays.map((p, i) => {
          const isHome = p.team === homeTeam
          // For scoring plays, swing is in offense's favor; for turnovers, against
          const offSwing = isHome ? p.wpSwing : -p.wpSwing
          const swingStr = Math.abs(offSwing) >= 1 ? `${offSwing >= 0 ? '+' : ''}${offSwing.toFixed(0)}%` : null
          const meta = KIND_META[p.kind]
          return (
            <div key={i} className={`flex items-center gap-3 px-4 py-2.5 border-l-2 ${isHome ? 'border-l-indigo-500/60' : 'border-l-rose-500/60'}`}>
              <div className="shrink-0 w-12 text-[11px] text-gray-500 font-mono tabular-nums">{fmtRemaining(p.rem)}</div>
              <img src={teamLogoUrl(p.team ?? '')} className="w-5 h-5 object-contain shrink-0 opacity-70" alt="" />
              <span className={`shrink-0 inline-block text-[10px] font-bold uppercase tracking-wider border rounded px-1.5 py-0.5 ${meta.color} ${meta.bg}`}>
                {meta.label}
              </span>
              <p className="flex-1 text-xs text-gray-400 leading-snug line-clamp-2 min-w-0">{p.desc}</p>
              {swingStr && (
                <span className={`shrink-0 text-[11px] tabular-nums font-semibold ${offSwing >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {swingStr} WP
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function WpTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as ChartPoint
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl px-3 py-2.5 shadow-2xl max-w-[220px] pointer-events-none">
      <div className="flex justify-between gap-3 text-xs font-bold mb-1.5">
        <span className="text-rose-400">{d.awayTeam} {(100 - d.wp).toFixed(1)}%</span>
        <span className="text-gray-600 font-normal">{fmtRemaining(d.rem)}</span>
        <span className="text-indigo-400">{d.homeTeam} {d.wp.toFixed(1)}%</span>
      </div>
      {d.desc && <p className="text-[11px] text-gray-500 leading-snug line-clamp-2">{d.desc}</p>}
    </div>
  )
}

interface ChartPoint {
  t: number; wp: number; rem: number; desc: string | null
  td: boolean; turnover: boolean; posteam: string | null
  homeTeam: string; awayTeam: string
}

function WinProbabilityChart({ game }: { game: GameDetail }) {
  const plays = game.win_prob
  if (!plays?.length) return null

  const homeTeam = game.home_team
  const awayTeam = game.away_team

  const data: ChartPoint[] = plays.map((p: WinProbPlay) => ({
    t: 3600 - p.game_seconds_remaining,
    wp: Math.round(p.home_wp * 1000) / 10,
    rem: p.game_seconds_remaining,
    desc: p.desc,
    td: p.touchdown === 1,
    turnover: p.interception === 1 || p.fumble_lost === 1,
    posteam: p.posteam,
    homeTeam,
    awayTeam,
  }))

  const maxT = Math.max(3600, data[data.length - 1]?.t ?? 3600)
  const finalWp = data[data.length - 1]?.wp ?? 50
  const scoringPlays = data.filter(d => d.td)
  const turnovers = data.filter(d => d.turnover)

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-4">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Win Probability</span>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-rose-500 inline-block" />{awayTeam}</span>
          <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-indigo-400 inline-block" />{homeTeam}</span>
        </div>
      </div>

      <div className="px-1 pt-3 pb-1">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="wpFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="#818cf8" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#818cf8" stopOpacity={0.02} />
              </linearGradient>
            </defs>

            <CartesianGrid vertical={false} stroke="#1f2937" strokeDasharray="0" />

            {/* Background territory tint */}
            <ReferenceArea y1={50} y2={100} fill="#6366f1" fillOpacity={0.05} ifOverflow="hidden" />
            <ReferenceArea y1={0}  y2={50}  fill="#f43f5e" fillOpacity={0.05} ifOverflow="hidden" />

            {/* 50% line */}
            <ReferenceLine y={50} stroke="#374151" strokeDasharray="4 3" strokeWidth={1} />

            {/* Quarter separators */}
            {[900, 1800, 2700, 3600].filter(t => t < maxT).map(t => (
              <ReferenceLine key={t} x={t} stroke="#1f2937" strokeWidth={1.5} />
            ))}

            {/* Scoring play markers */}
            {scoringPlays.map((d, i) => (
              <ReferenceLine key={`td-${i}`} x={d.t} strokeWidth={1.5} strokeOpacity={0.55}
                stroke={d.posteam === homeTeam ? '#818cf8' : '#fb7185'} />
            ))}
            {turnovers.map((d, i) => (
              <ReferenceLine key={`to-${i}`} x={d.t} strokeWidth={1} strokeOpacity={0.4}
                stroke={d.posteam === homeTeam ? '#fb7185' : '#818cf8'} strokeDasharray="2 2" />
            ))}

            <XAxis dataKey="t" type="number" domain={[0, maxT]}
              ticks={[450, 1350, 2250, 3150, ...(maxT > 3600 ? [3825] : [])]}
              tickFormatter={v => (({ 450: 'Q1', 1350: 'Q2', 2250: 'Q3', 3150: 'Q4', 3825: 'OT' } as Record<number, string>)[v] ?? '')}
              tick={{ fill: '#4b5563', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} ticks={[0, 50, 100]}
              tickFormatter={v => v === 50 ? '50%' : `${v}%`}
              tick={{ fill: '#374151', fontSize: 10 }} axisLine={false} tickLine={false} width={34} />

            <Tooltip content={<WpTooltip />} cursor={{ stroke: '#6b7280', strokeWidth: 1, strokeDasharray: '3 3' }} />

            <Area type="monotone" dataKey="wp" stroke="#818cf8" strokeWidth={2.5}
              fill="url(#wpFill)" dot={false}
              activeDot={{ r: 5, fill: '#818cf8', stroke: '#1e1b4b', strokeWidth: 2 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Footer */}
      <div className="px-5 pb-4 pt-1 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <img src={teamLogoUrl(awayTeam)} className="w-6 h-6 object-contain opacity-60" alt="" />
          <span className="text-lg font-black tabular-nums text-rose-400">{(100 - finalWp).toFixed(0)}%</span>
        </div>
        <span className="text-[10px] text-gray-700 uppercase tracking-widest">final</span>
        <div className="flex items-center gap-2">
          <span className="text-lg font-black tabular-nums text-indigo-400">{finalWp.toFixed(0)}%</span>
          <img src={teamLogoUrl(homeTeam)} className="w-6 h-6 object-contain opacity-60" alt="" />
        </div>
      </div>
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

  useEffect(() => {
    if (!gameId) return
    api.game(gameId).then(setGame).finally(() => setLoading(false))
  }, [gameId])

  if (loading) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Loading...</p></div>
  if (!game) return <div className="min-h-screen bg-gray-950"><Nav /><p className="p-8 text-gray-500">Game not found.</p></div>

  const crumbs: Crumb[] = []
  if (fromPlayer) {
    crumbs.push({
      label: fromPlayer.playerName,
      to: `/players/${fromPlayer.playerId}`,
      state: (fromPlayer as any).fromGame ? { fromGame: (fromPlayer as any).fromGame } : undefined,
    })
  } else if (fromWeek !== undefined) {
    crumbs.push({ label: weekLabel(fromWeek), to: `/?season=${game.season}&week=${fromWeek}` })
  }
  crumbs.push({ label: `${game.away_team} @ ${game.home_team}` })

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav crumbs={crumbs} />
      <div className="max-w-3xl mx-auto px-4 py-8">
        <button onClick={() => navigate(-1)} className={`${backBtnCls} mb-6`}>← Back</button>

        <GameContext.Provider value={{ gameId: game.game_id, season: game.season, week: game.week, awayTeam: game.away_team, homeTeam: game.home_team, fromWeek }}>
          <Scoreboard game={game} />
          <WinProbabilityChart game={game} />
          <KeyPlays game={game} />
          <GameLeaders game={game} />
          <BoxScore game={game} />
          {(game.away.length > 0 || game.home.length > 0) && <PlayerStats game={game} />}
        </GameContext.Provider>

      </div>
    </div>
  )
}
