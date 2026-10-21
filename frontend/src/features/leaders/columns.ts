import type { LeagueLeader } from '../../types'
import { hasReceivingActivity } from '../../utils/receiving'
import { passerRating, pct, ratio, sfmt } from './formatting'

type ColKind = 'trad' | 'adv'

export type LeaderCol = {
  key: string; label: string; kind: ColKind
  sortVal: (p: LeagueLeader) => number
  render: (p: LeagueLeader) => string | number | null
  highlight?: boolean; dim?: boolean
}

const PASSING_COLS: LeaderCol[] = [
  { key: 'g',    label: 'G',       kind: 'trad', dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'catt', label: 'C/ATT',   kind: 'trad',                  sortVal: p => p.completions,    render: p => `${p.completions}/${p.attempts}` },
  { key: 'cpct', label: 'CMP%',    kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.completions / p.attempts : 0, render: p => pct(p.completions, p.attempts) },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.pass_yards,     render: p => p.pass_yards.toLocaleString() },
  { key: 'ya',   label: 'Y/A',     kind: 'trad', dim: true,       sortVal: p => p.attempts ? p.pass_yards / p.attempts : 0, render: p => ratio(p.pass_yards, p.attempts) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.pass_tds,       render: p => p.pass_tds },
  { key: 'int',  label: 'INT',     kind: 'trad',                  sortVal: p => p.interceptions_thrown, render: p => p.interceptions_thrown },
  { key: 'sck',  label: 'SCK',     kind: 'trad', dim: true,       sortVal: p => p.sacks_taken,    render: p => p.sacks_taken },
  { key: 'rate', label: 'RATE',    kind: 'trad',                  sortVal: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown) ?? 0, render: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown)?.toFixed(1) ?? null },
  { key: 'car',  label: 'CAR',     kind: 'trad', dim: true,       sortVal: p => p.carries,        render: p => p.carries > 0 ? p.carries : null },
  { key: 'ryds', label: 'RYDS',    kind: 'trad',                  sortVal: p => p.rush_yards,     render: p => p.carries > 0 ? p.rush_yards : null },
  { key: 'aya',  label: 'AY/A',    kind: 'adv',                   sortVal: p => p.attempts > 0 ? (p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts : 0, render: p => p.attempts > 0 ? ((p.pass_yards + 20 * p.pass_tds - 45 * p.interceptions_thrown) / p.attempts).toFixed(1) : null },
  { key: 'epaa', label: 'EPA/Att', kind: 'adv',                   sortVal: p => p.attempts > 0 && p.pass_epa != null ? p.pass_epa / p.attempts : 0, render: p => p.attempts > 0 && p.pass_epa != null ? sfmt(p.pass_epa / p.attempts) : null },
]

const RUSHING_COLS: LeaderCol[] = [
  { key: 'g',    label: 'G',       kind: 'trad', dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'car',  label: 'CAR',     kind: 'trad',                  sortVal: p => p.carries,        render: p => p.carries },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rush_yards,     render: p => p.rush_yards.toLocaleString() },
  { key: 'ypc',  label: 'Y/C',     kind: 'trad', dim: true,       sortVal: p => p.carries ? p.rush_yards / p.carries : 0, render: p => ratio(p.rush_yards, p.carries) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rush_tds,       render: p => p.rush_tds },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rush_yards / p.games_played : 0, render: p => ratio(p.rush_yards, p.games_played) },
  { key: 'epac', label: 'EPA/Car', kind: 'adv',                   sortVal: p => p.carries > 0 && p.rush_epa != null ? p.rush_epa / p.carries : 0, render: p => p.carries > 0 && p.rush_epa != null ? sfmt(p.rush_epa / p.carries) : null },
]

