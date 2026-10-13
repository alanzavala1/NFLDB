import type { TCol } from './types'
import { ratio, passerRating, sfmt } from './formatting'

export const PASS_COLS: TCol[] = [
  { key: 'catt', label: 'C/ATT',   kind: 'trad',                  sortVal: p => p.completions,    render: p => `${p.completions}/${p.attempts}`,
    total: t => `${t.completions}/${t.attempts}` },
  { key: 'cpct', label: 'CMP%',    kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.completions / p.attempts : 0, render: p => p.attempts > 0 ? (p.completions / p.attempts * 100).toFixed(1) : null,
    total: t => t.attempts > 0 ? (t.completions / t.attempts * 100).toFixed(1) : null },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.pass_yards,     render: p => p.pass_yards > 0 ? p.pass_yards.toLocaleString() : null,
    total: t => t.pass_yards > 0 ? t.pass_yards.toLocaleString() : null },
  { key: 'tmpct', label: '% TM',   kind: 'trad', dim: true,       sortVal: p => p.pass_yards,
    render: (p, t) => t.pass_yards > 0 ? `${(p.pass_yards / t.pass_yards * 100).toFixed(1)}%` : null,
    share: (p, t) => t.pass_yards > 0 ? p.pass_yards / t.pass_yards : 0,
    total: () => '100%' },
  { key: 'ya',   label: 'Y/A',     kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.pass_yards / p.attempts : 0, render: p => ratio(p.pass_yards, p.attempts),
    total: t => ratio(t.pass_yards, t.attempts) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.pass_tds,       render: p => p.pass_tds > 0 ? p.pass_tds : null,
    total: t => t.pass_tds > 0 ? t.pass_tds : null },
  { key: 'int',  label: 'INT',     kind: 'trad',                  sortVal: p => p.interceptions_thrown, render: p => p.interceptions_thrown > 0 ? p.interceptions_thrown : null,
    total: t => t.interceptions_thrown > 0 ? t.interceptions_thrown : null },
  { key: 'sck',  label: 'SCK',     kind: 'trad', dim: true,       sortVal: p => p.sacks_taken,    render: p => p.sacks_taken > 0 ? p.sacks_taken : null,
    total: t => t.sacks_taken > 0 ? t.sacks_taken : null },
  { key: 'sckpct', label: 'SCK%',  kind: 'trad', dim: true,       sortVal: p => (p.attempts + p.sacks_taken) > 0 ? p.sacks_taken / (p.attempts + p.sacks_taken) : 0,
    render: p => (p.attempts + p.sacks_taken) > 0 ? (p.sacks_taken / (p.attempts + p.sacks_taken) * 100).toFixed(1) : null,
    total: t => (t.attempts + t.sacks_taken) > 0 ? (t.sacks_taken / (t.attempts + t.sacks_taken) * 100).toFixed(1) : null },
  { key: 'rate', label: 'RATE',    kind: 'trad',                  sortVal: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown) ?? 0, render: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown)?.toFixed(1) ?? null,
    total: t => passerRating(t.completions, t.attempts, t.pass_yards, t.pass_tds, t.interceptions_thrown)?.toFixed(1) ?? null },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.pass_yards / p.games_played : 0, render: p => p.attempts > 0 ? ratio(p.pass_yards, p.games_played) : null,
    total: (t, g) => g > 0 && t.pass_yards > 0 ? (t.pass_yards / g).toFixed(1) : null },
  { key: 'car',  label: 'CAR',     kind: 'trad', dim: true,       sortVal: p => p.carries,        render: p => p.carries > 0 ? p.carries : null,
    total: t => t.carries > 0 ? t.carries : null },
  { key: 'ryds', label: 'RYDS',    kind: 'trad',                  sortVal: p => p.rush_yards,     render: p => p.carries > 0 ? p.rush_yards : null,
    total: t => t.carries > 0 ? t.rush_yards : null },
  { key: 'rtd',  label: 'RTD',     kind: 'trad', dim: true,       sortVal: p => p.rush_tds,       render: p => p.carries > 0 && p.rush_tds > 0 ? p.rush_tds : null,
    total: t => t.carries > 0 && t.rush_tds > 0 ? t.rush_tds : null },
  { key: 'aya',  label: 'AY/A',    kind: 'adv',                   sortVal: p => p.attempts > 0 ? (p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts : 0, render: p => p.attempts > 0 ? ((p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts).toFixed(1) : null,
    total: t => t.attempts > 0 ? ((t.pass_yards + 20 * t.pass_tds - 45 * t.interceptions_thrown) / t.attempts).toFixed(1) : null },
  { key: 'epaa', label: 'EPA/Att', kind: 'adv',                   sortVal: p => p.attempts > 0 && p.pass_epa != null ? p.pass_epa / p.attempts : 0, render: p => p.attempts > 0 && p.pass_epa != null ? sfmt(p.pass_epa / p.attempts) : null,
    total: t => t.attempts > 0 ? sfmt(t.pass_epa / t.attempts) : null },
]

export const RUSH_COLS: TCol[] = [
  { key: 'car',  label: 'CAR',     kind: 'trad',                  sortVal: p => p.carries,        render: p => p.carries,
    total: t => t.carries },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rush_yards,     render: p => p.rush_yards > 0 ? p.rush_yards.toLocaleString() : null,
    total: t => t.rush_yards > 0 ? t.rush_yards.toLocaleString() : null },
  { key: 'tmpct', label: '% TM',   kind: 'trad', dim: true,       sortVal: p => p.rush_yards,
    render: (p, t) => t.rush_yards > 0 ? `${(p.rush_yards / t.rush_yards * 100).toFixed(1)}%` : null,
    share: (p, t) => t.rush_yards > 0 ? p.rush_yards / t.rush_yards : 0,
    total: () => '100%' },
  { key: 'ypc',  label: 'Y/C',     kind: 'trad', dim: true,       sortVal: p => p.carries ? p.rush_yards / p.carries : 0, render: p => ratio(p.rush_yards, p.carries),
    total: t => ratio(t.rush_yards, t.carries) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rush_tds,       render: p => p.rush_tds > 0 ? p.rush_tds : null,
    total: t => t.rush_tds > 0 ? t.rush_tds : null },
  { key: 'tdpct', label: 'TD%',    kind: 'trad', dim: true,       sortVal: p => p.carries > 0 ? p.rush_tds / p.carries : 0,
    render: p => p.carries > 0 && p.rush_tds > 0 ? (p.rush_tds / p.carries * 100).toFixed(1) : null,
    total: t => t.carries > 0 && t.rush_tds > 0 ? (t.rush_tds / t.carries * 100).toFixed(1) : null },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rush_yards / p.games_played : 0, render: p => ratio(p.rush_yards, p.games_played),
    total: (t, g) => g > 0 && t.rush_yards > 0 ? (t.rush_yards / g).toFixed(1) : null },
  { key: 'epac', label: 'EPA/Car', kind: 'adv',                   sortVal: p => p.carries > 0 && p.rush_epa != null ? p.rush_epa / p.carries : 0, render: p => p.carries > 0 && p.rush_epa != null ? sfmt(p.rush_epa / p.carries) : null,
    total: t => t.carries > 0 ? sfmt(t.rush_epa / t.carries) : null },
]

