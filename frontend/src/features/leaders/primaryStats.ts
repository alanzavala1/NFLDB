import type { LeagueLeader } from '../../types'
import { pct, ratio } from './formatting'

export interface PrimaryStat {
  label: string
  value: (p: LeagueLeader) => number
  display: (p: LeagueLeader) => string
  secondary: (p: LeagueLeader) => string
}

export const STAT_PRIMARY: Record<string, PrimaryStat> = {
  passing: {
    label: 'YDS',
    value: p => p.pass_yards,
    display: p => p.pass_yards.toLocaleString(),
    secondary: p => `${p.pass_tds} TD · ${p.interceptions_thrown} INT · ${pct(p.completions, p.attempts) ?? '—'}%`,
  },
  rushing: {
    label: 'YDS',
    value: p => p.rush_yards,
    display: p => p.rush_yards.toLocaleString(),
    secondary: p => `${p.carries} CAR · ${p.rush_tds} TD · ${ratio(p.rush_yards, p.carries) ?? '—'} Y/C`,
  },
  receiving: {
    label: 'YDS',
    value: p => p.rec_yards,
    display: p => p.rec_yards.toLocaleString(),
    secondary: p => `${p.receptions} REC · ${p.rec_tds} TD · ${ratio(p.rec_yards, p.receptions) ?? '—'} Y/R`,
  },
  defense: {
    label: 'TKL',
    value: p => p.solo_tackles + p.assist_tackles,
    display: p => (p.solo_tackles + p.assist_tackles).toString(),
    secondary: p => `${p.solo_tackles} SOLO · ${p.sacks > 0 ? `${p.sacks} SCK · ` : ''}${p.def_interceptions} INT`,
  },
}

export const POS_PRIMARY: Record<string, PrimaryStat> = {
  qb:  STAT_PRIMARY.passing,
  rb:  STAT_PRIMARY.rushing,
  wr:  STAT_PRIMARY.receiving,
  te:  STAT_PRIMARY.receiving,
  def: STAT_PRIMARY.defense,
  k: {
    label: 'PTS',
    value: p => p.fg_made * 3 + p.xp_made,
    display: p => (p.fg_made * 3 + p.xp_made).toString(),
    secondary: p => `${p.fg_made}/${p.fg_att} FG · ${p.xp_made}/${p.xp_att} XP`,
  },
  p: {
    label: 'PUNTS',
    value: p => p.punts ?? 0,
    display: p => String(p.punts ?? 0),
    secondary: p => `${(p.punt_yards ?? 0).toLocaleString()} YDS · ${(p.punts ?? 0) > 0 ? ((p.punt_yards ?? 0) / (p.punts ?? 1)).toFixed(1) : '—'} AVG`,
  },
}
