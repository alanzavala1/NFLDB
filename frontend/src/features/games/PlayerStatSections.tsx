import React from 'react'
import { hasReceivingActivity } from '../../utils/receiving'
import { Link } from 'react-router-dom'
import type { GameDetail, GamePlayerStats } from '../../types'
import type { GameOrigin } from '../../types/navigation'
import Card from '../../components/Card'
import { teamLogoUrl, teamName } from '../../utils/teams'
import { formatStat, formatYardsPerAttempt } from './formatting'
import { playerLink } from './navigation'

function TeamDivider({ team }: { team: string }) {
  return (
    <tr className="bg-surface-raise/40 border-t border-surface-line/60">
      <td colSpan={20} className="px-4 py-2">
        <div className="flex items-center gap-2.5">
          <img src={teamLogoUrl(team)} className="w-6 h-6 object-contain" alt="" />
          <span className="text-sm font-bold text-white">{team}</span>
          <span className="text-xs text-ink-dim">·</span>
          <span className="text-xs text-ink-dim">{teamName(team)}</span>
        </div>
      </td>
    </tr>
  )
}

function PlayerLinkCell({ p, origin }: { p: GamePlayerStats; origin: GameOrigin }) {
  const { to, state } = playerLink(p.player_id, origin)
  return (
    <td className="py-2 px-4 whitespace-nowrap">
      <Link to={to} state={state} className="text-indigo-400 hover:underline font-medium text-sm">
        {p.player_name}
      </Link>
      {p.jersey_number !== null && <span className="text-ink-dim text-xs ml-1">#{p.jersey_number}</span>}
    </td>
  )
}

function StatSection({ title, headers, children }: { title: string; headers: React.ReactNode[]; children: React.ReactNode }) {
  return (
    <Card title={title}>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-surface-line/60 bg-surface-raise/20">{headers}</tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </Card>
  )
}

export function PlayerStatSections({ game, origin }: { game: GameDetail; origin: GameOrigin }) {
  const TH = (label: string) => (
    <th key={label} className="py-2.5 px-3 text-right text-xs font-semibold text-ink-dim whitespace-nowrap">{label}</th>
  )
  const THL = (label: string) => (
    <th key={label} className="py-2.5 px-4 text-left text-xs font-semibold text-ink-dim whitespace-nowrap">{label}</th>
  )
  const TD = (val: string | number, dim = false) => {
    const empty = val === 0 || val === '0'
    return (
      <td className={`py-2 px-3 text-right tabular-nums text-sm whitespace-nowrap
        ${empty ? 'text-ink-dim' : dim ? 'text-ink-dim' : 'text-ink-mid'}`}>
        {empty ? '—' : val}
      </td>
    )
  }

  const rowCls = 'border-t border-surface-line/40 hover:bg-surface-raise/30'

  const passers   = { away: game.away.filter(p => p.attempts > 0), home: game.home.filter(p => p.attempts > 0) }
  const rushers   = { away: [...game.away].filter(p => p.carries > 0).sort((a, b) => b.rush_yards - a.rush_yards),
                      home: [...game.home].filter(p => p.carries > 0).sort((a, b) => b.rush_yards - a.rush_yards) }
  const receivers = { away: [...game.away].filter(p => hasReceivingActivity(p)).sort((a, b) => b.rec_yards - a.rec_yards),
                      home: [...game.home].filter(p => hasReceivingActivity(p)).sort((a, b) => b.rec_yards - a.rec_yards) }
  const defenders = { away: [...game.away].filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
                               .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles)),
                      home: [...game.home].filter(p => p.solo_tackles + p.assist_tackles + p.sacks + p.def_interceptions > 0)
                               .sort((a, b) => (b.solo_tackles + b.assist_tackles) - (a.solo_tackles + a.assist_tackles)) }

  return (
    <div className="space-y-4">

      {/* Passing */}
      {(passers.away.length > 0 || passers.home.length > 0) && (
        <StatSection title="Passing" headers={[THL('Player'), TH('C/ATT'), TH('YDS'), TH('Y/A'), TH('TD'), TH('INT'), TH('SCK'), TH('EPA')]}>
          {([{ team: game.away_team, list: passers.away }, { team: game.home_team, list: passers.home }] as const).map(({ team, list }) =>
            list.length === 0 ? null : (
              <React.Fragment key={team}>
                <TeamDivider team={team} />
                {list.map(p => (
                  <tr key={p.player_id} className={rowCls}>
                    <PlayerLinkCell p={p} origin={origin} />
                    {TD(`${p.completions}/${p.attempts}`)}
                    {TD(formatStat(p.pass_yards))}
                    {TD(formatYardsPerAttempt(p.pass_yards, p.attempts), true)}
                    {TD(p.pass_tds)}
                    {TD(p.interceptions_thrown)}
                    {TD(p.sacks_taken)}
                    {TD(formatStat(p.pass_epa), true)}
                  </tr>
                ))}
              </React.Fragment>
            )
          )}
        </StatSection>
      )}

      {/* Rushing */}
      {(rushers.away.length > 0 || rushers.home.length > 0) && (
        <StatSection title="Rushing" headers={[THL('Player'), TH('CAR'), TH('YDS'), TH('Y/C'), TH('TD'), TH('EPA')]}>
          {([{ team: game.away_team, list: rushers.away }, { team: game.home_team, list: rushers.home }] as const).map(({ team, list }) =>
            list.length === 0 ? null : (
              <React.Fragment key={team}>
                <TeamDivider team={team} />
                {list.map(p => (
                  <tr key={p.player_id} className={rowCls}>
                    <PlayerLinkCell p={p} origin={origin} />
                    {TD(p.carries)}
                    {TD(formatStat(p.rush_yards))}
                    {TD(formatYardsPerAttempt(p.rush_yards, p.carries), true)}
                    {TD(p.rush_tds)}
                    {TD(formatStat(p.rush_epa), true)}
                  </tr>
                ))}
              </React.Fragment>
            )
          )}
        </StatSection>
      )}

      {/* Receiving */}
      {(receivers.away.length > 0 || receivers.home.length > 0) && (
        <StatSection title="Receiving" headers={[THL('Player'), TH('REC/TGT'), TH('YDS'), TH('Y/R'), TH('TD'), TH('YAC'), TH('EPA')]}>
          {([{ team: game.away_team, list: receivers.away }, { team: game.home_team, list: receivers.home }] as const).map(({ team, list }) =>
            list.length === 0 ? null : (
              <React.Fragment key={team}>
                <TeamDivider team={team} />
                {list.map(p => (
                  <tr key={p.player_id} className={rowCls}>
                    <PlayerLinkCell p={p} origin={origin} />
                    {TD(`${p.receptions}/${p.targets ?? '—'}`)}
                    {TD(formatStat(p.rec_yards))}
                    {TD(formatYardsPerAttempt(p.rec_yards, p.receptions), true)}
                    {TD(p.rec_tds)}
                    {TD(formatStat(p.yac), true)}
                    {TD(formatStat(p.rec_epa), true)}
                  </tr>
                ))}
              </React.Fragment>
            )
          )}
        </StatSection>
      )}

      {/* Defense */}
      {(defenders.away.length > 0 || defenders.home.length > 0) && (
        <StatSection title="Defense" headers={[THL('Player'), TH('TOT'), TH('SOLO'), TH('AST'), TH('SACK'), TH('TFL'), TH('INT'), TH('PBU')]}>
          {([{ team: game.away_team, list: defenders.away }, { team: game.home_team, list: defenders.home }] as const).map(({ team, list }) =>
            list.length === 0 ? null : (
              <React.Fragment key={team}>
                <TeamDivider team={team} />
                {list.map(p => (
                  <tr key={p.player_id} className={rowCls}>
                    <PlayerLinkCell p={p} origin={origin} />
                    {TD(formatStat(p.solo_tackles + p.assist_tackles))}
                    {TD(formatStat(p.solo_tackles))}
                    {TD(formatStat(p.assist_tackles), true)}
                    {TD(formatStat(p.sacks))}
                    {TD(formatStat(p.tackles_for_loss), true)}
                    {TD(p.def_interceptions)}
                    {TD(p.pass_breakups)}
                  </tr>
                ))}
              </React.Fragment>
            )
          )}
        </StatSection>
      )}

    </div>
  )
}
