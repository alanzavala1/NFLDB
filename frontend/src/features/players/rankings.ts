import type { LeagueLeader } from '../../types'
import { hasReceivingActivity } from '../../utils/receiving'

function computeRank(leaders: LeagueLeader[], playerId: string, value: (p: LeagueLeader) => number, filter: (p: LeagueLeader) => boolean): number | null {
  const filtered = leaders.filter(filter)
  // Player must qualify themselves
  if (!filtered.some(p => p.player_id === playerId)) return null
  const sorted = [...filtered].sort((a, b) => value(b) - value(a))
  const idx = sorted.findIndex(p => p.player_id === playerId)
  return idx >= 0 ? idx + 1 : null
}

function rankSuffix(rank: number | null, season: number): string | null {
  if (rank == null) return null
  const suffix = rank === 1 ? 'st' : rank === 2 ? 'nd' : rank === 3 ? 'rd' : 'th'
  return `${rank}${suffix} in NFL · ${season}`
}

function passerRatingNum(cmp: number, att: number, yds: number, td: number, int_: number): number | null {
  if (att === 0) return null
  const clamp = (x: number) => Math.min(2.375, Math.max(0, x))
  const a = clamp((cmp / att - 0.3) / 0.2)
  const b = clamp((yds / att - 3) / 4)
  const c = clamp((td / att) / 0.05)
  const d = clamp(2.375 - (int_ / att) / 0.04)
  return ((a + b + c + d) / 6) * 100
}

export function computeHighlightRanks(pos: string, playerId: string, leaders: LeagueLeader[], season: number): Record<string, string | null> {
  const r = (val: (p: LeagueLeader) => number, filter: (p: LeagueLeader) => boolean) =>
    rankSuffix(computeRank(leaders, playerId, val, filter), season)
  if (pos === 'QB') {
    const qbFilter = (p: LeagueLeader) => p.attempts >= 100
    return {
      'Passer Rating': r(p => passerRatingNum(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown) ?? 0, qbFilter),
      'AY/A':          r(p => p.attempts > 0 ? (p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts : 0, qbFilter),
      'EPA / Att':     r(p => p.attempts > 0 && p.pass_epa != null ? p.pass_epa / p.attempts : 0, qbFilter),
    }
  }
  if (pos === 'RB') {
    const rbFilter = (p: LeagueLeader) => p.carries >= 50
    return {
      'Rush Yards':  r(p => p.rush_yards, rbFilter),
      'Y / Carry':   r(p => p.carries > 0 ? p.rush_yards / p.carries : 0, rbFilter),
      'EPA / Carry': r(p => p.carries > 0 && p.rush_epa != null ? p.rush_epa / p.carries : 0, rbFilter),
      'SCR YDS / G': r(p => p.games_played > 0 ? (p.rush_yards + p.rec_yards) / p.games_played : 0, rbFilter),
    }
  }
  if (pos === 'WR') {
    const wrFilter = (p: LeagueLeader) => p.targets >= 20
    return {
      'Rec Yards':    r(p => p.rec_yards, p => hasReceivingActivity(p, 20)),
      'Catch %':      r(p => p.targets > 0 ? p.receptions / p.targets : 0, wrFilter),
      'EPA / Target': r(p => p.targets > 0 && p.rec_epa != null ? p.rec_epa / p.targets : 0, wrFilter),
      'Y / Target':   r(p => p.targets > 0 ? p.rec_yards / p.targets : 0, wrFilter),
    }
  }
  if (pos === 'DEF') {
    return {
      'Tackles': r(p => p.solo_tackles + p.assist_tackles, p => p.solo_tackles + p.assist_tackles >= 10),
      'Sacks':   r(p => p.sacks, p => p.sacks > 0),
      'INT':     r(p => p.def_interceptions, p => p.def_interceptions > 0),
      'PBU':     r(p => p.pass_breakups, p => p.pass_breakups > 0),
    }
  }
  if (pos === 'K') {
    return { 'Points': r(p => p.fg_made * 3 + p.xp_made, p => p.fg_att + p.xp_att > 0) }
  }
  if (pos === 'P') {
    return { 'Punts': r(p => p.punts ?? 0, p => (p.punts ?? 0) > 0) }
  }
  return {}
}