const RECEIVING_COLS: LeaderCol[] = [
  { key: 'g',    label: 'G',       kind: 'trad', dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'tgt',  label: 'TGT',     kind: 'trad', dim: true,       sortVal: p => p.targets,        render: p => p.targets },
  { key: 'rec',  label: 'REC',     kind: 'trad',                  sortVal: p => p.receptions,     render: p => p.receptions },
  { key: 'yds',  label: 'YDS',     kind: 'trad', highlight: true, sortVal: p => p.rec_yards,      render: p => p.rec_yards.toLocaleString() },
  { key: 'ypr',  label: 'Y/R',     kind: 'trad', dim: true,       sortVal: p => p.receptions ? p.rec_yards / p.receptions : 0, render: p => ratio(p.rec_yards, p.receptions) },
  { key: 'td',   label: 'TD',      kind: 'trad',                  sortVal: p => p.rec_tds,        render: p => p.rec_tds },
  { key: 'cpct', label: 'CTH%',    kind: 'trad', dim: true,       sortVal: p => p.targets ? p.receptions / p.targets : 0, render: p => pct(p.receptions, p.targets) },
  { key: 'ypg',  label: 'Y/G',     kind: 'trad', dim: true,       sortVal: p => p.games_played ? p.rec_yards / p.games_played : 0, render: p => ratio(p.rec_yards, p.games_played) },
  { key: 'ytgt', label: 'Y/TGT',   kind: 'adv',                   sortVal: p => p.targets ? p.rec_yards / p.targets : 0, render: p => ratio(p.rec_yards, p.targets) },
  { key: 'epat', label: 'EPA/Tgt', kind: 'adv',                   sortVal: p => p.targets > 0 && p.rec_epa != null ? p.rec_epa / p.targets : 0, render: p => p.targets > 0 && p.rec_epa != null ? sfmt(p.rec_epa / p.targets) : null },
]

const DEFENSE_COLS: LeaderCol[] = [
  { key: 'g',    label: 'G',    kind: 'trad', dim: true,       sortVal: p => p.games_played,             render: p => p.games_played },
  { key: 'tot',  label: 'TOT',  kind: 'trad', highlight: true, sortVal: p => p.solo_tackles + p.assist_tackles, render: p => p.solo_tackles + p.assist_tackles },
  { key: 'solo', label: 'SOLO', kind: 'trad',                  sortVal: p => p.solo_tackles,             render: p => p.solo_tackles },
  { key: 'ast',  label: 'AST',  kind: 'trad', dim: true,       sortVal: p => p.assist_tackles,           render: p => p.assist_tackles },
  { key: 'tfl',  label: 'TFL',  kind: 'trad',                  sortVal: p => p.tackles_for_loss,         render: p => p.tackles_for_loss > 0 ? p.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', kind: 'trad',                  sortVal: p => p.sacks,                    render: p => p.sacks > 0 ? p.sacks : null },
  { key: 'qbh',  label: 'QBH',  kind: 'trad', dim: true,       sortVal: p => p.qb_hits,                  render: p => p.qb_hits > 0 ? p.qb_hits : null },
  { key: 'int',  label: 'INT',  kind: 'trad',                  sortVal: p => p.def_interceptions,        render: p => p.def_interceptions > 0 ? p.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  kind: 'trad', dim: true,       sortVal: p => p.pass_breakups,            render: p => p.pass_breakups > 0 ? p.pass_breakups : null },
  { key: 'ff',   label: 'FF',   kind: 'trad',                  sortVal: p => p.forced_fumbles ?? 0,      render: p => (p.forced_fumbles ?? 0) > 0 ? p.forced_fumbles : null },
]

export type PosCol = {
  key: string; label: string; desc: string
  sortVal: (p: LeagueLeader) => number
  render: (p: LeagueLeader) => string | number | null
  highlight?: boolean; dim?: boolean
}

const QB_POS_COLS: PosCol[] = [
  { key: 'g',    label: 'G',     desc: 'Games played',          dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'catt', label: 'C/ATT', desc: 'Completions/Attempts',                   sortVal: p => p.completions,    render: p => `${p.completions}/${p.attempts}` },
  { key: 'cpct', label: 'CMP%',  desc: 'Completion %',          dim: true,       sortVal: p => p.attempts ? p.completions / p.attempts : 0, render: p => pct(p.completions, p.attempts) },
  { key: 'yds',  label: 'YDS',   desc: 'Passing yards',         highlight: true, sortVal: p => p.pass_yards,     render: p => p.pass_yards.toLocaleString() },
  { key: 'ya',   label: 'Y/A',   desc: 'Yards per attempt',     dim: true,       sortVal: p => p.attempts ? p.pass_yards / p.attempts : 0, render: p => ratio(p.pass_yards, p.attempts) },
  { key: 'td',   label: 'TD',    desc: 'Passing touchdowns',                     sortVal: p => p.pass_tds,       render: p => p.pass_tds },
  { key: 'int',  label: 'INT',   desc: 'Interceptions',                          sortVal: p => p.interceptions_thrown, render: p => p.interceptions_thrown },
  { key: 'rate', label: 'RATE',  desc: 'Passer rating',                          sortVal: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown) ?? 0, render: p => passerRating(p.completions, p.attempts, p.pass_yards, p.pass_tds, p.interceptions_thrown)?.toFixed(1) ?? null },
  { key: 'epaa', label: 'EPA/A', desc: 'EPA per attempt',       dim: true,       sortVal: p => p.attempts > 0 && p.pass_epa != null ? p.pass_epa / p.attempts : 0, render: p => p.attempts > 0 && p.pass_epa != null ? sfmt(p.pass_epa / p.attempts) : null },
]