export const REC_COLS: TCol[] = [
  { key: 'tgt',  label: 'TGT',     kind: 'trad', dim: true,       sortVal: p => p.targets,        render: p => p.targets > 0 ? p.targets : null,
    total: t => t.targets > 0 ? t.targets : null },
  { key: 'rec',  label: 'REC',     kind: 'trad',                  sortVal: p => p.receptions,     render: p => p.receptions > 0 ? p.receptions : null,
    total: t => t.receptions > 0 ? t.receptions : null },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rec_yards,      render: p => p.rec_yards > 0 ? p.rec_yards.toLocaleString() : null,
    total: t => t.rec_yards > 0 ? t.rec_yards.toLocaleString() : null },
  { key: 'tmpct', label: '% TM',   kind: 'trad', dim: true,       sortVal: p => p.rec_yards,
    render: (p, t) => t.rec_yards > 0 ? `${(p.rec_yards / t.rec_yards * 100).toFixed(1)}%` : null,
    share: (p, t) => t.rec_yards > 0 ? p.rec_yards / t.rec_yards : 0,
    total: () => '100%' },
  { key: 'ypr',  label: 'Y/R',     kind: 'trad', dim: true,       sortVal: p => p.receptions ? p.rec_yards / p.receptions : 0, render: p => ratio(p.rec_yards, p.receptions),
    total: t => ratio(t.rec_yards, t.receptions) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rec_tds,        render: p => p.rec_tds > 0 ? p.rec_tds : null,
    total: t => t.rec_tds > 0 ? t.rec_tds : null },
  { key: 'cpct', label: 'CTH%',    kind: 'trad', dim: true,       sortVal: p => p.targets ? p.receptions / p.targets : 0, render: p => p.targets > 0 ? (p.receptions / p.targets * 100).toFixed(1) : null,
    total: t => t.targets > 0 ? (t.receptions / t.targets * 100).toFixed(1) : null },
  { key: 'tdpct', label: 'TD%',    kind: 'trad', dim: true,       sortVal: p => p.targets > 0 ? p.rec_tds / p.targets : 0,
    render: p => p.targets > 0 && p.rec_tds > 0 ? (p.rec_tds / p.targets * 100).toFixed(1) : null,
    total: t => t.targets > 0 && t.rec_tds > 0 ? (t.rec_tds / t.targets * 100).toFixed(1) : null },
  { key: 'yac',  label: 'YAC',     kind: 'trad', dim: true,       sortVal: p => p.yac,
    render: p => p.yac > 0 ? p.yac.toLocaleString() : null,
    total: t => t.yac > 0 ? t.yac.toLocaleString() : null },
  { key: 'yacr', label: 'YAC/R',   kind: 'trad', dim: true,       sortVal: p => p.receptions > 0 ? p.yac / p.receptions : 0,
    render: p => p.receptions > 0 && p.yac > 0 ? (p.yac / p.receptions).toFixed(1) : null,
    total: t => t.receptions > 0 && t.yac > 0 ? (t.yac / t.receptions).toFixed(1) : null },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rec_yards / p.games_played : 0, render: p => ratio(p.rec_yards, p.games_played),
    total: (t, g) => g > 0 && t.rec_yards > 0 ? (t.rec_yards / g).toFixed(1) : null },
  { key: 'ytgt', label: 'Y/TGT',   kind: 'adv',                   sortVal: p => p.targets ? p.rec_yards / p.targets : 0, render: p => ratio(p.rec_yards, p.targets),
    total: t => ratio(t.rec_yards, t.targets) },
  { key: 'aytg', label: 'AY/TGT',  kind: 'adv',                   sortVal: p => p.targets > 0 && p.air_yards != null ? p.air_yards / p.targets : 0, render: p => p.targets > 0 && p.air_yards != null ? ratio(p.air_yards, p.targets) : null,
    total: t => t.targets > 0 ? ratio(t.air_yards, t.targets) : null },
  { key: 'epat', label: 'EPA/Tgt', kind: 'adv',                   sortVal: p => p.targets > 0 && p.rec_epa != null ? p.rec_epa / p.targets : 0, render: p => p.targets > 0 && p.rec_epa != null ? sfmt(p.rec_epa / p.targets) : null,
    total: t => t.targets > 0 ? sfmt(t.rec_epa / t.targets) : null },
]

