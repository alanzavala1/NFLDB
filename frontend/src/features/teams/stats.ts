import type { TeamLeader } from '../../types'
import type { SectionTotals, SectionKind, SummaryBox } from './types'
import { sfmt, passerRating } from './formatting'

export function aggregateTotals(players: TeamLeader[]): SectionTotals {
  const t: SectionTotals = {
    attempts: 0, completions: 0, pass_yards: 0, pass_tds: 0,
    interceptions_thrown: 0, sacks_taken: 0, pass_epa: 0,
    carries: 0, rush_yards: 0, rush_tds: 0, rush_epa: 0,
    targets: 0, receptions: 0, rec_yards: 0, rec_tds: 0,
    air_yards: 0, yac: 0, rec_epa: 0,
    solo_tackles: 0, assist_tackles: 0, sacks: 0, tackles_for_loss: 0,
    qb_hits: 0, def_interceptions: 0, pass_breakups: 0,
    forced_fumbles: 0, fumble_recoveries: 0,
  }
  for (const p of players) {
    t.attempts += p.attempts; t.completions += p.completions
    t.pass_yards += p.pass_yards; t.pass_tds += p.pass_tds
    t.interceptions_thrown += p.interceptions_thrown
    t.sacks_taken += p.sacks_taken
    if (p.pass_epa != null) t.pass_epa += p.pass_epa
    t.carries += p.carries; t.rush_yards += p.rush_yards; t.rush_tds += p.rush_tds
    if (p.rush_epa != null) t.rush_epa += p.rush_epa
    t.targets = t.targets == null || p.targets == null ? null : t.targets + p.targets; t.receptions += p.receptions
    t.rec_yards += p.rec_yards; t.rec_tds += p.rec_tds
    t.air_yards = t.air_yards == null || p.air_yards == null ? null : t.air_yards + p.air_yards
    t.yac = t.yac == null || p.yac == null ? null : t.yac + p.yac
    if (p.rec_epa != null) t.rec_epa += p.rec_epa
    t.solo_tackles += p.solo_tackles; t.assist_tackles += p.assist_tackles
    t.sacks += p.sacks; t.tackles_for_loss += p.tackles_for_loss
    t.qb_hits += p.qb_hits; t.def_interceptions += p.def_interceptions
    t.pass_breakups += p.pass_breakups
    t.forced_fumbles += p.forced_fumbles; t.fumble_recoveries += p.fumble_recoveries
  }
  return t
}

export function buildSummary(section: SectionKind, t: SectionTotals, games: number): SummaryBox[] {
  const pct = (a: number, b: number | null) => b != null && b > 0 ? `${(a / b * 100).toFixed(1)}%` : '—'
  const rat = (a: number | null, b: number | null, d = 1) => a != null && b != null && b > 0 ? (a / b).toFixed(d) : '—'
  const epa = (a: number, b: number | null) => b != null && b > 0 ? sfmt(a / b) : '—'
  const perg = (a: number) => games > 0 ? (a / games).toFixed(1) : '—'
  switch (section) {
    case 'passing': {
      const rate = passerRating(t.completions, t.attempts, t.pass_yards, t.pass_tds, t.interceptions_thrown)
      return [
        { label: 'CMP/ATT', value: `${t.completions}/${t.attempts}` },
        { label: 'CMP%',    value: pct(t.completions, t.attempts) },
        { label: 'YDS',     value: t.pass_yards.toLocaleString() },
        { label: 'Y/A',     value: rat(t.pass_yards, t.attempts) },
        { label: 'TD-INT',  value: `${t.pass_tds}-${t.interceptions_thrown}` },
        { label: 'SCK',     value: String(t.sacks_taken) },
        { label: 'RATE',    value: rate != null ? rate.toFixed(1) : '—' },
        { label: 'EPA/Att', value: epa(t.pass_epa, t.attempts) },
      ]
    }
    case 'rushing':
      return [
        { label: 'CAR',     value: String(t.carries) },
        { label: 'YDS',     value: t.rush_yards.toLocaleString() },
        { label: 'Y/C',     value: rat(t.rush_yards, t.carries) },
        { label: 'TD',      value: String(t.rush_tds) },
        { label: 'Y/G',     value: perg(t.rush_yards) },
        { label: 'EPA/Car', value: epa(t.rush_epa, t.carries) },
      ]
    case 'receiving':
      return [
        { label: 'REC/TGT', value: `${t.receptions}/${t.targets ?? '—'}` },
        { label: 'CTH%',    value: pct(t.receptions, t.targets) },
        { label: 'YDS',     value: t.rec_yards.toLocaleString() },
        { label: 'Y/R',     value: rat(t.rec_yards, t.receptions) },
        { label: 'TD',      value: String(t.rec_tds) },
        { label: 'YAC',     value: t.yac?.toLocaleString() ?? '—' },
        { label: 'aDOT',    value: rat(t.air_yards, t.targets) },
        { label: 'EPA/Tgt', value: epa(t.rec_epa, t.targets) },
      ]
    case 'scrimmage': {
      const tch = t.carries + t.receptions
      const scrim = t.rush_yards + t.rec_yards
      const rushPct = scrim > 0 ? Math.round(t.rush_yards / scrim * 100) : 0
      return [
        { label: 'TCH',     value: String(tch) },
        { label: 'SCRIM',   value: scrim.toLocaleString() },
        { label: 'Y/T',     value: rat(scrim, tch) },
        { label: 'TD',      value: String(t.rush_tds + t.rec_tds) },
        { label: 'Y/G',     value: perg(scrim) },
        { label: 'RUN/REC', value: scrim > 0 ? `${rushPct}/${100 - rushPct}` : '—' },
      ]
    }
    case 'defense': {
      const tkl = t.solo_tackles + t.assist_tackles
      return [
        { label: 'TKL',   value: String(tkl) },
        { label: 'TKL/G', value: perg(tkl) },
        { label: 'SACK',  value: String(t.sacks) },
        { label: 'TFL',   value: String(t.tackles_for_loss) },
        { label: 'QBH',   value: String(t.qb_hits) },
        { label: 'INT',   value: String(t.def_interceptions) },
        { label: 'PBU',   value: String(t.pass_breakups) },
        { label: 'TO',    value: String(t.forced_fumbles + t.fumble_recoveries + t.def_interceptions) },
      ]
    }
  }
}