const RB_POS_COLS: PosCol[] = [
  { key: 'g',    label: 'G',       desc: 'Games played',           dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'car',  label: 'CAR',     desc: 'Carries',                                 sortVal: p => p.carries,        render: p => p.carries },
  { key: 'yds',  label: 'YDS',     desc: 'Rushing yards',          highlight: true, sortVal: p => p.rush_yards,     render: p => p.rush_yards.toLocaleString() },
  { key: 'ypc',  label: 'Y/C',     desc: 'Yards per carry',        dim: true,       sortVal: p => p.carries ? p.rush_yards / p.carries : 0, render: p => ratio(p.rush_yards, p.carries) },
  { key: 'td',   label: 'TD',      desc: 'Rushing touchdowns',                      sortVal: p => p.rush_tds,       render: p => p.rush_tds },
  { key: 'ypg',  label: 'Y/G',     desc: 'Rush yards per game',    dim: true,       sortVal: p => p.games_played ? p.rush_yards / p.games_played : 0, render: p => ratio(p.rush_yards, p.games_played) },
  { key: 'rec',  label: 'REC',     desc: 'Receptions',             dim: true,       sortVal: p => p.receptions,     render: p => p.receptions > 0 ? p.receptions : null },
  { key: 'ryds', label: 'REC YDS', desc: 'Receiving yards',                         sortVal: p => p.rec_yards,      render: p => p.rec_yards > 0 ? p.rec_yards.toLocaleString() : null },
  { key: 'epac', label: 'EPA/C',   desc: 'EPA per carry',          dim: true,       sortVal: p => p.carries > 0 && p.rush_epa != null ? p.rush_epa / p.carries : 0, render: p => p.carries > 0 && p.rush_epa != null ? sfmt(p.rush_epa / p.carries) : null },
]