export const SCRIM_COLS: TCol[] = [
  { key: 'tch',   label: 'TCH',   kind: 'trad',                  sortVal: p => p.carries + p.receptions, render: p => (p.carries + p.receptions) > 0 ? (p.carries + p.receptions) : null,
    total: t => (t.carries + t.receptions) > 0 ? (t.carries + t.receptions) : null },
  { key: 'scrim', label: 'SCRIM', kind: 'trad', highlight: true, sortVal: p => p.rush_yards + p.rec_yards, render: p => {
      const v = p.rush_yards + p.rec_yards; return v > 0 ? v.toLocaleString() : null
    },
    total: t => {
      const v = t.rush_yards + t.rec_yards; return v > 0 ? v.toLocaleString() : null
    } },
  { key: 'tmpct', label: '% TM',  kind: 'trad', dim: true,       sortVal: p => p.rush_yards + p.rec_yards,
    render: (p, t) => {
      const team = t.rush_yards + t.rec_yards
      const player = p.rush_yards + p.rec_yards
      return team > 0 ? `${(player / team * 100).toFixed(1)}%` : null
    },
    share: (p, t) => {
      const team = t.rush_yards + t.rec_yards
      return team > 0 ? (p.rush_yards + p.rec_yards) / team : 0
    },
    total: () => '100%' },
  { key: 'ypt',   label: 'Y/T',   kind: 'trad', dim: true,       sortVal: p => (p.carries + p.receptions) > 0 ? (p.rush_yards + p.rec_yards) / (p.carries + p.receptions) : 0,
    render: p => {
      const tch = p.carries + p.receptions
      return tch > 0 ? ((p.rush_yards + p.rec_yards) / tch).toFixed(1) : null
    },
    total: t => {
      const tch = t.carries + t.receptions
      return tch > 0 ? ((t.rush_yards + t.rec_yards) / tch).toFixed(1) : null
    } },
  { key: 'td',    label: 'TD',    kind: 'trad',                  sortVal: p => p.rush_tds + p.rec_tds, render: p => {
      const td = p.rush_tds + p.rec_tds; return td > 0 ? td : null
    },
    total: t => {
      const td = t.rush_tds + t.rec_tds; return td > 0 ? td : null
    } },
  { key: 'ypg',   label: 'Y/G',   kind: 'trad', dim: true,       sortVal: p => p.games_played > 0 ? (p.rush_yards + p.rec_yards) / p.games_played : 0,
    render: p => {
      const v = p.rush_yards + p.rec_yards
      return p.games_played > 0 && v > 0 ? (v / p.games_played).toFixed(1) : null
    },
    total: (t, g) => {
      const v = t.rush_yards + t.rec_yards
      return g > 0 && v > 0 ? (v / g).toFixed(1) : null
    } },
  { key: 'rush',  label: 'RUSH',  kind: 'trad', dim: true,       sortVal: p => p.rush_yards, render: p => p.rush_yards > 0 ? p.rush_yards.toLocaleString() : null,
    total: t => t.rush_yards > 0 ? t.rush_yards.toLocaleString() : null },
  { key: 'rec',   label: 'REC',   kind: 'trad', dim: true,       sortVal: p => p.rec_yards,  render: p => p.rec_yards > 0 ? p.rec_yards.toLocaleString() : null,
    total: t => t.rec_yards > 0 ? t.rec_yards.toLocaleString() : null },
  { key: 'mix',   label: 'RUN/REC', kind: 'adv',                 sortVal: p => {
      const v = p.rush_yards + p.rec_yards; return v > 0 ? p.rush_yards / v : 0
    },
    render: p => {
      const v = p.rush_yards + p.rec_yards
      if (v === 0) return null
      const rushPct = Math.round(p.rush_yards / v * 100)
      return `${rushPct}/${100 - rushPct}`
    },
    total: t => {
      const v = t.rush_yards + t.rec_yards
      if (v === 0) return null
      const rushPct = Math.round(t.rush_yards / v * 100)
      return `${rushPct}/${100 - rushPct}`
    } },
  { key: 'epa',   label: 'EPA',   kind: 'adv',                   sortVal: p => (p.rush_epa ?? 0) + (p.rec_epa ?? 0),
    render: p => {
      const tch = p.carries + p.receptions
      if (tch === 0) return null
      return sfmt((p.rush_epa ?? 0) + (p.rec_epa ?? 0), 1)
    },
    total: t => {
      const tch = t.carries + t.receptions
      return tch > 0 ? sfmt(t.rush_epa + t.rec_epa, 1) : null
    } },
]

export const DEF_COLS: TCol[] = [
  { key: 'tot',  label: 'TOT',  kind: 'trad', highlight: true, sortVal: p => p.solo_tackles + p.assist_tackles, render: p => p.solo_tackles + p.assist_tackles,
    total: t => t.solo_tackles + t.assist_tackles },
  { key: 'tmpct', label: '% TM', kind: 'trad', dim: true,       sortVal: p => p.solo_tackles + p.assist_tackles,
    render: (p, t) => {
      const team = t.solo_tackles + t.assist_tackles
      const player = p.solo_tackles + p.assist_tackles
      return team > 0 ? `${(player / team * 100).toFixed(1)}%` : null
    },
    share: (p, t) => {
      const team = t.solo_tackles + t.assist_tackles
      return team > 0 ? (p.solo_tackles + p.assist_tackles) / team : 0
    },
    total: () => '100%' },
  { key: 'tklpg', label: 'TKL/G', kind: 'trad', dim: true,       sortVal: p => p.games_played > 0 ? (p.solo_tackles + p.assist_tackles) / p.games_played : 0,
    render: p => p.games_played > 0 ? ((p.solo_tackles + p.assist_tackles) / p.games_played).toFixed(1) : null,
    total: (t, g) => g > 0 ? ((t.solo_tackles + t.assist_tackles) / g).toFixed(1) : null },
  { key: 'solo', label: 'SOLO', kind: 'trad',                  sortVal: p => p.solo_tackles,        render: p => p.solo_tackles,
    total: t => t.solo_tackles },
  { key: 'ast',  label: 'AST',  kind: 'trad', dim: true,       sortVal: p => p.assist_tackles,      render: p => p.assist_tackles,
    total: t => t.assist_tackles },
  { key: 'tfl',  label: 'TFL',  kind: 'trad',                  sortVal: p => p.tackles_for_loss,    render: p => p.tackles_for_loss > 0 ? p.tackles_for_loss : null,
    total: t => t.tackles_for_loss > 0 ? t.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', kind: 'trad',                  sortVal: p => p.sacks,               render: p => p.sacks > 0 ? p.sacks : null,
    total: t => t.sacks > 0 ? t.sacks : null },
  { key: 'qbh',  label: 'QBH',  kind: 'trad', dim: true,       sortVal: p => p.qb_hits,             render: p => p.qb_hits > 0 ? p.qb_hits : null,
    total: t => t.qb_hits > 0 ? t.qb_hits : null },
  { key: 'int',  label: 'INT',  kind: 'trad',                  sortVal: p => p.def_interceptions,   render: p => p.def_interceptions > 0 ? p.def_interceptions : null,
    total: t => t.def_interceptions > 0 ? t.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  kind: 'trad', dim: true,       sortVal: p => p.pass_breakups,       render: p => p.pass_breakups > 0 ? p.pass_breakups : null,
    total: t => t.pass_breakups > 0 ? t.pass_breakups : null },
  { key: 'ff',   label: 'FF',   kind: 'trad',                  sortVal: p => p.forced_fumbles,      render: p => p.forced_fumbles > 0 ? p.forced_fumbles : null,
    total: t => t.forced_fumbles > 0 ? t.forced_fumbles : null },
  { key: 'fr',   label: 'FR',   kind: 'trad', dim: true,       sortVal: p => p.fumble_recoveries,   render: p => p.fumble_recoveries > 0 ? p.fumble_recoveries : null,
    total: t => t.fumble_recoveries > 0 ? t.fumble_recoveries : null },
]