const REC_POS_COLS: PosCol[] = [
  { key: 'g',    label: 'G',     desc: 'Games played',            dim: true,       sortVal: p => p.games_played,   render: p => p.games_played },
  { key: 'tgt',  label: 'TGT',   desc: 'Targets',                 dim: true,       sortVal: p => p.targets,        render: p => p.targets },
  { key: 'rec',  label: 'REC',   desc: 'Receptions',                               sortVal: p => p.receptions,     render: p => p.receptions },
  { key: 'yds',  label: 'YDS',   desc: 'Receiving yards',         highlight: true, sortVal: p => p.rec_yards,      render: p => p.rec_yards.toLocaleString() },
  { key: 'ypr',  label: 'Y/R',   desc: 'Yards per reception',     dim: true,       sortVal: p => p.receptions ? p.rec_yards / p.receptions : 0, render: p => ratio(p.rec_yards, p.receptions) },
  { key: 'td',   label: 'TD',    desc: 'Receiving touchdowns',                     sortVal: p => p.rec_tds,        render: p => p.rec_tds },
  { key: 'cth',  label: 'CTH%',  desc: 'Catch rate',              dim: true,       sortVal: p => p.targets ? p.receptions / p.targets : 0, render: p => pct(p.receptions, p.targets) },
  { key: 'ypg',  label: 'Y/G',   desc: 'Yards per game',          dim: true,       sortVal: p => p.games_played ? p.rec_yards / p.games_played : 0, render: p => ratio(p.rec_yards, p.games_played) },
  { key: 'epat', label: 'EPA/T', desc: 'EPA per target',          dim: true,       sortVal: p => p.targets > 0 && p.rec_epa != null ? p.rec_epa / p.targets : 0, render: p => p.targets > 0 && p.rec_epa != null ? sfmt(p.rec_epa / p.targets) : null },
]

const K_POS_COLS: PosCol[] = [
  { key: 'g',   label: 'G',    desc: 'Games played',          dim: true,       sortVal: p => p.games_played,  render: p => p.games_played },
  { key: 'fg',  label: 'FG',   desc: 'Field goals made/att',  highlight: true, sortVal: p => p.fg_made,       render: p => p.fg_att > 0 ? `${p.fg_made}/${p.fg_att}` : null },
  { key: 'fgp', label: 'FG%',  desc: 'FG make rate',                           sortVal: p => p.fg_att ? p.fg_made / p.fg_att : 0, render: p => pct(p.fg_made, p.fg_att) },
  { key: 'xp',  label: 'XP',   desc: 'Extra points made/att', dim: true,       sortVal: p => p.xp_made,       render: p => p.xp_att > 0 ? `${p.xp_made}/${p.xp_att}` : null },
  { key: 'xpp', label: 'XP%',  desc: 'XP make rate',          dim: true,       sortVal: p => p.xp_att ? p.xp_made / p.xp_att : 0, render: p => pct(p.xp_made, p.xp_att) },
  { key: 'pts', label: 'PTS',  desc: 'Points scored',                          sortVal: p => p.fg_made * 3 + p.xp_made, render: p => (p.fg_made * 3 + p.xp_made) || null },
]

const DEF_POS_COLS: PosCol[] = [
  { key: 'g',    label: 'G',    desc: 'Games played',          dim: true,       sortVal: p => p.games_played,          render: p => p.games_played },
  { key: 'tot',  label: 'TOT',  desc: 'Total tackles',         highlight: true, sortVal: p => p.solo_tackles + p.assist_tackles, render: p => p.solo_tackles + p.assist_tackles },
  { key: 'solo', label: 'SOLO', desc: 'Solo tackles',                           sortVal: p => p.solo_tackles,          render: p => p.solo_tackles },
  { key: 'ast',  label: 'AST',  desc: 'Assisted tackles',      dim: true,       sortVal: p => p.assist_tackles,        render: p => p.assist_tackles },
  { key: 'tfl',  label: 'TFL',  desc: 'Tackles for loss',                       sortVal: p => p.tackles_for_loss,      render: p => p.tackles_for_loss > 0 ? p.tackles_for_loss : null },
  { key: 'sck',  label: 'SACK', desc: 'Sacks',                                  sortVal: p => p.sacks,                 render: p => p.sacks > 0 ? p.sacks : null },
  { key: 'int',  label: 'INT',  desc: 'Interceptions',                          sortVal: p => p.def_interceptions,     render: p => p.def_interceptions > 0 ? p.def_interceptions : null },
  { key: 'pbu',  label: 'PBU',  desc: 'Pass breakups',         dim: true,       sortVal: p => p.pass_breakups,         render: p => p.pass_breakups > 0 ? p.pass_breakups : null },
  { key: 'ff',   label: 'FF',   desc: 'Forced fumbles',        dim: true,       sortVal: p => p.forced_fumbles ?? 0,   render: p => (p.forced_fumbles ?? 0) > 0 ? p.forced_fumbles : null },
]

const P_POS_COLS: PosCol[] = [
  { key: 'g',    label: 'G',      desc: 'Games played',         dim: true,       sortVal: p => p.games_played,  render: p => p.games_played },
  { key: 'punts',label: 'PUNTS',  desc: 'Punts',                highlight: true, sortVal: p => p.punts ?? 0,       render: p => p.punts ?? null },
  { key: 'yds',  label: 'YDS',    desc: 'Total punt yards',                      sortVal: p => p.punt_yards ?? 0,  render: p => p.punt_yards ?? null },
  { key: 'avg',  label: 'AVG',    desc: 'Yards per punt',       dim: true,       sortVal: p => { const pn = p.punts ?? 0; return pn > 0 ? (p.punt_yards ?? 0) / pn : 0 }, render: p => { const pn = p.punts ?? 0; return pn > 0 ? ((p.punt_yards ?? 0) / pn).toFixed(1) : null } },
  { key: 'ypg',  label: 'YDS/G',  desc: 'Punt yards per game',  dim: true,       sortVal: p => p.games_played > 0 ? (p.punt_yards ?? 0) / p.games_played : 0, render: p => p.games_played > 0 ? ((p.punt_yards ?? 0) / p.games_played).toFixed(1) : null },
]

const DEF_POS_SET = new Set(['LB','ILB','OLB','MLB','EDGE','DE','DT','NT','DL','CB','S','SS','FS','DB','SAF'])

type StatTab = { key: string; label: string; filter: (p: LeagueLeader) => boolean; defaultSort: string; cols: LeaderCol[] }

type PosTab  = { key: string; label: string; filter: (p: LeagueLeader) => boolean; defaultSort: string; cols: PosCol[] }

export const STAT_TABS: StatTab[] = [
  { key: 'passing',   label: 'Passing',   filter: p => p.attempts >= 100,                                   defaultSort: 'yds', cols: PASSING_COLS },
  { key: 'rushing',   label: 'Rushing',   filter: p => p.carries >= 50,                                     defaultSort: 'yds', cols: RUSHING_COLS },
  { key: 'receiving', label: 'Receiving', filter: p => hasReceivingActivity(p, 20),                        defaultSort: 'yds', cols: RECEIVING_COLS },
  { key: 'defense',   label: 'Defense',   filter: p => p.solo_tackles + p.assist_tackles >= 10,             defaultSort: 'tot', cols: DEFENSE_COLS },
]

export const POS_TABS: PosTab[] = [
  { key: 'qb',  label: 'QB',      filter: p => p.position === 'QB' && p.attempts >= 1,                          defaultSort: 'yds', cols: QB_POS_COLS },
  { key: 'rb',  label: 'RB',      filter: p => p.position === 'RB' && p.carries >= 1,                           defaultSort: 'yds', cols: RB_POS_COLS },
  { key: 'wr',  label: 'WR',      filter: p => p.position === 'WR' && hasReceivingActivity(p),                  defaultSort: 'yds', cols: REC_POS_COLS },
  { key: 'te',  label: 'TE',      filter: p => p.position === 'TE' && hasReceivingActivity(p),                  defaultSort: 'yds', cols: REC_POS_COLS },
  { key: 'k',   label: 'K',       filter: p => p.position === 'K' && (p.fg_att + p.xp_att) >= 1,               defaultSort: 'pts', cols: K_POS_COLS },
  { key: 'def', label: 'Defense', filter: p => DEF_POS_SET.has(p.position ?? '') && (p.solo_tackles + p.assist_tackles) >= 1, defaultSort: 'tot', cols: DEF_POS_COLS },
  { key: 'p',   label: 'P',       filter: p => p.position === 'P' && (p.punts ?? 0) >= 1,                            defaultSort: 'punts', cols: P_POS_COLS },
]



// In-progress season: composite scores for race candidates
