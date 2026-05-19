import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, CURRENT_NFL_SEASON } from '../api'
import type { LeagueLeader, SeasonEntry, WpaLeader, WpaLeaders } from '../api'
import Nav, { backBtnCls } from '../components/Nav'
import { teamLogoUrl } from '../utils/teams'

function passerRating(cmp: number, att: number, yds: number, td: number, int_: number): number | null {
  if (att === 0) return null
  const clamp = (x: number) => Math.min(2.375, Math.max(0, x))
  const a = clamp((cmp / att - 0.3) / 0.2)
  const b = clamp((yds / att - 3) / 4)
  const c = clamp((td / att) / 0.05)
  const d = clamp(2.375 - (int_ / att) / 0.04)
  return ((a + b + c + d) / 6) * 100
}
function pct(a: number, b: number) { return b > 0 ? (a / b * 100).toFixed(1) : null }
function ratio(y: number, a: number, d = 1) { return a > 0 ? (y / a).toFixed(d) : null }
function sfmt(x: number, d = 3) { return `${x >= 0 ? '+' : ''}${x.toFixed(d)}` }

type SortDir = 'asc' | 'desc'
type ColKind = 'trad' | 'adv'

// ── Stat-leaders column definitions ──────────────────────────────────────────

type LeaderCol = {
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

// ── Positional column definitions ─────────────────────────────────────────────

type PosCol = {
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
  { key: 'punts',label: 'PUNTS',  desc: 'Punts',                highlight: true, sortVal: p => (p as any).punts ?? 0,       render: p => (p as any).punts ?? null },
  { key: 'yds',  label: 'YDS',    desc: 'Total punt yards',                      sortVal: p => (p as any).punt_yards ?? 0,  render: p => (p as any).punt_yards ?? null },
  { key: 'avg',  label: 'AVG',    desc: 'Yards per punt',       dim: true,       sortVal: p => { const pn = (p as any).punts ?? 0; return pn > 0 ? ((p as any).punt_yards ?? 0) / pn : 0 }, render: p => { const pn = (p as any).punts ?? 0; return pn > 0 ? (((p as any).punt_yards ?? 0) / pn).toFixed(1) : null } },
  { key: 'ypg',  label: 'YDS/G',  desc: 'Punt yards per game',  dim: true,       sortVal: p => p.games_played > 0 ? ((p as any).punt_yards ?? 0) / p.games_played : 0, render: p => p.games_played > 0 ? (((p as any).punt_yards ?? 0) / p.games_played).toFixed(1) : null },
]

const DEF_POS_SET = new Set(['LB','ILB','OLB','MLB','EDGE','DE','DT','NT','DL','CB','S','SS','FS','DB','SAF'])

type StatTab = { key: string; label: string; filter: (p: LeagueLeader) => boolean; defaultSort: string; cols: LeaderCol[] }
type PosTab  = { key: string; label: string; filter: (p: LeagueLeader) => boolean; defaultSort: string; cols: PosCol[] }

const STAT_TABS: StatTab[] = [
  { key: 'passing',   label: 'Passing',   filter: p => p.attempts >= 100,                                   defaultSort: 'yds', cols: PASSING_COLS },
  { key: 'rushing',   label: 'Rushing',   filter: p => p.carries >= 50,                                     defaultSort: 'yds', cols: RUSHING_COLS },
  { key: 'receiving', label: 'Receiving', filter: p => p.targets >= 20,                                     defaultSort: 'yds', cols: RECEIVING_COLS },
  { key: 'defense',   label: 'Defense',   filter: p => p.solo_tackles + p.assist_tackles >= 10,             defaultSort: 'tot', cols: DEFENSE_COLS },
]

const POS_TABS: PosTab[] = [
  { key: 'qb',  label: 'QB',      filter: p => p.position === 'QB' && p.attempts >= 1,                          defaultSort: 'yds', cols: QB_POS_COLS },
  { key: 'rb',  label: 'RB',      filter: p => p.position === 'RB' && p.carries >= 1,                           defaultSort: 'yds', cols: RB_POS_COLS },
  { key: 'wr',  label: 'WR',      filter: p => p.position === 'WR' && p.targets >= 1,                           defaultSort: 'yds', cols: REC_POS_COLS },
  { key: 'te',  label: 'TE',      filter: p => p.position === 'TE' && p.targets >= 1,                           defaultSort: 'yds', cols: REC_POS_COLS },
  { key: 'k',   label: 'K',       filter: p => p.position === 'K' && (p.fg_att + p.xp_att) >= 1,               defaultSort: 'pts', cols: K_POS_COLS },
  { key: 'def', label: 'Defense', filter: p => DEF_POS_SET.has(p.position ?? '') && (p.solo_tackles + p.assist_tackles) >= 1, defaultSort: 'tot', cols: DEF_POS_COLS },
  { key: 'p',   label: 'P',       filter: p => p.position === 'P' && ((p as any).punts ?? 0) >= 1,                            defaultSort: 'punts', cols: P_POS_COLS },
]

// ── Awards: hardcoded ground truth for past seasons ──────────────────────────

import { PAST_AWARDS, AWARD_ORDER, AWARD_LABEL, type AwardKey, type AwardWinner } from '../utils/awards'

// In-progress season: composite scores for race candidates
function mvpScore(p: LeagueLeader): number {
  // QB-heavy formula but skill-position monsters can break in via rush/rec yards
  if (p.attempts >= 100) {
    return p.pass_yards + p.pass_tds * 20 - p.interceptions_thrown * 15 + p.rush_yards * 0.5 + p.rush_tds * 20 + (p.pass_epa ?? 0) * 5
  }
  if (p.carries + p.receptions >= 100) {
    return (p.rush_yards + p.rec_yards) + (p.rush_tds + p.rec_tds) * 25 + ((p.rush_epa ?? 0) + (p.rec_epa ?? 0)) * 5
  }
  return -Infinity
}
function opoyScore(p: LeagueLeader): number {
  if (p.position === 'QB') return -Infinity
  if (p.carries < 50 && p.targets < 30) return -Infinity
  return (p.rush_yards + p.rec_yards) + (p.rush_tds + p.rec_tds) * 25 + ((p.rush_epa ?? 0) + (p.rec_epa ?? 0)) * 5
}
function dpoyScore(p: LeagueLeader): number {
  const tot = p.solo_tackles + p.assist_tackles
  if (tot < 20 && p.sacks < 5 && p.def_interceptions < 3) return -Infinity
  return p.sacks * 15 + p.tackles_for_loss * 5 + p.def_interceptions * 20 + p.qb_hits * 2 + p.pass_breakups * 3 + p.solo_tackles + p.assist_tackles * 0.5
}

interface RaceScorer { award: AwardKey; label: string; score: (p: LeagueLeader) => number; statLine: (p: LeagueLeader) => string }
const RACE_SCORERS: RaceScorer[] = [
  { award: 'MVP',  label: 'MVP Race',  score: mvpScore,  statLine: p => p.attempts >= 100
    ? `${p.pass_yards.toLocaleString()} YDS · ${p.pass_tds} TD · ${p.interceptions_thrown} INT`
    : `${(p.rush_yards + p.rec_yards).toLocaleString()} SCRIM · ${p.rush_tds + p.rec_tds} TD` },
  { award: 'OPOY', label: 'OPOY Race', score: opoyScore, statLine: p => `${(p.rush_yards + p.rec_yards).toLocaleString()} SCRIM · ${p.rush_tds + p.rec_tds} TD` },
  { award: 'DPOY', label: 'DPOY Race', score: dpoyScore, statLine: p => `${p.solo_tackles + p.assist_tackles} TKL · ${p.sacks} SCK · ${p.def_interceptions} INT` },
]

function AwardWinnerCard({ winner }: { winner: AwardWinner }) {
  const isMvp = winner.award === 'MVP'
  return (
    <div className={`rounded-xl border p-3.5 ${isMvp ? 'border-yellow-500/40 bg-yellow-500/5' : 'border-gray-800 bg-gray-900'}`}>
      <div className={`text-[10px] font-black uppercase tracking-widest mb-2 ${isMvp ? 'text-yellow-300' : 'text-gray-500'}`}>
        {AWARD_LABEL[winner.award]}
      </div>
      <div className="flex items-center gap-2.5">
        <img src={teamLogoUrl(winner.team)} className="w-8 h-8 object-contain shrink-0" alt="" />
        <div className="min-w-0">
          <div className={`text-sm font-bold truncate ${isMvp ? 'text-white' : 'text-gray-200'}`}>{winner.player}</div>
          <div className="text-[11px] text-gray-500">{winner.team} · {winner.pos}</div>
        </div>
      </div>
    </div>
  )
}

function RaceCard({ scorer, leaders }: { scorer: RaceScorer; leaders: LeagueLeader[] }) {
  const top3 = [...leaders]
    .map(p => ({ p, s: scorer.score(p) }))
    .filter(x => x.s > -Infinity)
    .sort((a, b) => b.s - a.s)
    .slice(0, 3)
    .map(x => x.p)
  const isMvp = scorer.award === 'MVP'
  return (
    <div className={`rounded-xl border p-3.5 ${isMvp ? 'border-yellow-500/40 bg-yellow-500/5' : 'border-gray-800 bg-gray-900'}`}>
      <div className={`text-[10px] font-black uppercase tracking-widest mb-2.5 ${isMvp ? 'text-yellow-300' : 'text-gray-500'}`}>
        {scorer.label}
      </div>
      {top3.length === 0
        ? <p className="text-xs text-gray-700">No qualifying candidates yet</p>
        : (
          <div className="space-y-1.5">
            {top3.map((p, i) => (
              <Link key={p.player_id} to={`/players/${p.player_id}`}
                className="flex items-center gap-2 group hover:bg-gray-800/40 rounded px-1 py-0.5 -mx-1 transition-colors">
                <span className={`text-[10px] font-black tabular-nums w-3 shrink-0 ${i === 0 ? 'text-yellow-400' : 'text-gray-600'}`}>{i + 1}</span>
                {p.headshot_url
                  ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                  : <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
                }
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-gray-200 group-hover:text-white truncate transition-colors">{p.player_name}</div>
                  <div className="text-[10px] text-gray-600 truncate">{p.team} · {p.position} · {scorer.statLine(p)}</div>
                </div>
              </Link>
            ))}
          </div>
        )
      }
    </div>
  )
}

function AwardsSection({ season, leaders }: { season: number; leaders: LeagueLeader[] }) {
  const past = PAST_AWARDS[season]
  const isPast = !!past

  if (isPast) {
    return (
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-base font-black text-white tracking-tight uppercase">{season} Award Winners</h2>
          <div className="flex-1 h-px bg-gray-800" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {AWARD_ORDER.map(key => {
            const w = past.find(x => x.award === key)
            return w ? <AwardWinnerCard key={key} winner={w} /> : null
          })}
        </div>
      </div>
    )
  }

  // In-progress season: race view
  if (leaders.length === 0) return null
  return (
    <div className="mb-8">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-base font-black text-white tracking-tight uppercase">{season} Award Races</h2>
        <div className="flex-1 h-px bg-gray-800" />
        <span className="text-[10px] text-gray-600 uppercase tracking-widest">Stat-based · Voting decides actual winners</span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {RACE_SCORERS.map(s => <RaceCard key={s.award} scorer={s} leaders={leaders} />)}
      </div>
    </div>
  )
}

// ── Primary stat config for podiums + dashboard ──────────────────────────────

interface PrimaryStat {
  label: string
  value: (p: LeagueLeader) => number
  display: (p: LeagueLeader) => string
  secondary: (p: LeagueLeader) => string
}

const STAT_PRIMARY: Record<string, PrimaryStat> = {
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

const POS_PRIMARY: Record<string, PrimaryStat> = {
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
    value: p => (p as any).punts ?? 0,
    display: p => String((p as any).punts ?? 0),
    secondary: p => `${((p as any).punt_yards ?? 0).toLocaleString()} YDS · ${((p as any).punts ?? 0) > 0 ? (((p as any).punt_yards ?? 0) / ((p as any).punts ?? 1)).toFixed(1) : '—'} AVG`,
  },
}

// ── Dashboard tiles (top-of-page category leaders) ───────────────────────────

interface DashboardCategory {
  key: string
  label: string
  tabKey: string
  filter: (p: LeagueLeader) => boolean
  primary: PrimaryStat
}

const DASHBOARD_CATEGORIES: DashboardCategory[] = [
  { key: 'pass_yds', label: 'Passing Leader',   tabKey: 'passing',   filter: p => p.attempts >= 100,                   primary: STAT_PRIMARY.passing },
  { key: 'rush_yds', label: 'Rushing Leader',   tabKey: 'rushing',   filter: p => p.carries >= 50,                     primary: STAT_PRIMARY.rushing },
  { key: 'rec_yds',  label: 'Receiving Leader', tabKey: 'receiving', filter: p => p.targets >= 20,                     primary: STAT_PRIMARY.receiving },
  { key: 'tkl',      label: 'Tackles Leader',   tabKey: 'defense',   filter: p => p.solo_tackles + p.assist_tackles >= 10, primary: STAT_PRIMARY.defense },
]

function DashboardTile({ cat, leaders, onClick }: { cat: DashboardCategory; leaders: LeagueLeader[]; onClick: () => void }) {
  const top = leaders.filter(cat.filter).sort((a, b) => cat.primary.value(b) - cat.primary.value(a))[0]
  if (!top) {
    return (
      <button onClick={onClick} className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-left hover:border-gray-700 transition-colors min-h-[148px]">
        <div className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">{cat.label}</div>
        <p className="text-xs text-gray-700 mt-4">No data yet</p>
      </button>
    )
  }
  return (
    <button onClick={onClick} className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-left hover:border-indigo-600 hover:bg-gray-900/70 transition-all w-full">
      <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-3">{cat.label}</div>
      <div className="flex items-center gap-3">
        {top.headshot_url
          ? <img src={top.headshot_url} className="w-12 h-12 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
          : <div className="w-12 h-12 rounded-full bg-gray-800 shrink-0" />
        }
        <div className="flex-1 min-w-0">
          <div className="text-sm font-bold text-white truncate">{top.player_name}</div>
          <div className="text-[11px] text-gray-500 flex items-center gap-1.5 mt-0.5">
            {top.team && <img src={teamLogoUrl(top.team)} className="w-3.5 h-3.5 object-contain opacity-80" alt="" />}
            <span>{top.team ?? '—'}</span>
            {top.position && <><span className="text-gray-700">·</span><span>{top.position}</span></>}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-baseline justify-between">
        <span className="text-2xl font-black text-white tabular-nums leading-none">{cat.primary.display(top)}</span>
        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-600">{cat.primary.label}</span>
      </div>
      <div className="text-[11px] text-gray-500 mt-1.5 truncate">{cat.primary.secondary(top)}</div>
    </button>
  )
}

function StatDashboard({ leaders, onPick }: { leaders: LeagueLeader[]; onPick: (tabKey: string) => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
      {DASHBOARD_CATEGORIES.map(c => (
        <DashboardTile key={c.key} cat={c} leaders={leaders} onClick={() => onPick(c.tabKey)} />
      ))}
    </div>
  )
}

// ── Podium (top 3 for the active tab) ────────────────────────────────────────

const PODIUM_TONES: Record<1 | 2 | 3, { ring: string; text: string; chipBg: string; chipText: string; medal: string }> = {
  1: { ring: 'ring-yellow-500/60', text: 'text-yellow-300', chipBg: 'bg-yellow-500/15 border-yellow-500/40', chipText: 'text-yellow-200', medal: '1st' },
  2: { ring: 'ring-gray-400/50',   text: 'text-gray-200',   chipBg: 'bg-gray-400/15 border-gray-400/40',     chipText: 'text-gray-100',  medal: '2nd' },
  3: { ring: 'ring-amber-700/60',  text: 'text-amber-400',  chipBg: 'bg-amber-700/15 border-amber-700/40',   chipText: 'text-amber-200', medal: '3rd' },
}

function PodiumCard({ player, rank, primary }: { player: LeagueLeader; rank: 1 | 2 | 3; primary: PrimaryStat }) {
  const tone = PODIUM_TONES[rank]
  const isGold = rank === 1
  return (
    <Link
      to={`/players/${player.player_id}`}
      className={`block relative bg-gray-900 border border-gray-800 rounded-xl px-4 hover:border-gray-600 transition-colors ${isGold ? 'py-5' : 'py-4'}`}
    >
      <div className={`absolute -top-2.5 left-3 px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-widest border ${tone.chipBg} ${tone.chipText}`}>
        {tone.medal}
      </div>
      <div className="flex items-center gap-3 mt-1">
        {player.headshot_url
          ? <img src={player.headshot_url} className={`rounded-full object-cover object-top shrink-0 bg-gray-800 ring-2 ${tone.ring} ${isGold ? 'w-16 h-16' : 'w-14 h-14'}`} alt="" />
          : <div className={`rounded-full bg-gray-800 shrink-0 ${isGold ? 'w-16 h-16' : 'w-14 h-14'}`} />
        }
        <div className="flex-1 min-w-0">
          <div className={`font-bold text-white truncate leading-tight ${isGold ? 'text-base' : 'text-sm'}`}>{player.player_name}</div>
          <div className="text-[11px] text-gray-500 flex items-center gap-1.5 mt-0.5">
            {player.team && <img src={teamLogoUrl(player.team)} className="w-3.5 h-3.5 object-contain opacity-80" alt="" />}
            <span>{player.team ?? '—'}</span>
            {player.position && <><span className="text-gray-700">·</span><span>{player.position}</span></>}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className={`font-black text-white tabular-nums leading-none ${isGold ? 'text-3xl' : 'text-2xl'}`}>
          {primary.display(player)}
        </span>
        <span className={`text-[10px] font-bold uppercase tracking-widest ${tone.text}`}>{primary.label}</span>
      </div>
      <div className="text-[11px] text-gray-500 mt-1 truncate">{primary.secondary(player)}</div>
    </Link>
  )
}

function Podium({ players, primary }: { players: LeagueLeader[]; primary: PrimaryStat }) {
  const sorted = [...players].sort((a, b) => primary.value(b) - primary.value(a))
  const top3 = sorted.slice(0, 3)
  if (top3.length < 3) return null
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
      <div className="order-2 sm:order-1"><PodiumCard player={top3[1]} rank={2} primary={primary} /></div>
      <div className="order-1 sm:order-2"><PodiumCard player={top3[0]} rank={1} primary={primary} /></div>
      <div className="order-3"><PodiumCard player={top3[2]} rank={3} primary={primary} /></div>
    </div>
  )
}

// ── Shared rank badge ─────────────────────────────────────────────────────────

function RankBadge({ rank }: { rank: number }) {
  const cls = rank === 1 ? 'text-yellow-400 font-black' : rank === 2 ? 'text-gray-300 font-bold' : rank === 3 ? 'text-amber-600 font-bold' : 'text-gray-600 font-medium'
  return <span className={`text-sm tabular-nums ${cls}`}>{rank}</span>
}

// ── Stat-leaders table ────────────────────────────────────────────────────────

function LeaderTable({ players, cols, sort, onSort }: {
  players: LeagueLeader[]
  cols: LeaderCol[]
  sort: { key: string; dir: SortDir }
  onSort: (key: string) => void
}) {
  const tradCount = cols.filter(c => c.kind === 'trad').length
  const advCount  = cols.filter(c => c.kind === 'adv').length

  const sorted = [...players].sort((a, b) => {
    const col = cols.find(c => c.key === sort.key)
    if (!col) return 0
    const diff = col.sortVal(b) - col.sortVal(a)
    return sort.dir === 'desc' ? diff : -diff
  })

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-right cursor-pointer select-none hover:text-white transition-colors'

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800/50">
            <th colSpan={4} />
            {tradCount > 0 && <th colSpan={tradCount} className="py-1 text-center text-[10px] font-semibold text-gray-600 uppercase tracking-widest border-l border-gray-800/40">Stats</th>}
            {advCount  > 0 && <th colSpan={advCount}  className="py-1 text-center text-[10px] font-semibold text-amber-500/60 uppercase tracking-widest bg-amber-950/20 border-l border-gray-800/40">Advanced</th>}
          </tr>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-gray-500 text-left">Player</th>
            <th className="py-2.5 px-2 text-xs font-semibold text-gray-500 text-left">Pos</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-500 text-left">Team</th>
            {cols.map((c, i) => {
              const active = sort.key === c.key
              const sep = i === 0 || cols[i - 1].kind !== c.kind
              return (
                <th key={c.key} onClick={() => onSort(c.key)}
                  className={`${thBase} ${sep ? 'border-l border-gray-800/40' : ''}
                    ${c.kind === 'adv' ? 'bg-amber-950/10 text-amber-300/50 hover:text-amber-200' : active ? 'text-white' : 'text-gray-500'}`}>
                  <span className="flex items-center justify-end gap-1">
                    {c.label}
                    <span className={`text-[10px] transition-opacity ${active ? 'opacity-100' : 'opacity-0'}`}>
                      {sort.dir === 'desc' ? '↓' : '↑'}
                    </span>
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => (
            <tr key={p.player_id} className="border-t border-gray-800/50 hover:bg-gray-800/30 transition-colors">
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  {p.headshot_url
                    ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                    : <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
                  }
                  <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{p.player_name}</Link>
                </div>
              </td>
              <td className="py-2.5 px-2 whitespace-nowrap">
                <span className="text-xs text-gray-500 font-medium">{p.position ?? '—'}</span>
              </td>
              <td className="py-2.5 px-3 whitespace-nowrap">
                {p.team
                  ? <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
                      <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                      <span className="text-xs text-gray-400 group-hover:text-white transition-colors font-medium">{p.team}</span>
                    </Link>
                  : <span className="text-gray-700 text-xs">—</span>
                }
              </td>
              {cols.map((c, i) => {
                const sep = i === 0 || cols[i - 1].kind !== c.kind
                const val = c.render(p)
                const isNull = val === null || val === undefined
                const str = isNull ? null : String(val)
                const isPos = !isNull && str!.startsWith('+')
                const isNeg = !isNull && str!.startsWith('-')
                return (
                  <td key={c.key} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap
                    ${sep ? 'border-l border-gray-800/30' : ''}
                    ${c.kind === 'adv' ? 'bg-amber-950/10' : ''}
                    ${isNull ? 'text-gray-700' : isPos ? 'text-emerald-400 font-semibold' : isNeg ? 'text-red-400 font-semibold' : c.highlight ? 'text-white font-bold' : c.kind === 'adv' ? 'text-amber-200/80' : c.dim ? 'text-gray-500' : 'text-gray-300'}`}>
                    {isNull ? '—' : str}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Positional rankings table ─────────────────────────────────────────────────

function PosTable({ players, cols, sort, onSort }: {
  players: LeagueLeader[]
  cols: PosCol[]
  sort: { key: string; dir: SortDir }
  onSort: (key: string) => void
}) {
  const sorted = [...players].sort((a, b) => {
    const col = cols.find(c => c.key === sort.key)
    if (!col) return 0
    const diff = col.sortVal(b) - col.sortVal(a)
    return sort.dir === 'desc' ? diff : -diff
  })

  const thBase = 'py-2 px-3 text-xs font-medium whitespace-nowrap text-right cursor-pointer select-none hover:text-white transition-colors'

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-gray-500 text-left min-w-[160px]">Player</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-500 text-left">Team</th>
            {cols.map(c => {
              const active = sort.key === c.key
              return (
                <th key={c.key} onClick={() => onSort(c.key)} title={c.desc}
                  className={`${thBase} ${active ? 'text-white' : c.dim ? 'text-gray-600' : 'text-gray-500'}`}>
                  <span className="flex items-center justify-end gap-1">
                    {c.label}
                    <span className={`text-[10px] transition-opacity ${active ? 'opacity-100' : 'opacity-0'}`}>
                      {sort.dir === 'desc' ? '↓' : '↑'}
                    </span>
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p, i) => (
            <tr key={p.player_id} className="border-t border-gray-800/50 hover:bg-gray-800/30 transition-colors">
              <td className="py-2.5 pl-4 pr-2 text-right"><RankBadge rank={i + 1} /></td>
              <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                <div className="flex items-center gap-2">
                  {p.headshot_url
                    ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                    : <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
                  }
                  <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{p.player_name}</Link>
                </div>
              </td>
              <td className="py-2.5 px-3 whitespace-nowrap">
                {p.team
                  ? <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
                      <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                      <span className="text-xs text-gray-400 group-hover:text-white transition-colors font-medium">{p.team}</span>
                    </Link>
                  : <span className="text-gray-700 text-xs">—</span>
                }
              </td>
              {cols.map(c => {
                const val = c.render(p)
                const isNull = val === null || val === undefined
                const str = isNull ? null : String(val)
                const isPos = !isNull && str!.startsWith('+')
                const isNeg = !isNull && str!.startsWith('-')
                return (
                  <td key={c.key} className={`py-2.5 px-3 text-right tabular-nums text-sm whitespace-nowrap
                    ${isNull ? 'text-gray-700' : isPos ? 'text-emerald-400 font-semibold' : isNeg ? 'text-red-400 font-semibold' : c.highlight ? 'text-white font-bold' : c.dim ? 'text-gray-500' : 'text-gray-300'}`}>
                    {isNull ? '—' : str}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── WPA table ─────────────────────────────────────────────────────────────────

type WpaSubTab = 'passing' | 'rushing' | 'receiving'

function WpaTable({ players, contextLabel }: { players: WpaLeader[]; contextLabel: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800/50">
            <th colSpan={4} />
            <th colSpan={1} className="py-1 text-center text-[10px] font-semibold text-violet-400/60 uppercase tracking-widest bg-violet-950/20 border-l border-gray-800/40">WPA</th>
            <th colSpan={2} className="py-1 text-center text-[10px] font-semibold text-gray-600 uppercase tracking-widest border-l border-gray-800/40">Context</th>
          </tr>
          <tr className="border-b border-gray-800">
            <th className="py-2.5 pl-4 pr-2 text-xs font-semibold text-gray-500 text-right w-8">#</th>
            <th className="py-2.5 pl-2 pr-3 text-xs font-semibold text-gray-500 text-left">Player</th>
            <th className="py-2.5 px-2 text-xs font-semibold text-gray-500 text-left">Pos</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-500 text-left">Team</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-violet-400/50 text-right border-l border-gray-800/40 bg-violet-950/10">WPA</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-600 text-right border-l border-gray-800/40">G</th>
            <th className="py-2.5 px-3 text-xs font-semibold text-gray-600 text-right">{contextLabel}</th>
          </tr>
        </thead>
        <tbody>
          {players.map((p, i) => {
            const wpaStr = `${p.wpa >= 0 ? '+' : ''}${p.wpa.toFixed(3)}`
            const isPos = p.wpa >= 0
            const ctx = p.attempts ?? p.carries ?? p.receptions ?? null
            return (
              <tr key={p.player_id} className="border-t border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                <td className="py-2.5 pl-4 pr-2 text-right">
                  <span className={`text-sm tabular-nums ${i === 0 ? 'text-yellow-400 font-black' : i === 1 ? 'text-gray-300 font-bold' : i === 2 ? 'text-amber-600 font-bold' : 'text-gray-600 font-medium'}`}>{i + 1}</span>
                </td>
                <td className="py-2.5 pl-2 pr-3 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    {p.headshot_url
                      ? <img src={p.headshot_url} className="w-7 h-7 rounded-full object-cover object-top shrink-0 bg-gray-800" alt="" />
                      : <div className="w-7 h-7 rounded-full bg-gray-800 shrink-0" />
                    }
                    <Link to={`/players/${p.player_id}`} className="text-indigo-400 hover:underline font-semibold text-sm leading-tight">{p.player_name}</Link>
                  </div>
                </td>
                <td className="py-2.5 px-2 whitespace-nowrap">
                  <span className="text-xs text-gray-500 font-medium">{p.position ?? '—'}</span>
                </td>
                <td className="py-2.5 px-3 whitespace-nowrap">
                  {p.team
                    ? <Link to={`/teams/${p.team}`} className="flex items-center gap-1.5 group w-fit">
                        <img src={teamLogoUrl(p.team)} className="w-5 h-5 object-contain opacity-80 group-hover:opacity-100" alt="" />
                        <span className="text-xs text-gray-400 group-hover:text-white transition-colors font-medium">{p.team}</span>
                      </Link>
                    : <span className="text-gray-700 text-xs">—</span>
                  }
                </td>
                <td className={`py-2.5 px-3 text-right tabular-nums font-bold text-sm border-l border-gray-800/30 bg-violet-950/10 ${isPos ? 'text-emerald-400' : 'text-red-400'}`}>
                  {wpaStr}
                </td>
                <td className="py-2.5 px-3 text-right tabular-nums text-sm text-gray-600 border-l border-gray-800/30">{p.games_played}</td>
                <td className="py-2.5 px-3 text-right tabular-nums text-sm text-gray-500">{ctx ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Mode = 'leaders' | 'positions'

export default function LeadersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [seasons, setSeasons] = useState<SeasonEntry[]>([])
  const [leaders, setLeaders] = useState<LeagueLeader[]>([])
  const [loading, setLoading] = useState(true)
  const [wpaData, setWpaData] = useState<WpaLeaders | null>(null)
  const [wpaLoading, setWpaLoading] = useState(false)
  const [wpaSubTab, setWpaSubTab] = useState<WpaSubTab>('passing')

  const season  = Number(searchParams.get('season') ?? CURRENT_NFL_SEASON)
  const mode    = (searchParams.get('mode') ?? 'leaders') as Mode
  const statKey = searchParams.get('tab') ?? 'passing'
  const posKey  = searchParams.get('pos') ?? 'qb'

  const statTab = STAT_TABS.find(t => t.key === statKey) ?? STAT_TABS[0]
  const posTab  = POS_TABS.find(t => t.key === posKey)   ?? POS_TABS[0]

  const WPA_KEY = 'wpa'
  const isWpa = statKey === WPA_KEY

  const [sorts, setSorts] = useState<Record<string, { key: string; dir: SortDir }>>(() => ({
    ...Object.fromEntries(STAT_TABS.map(t => [t.key, { key: t.defaultSort, dir: 'desc' as SortDir }])),
    ...Object.fromEntries(POS_TABS.map(t => [t.key, { key: t.defaultSort, dir: 'desc' as SortDir }])),
  }))

  useEffect(() => {
    api.seasons().then(all => setSeasons(all.filter(s => s.status === 'loaded')))
  }, [])

  useEffect(() => {
    setLoading(true)
    setLeaders([])
    api.leaders(season).then(setLeaders).finally(() => setLoading(false))
  }, [season])

  useEffect(() => {
    if (!isWpa || mode !== 'leaders') return
    setWpaLoading(true)
    setWpaData(null)
    api.wpaLeaders(season).then(setWpaData).finally(() => setWpaLoading(false))
  }, [isWpa, mode, season])

  function setMode(m: Mode) { setSearchParams(p => { p.set('mode', m); return p }, { replace: true }) }
  function setStatTab(key: string) { setSearchParams(p => { p.set('tab', key); return p }, { replace: true }) }
  function setPosTab(key: string) { setSearchParams(p => { p.set('pos', key); return p }, { replace: true }) }

  function handleSort(tabKey: string, colKey: string) {
    setSorts(prev => {
      const cur = prev[tabKey]
      return { ...prev, [tabKey]: cur.key === colKey ? { key: colKey, dir: cur.dir === 'desc' ? 'asc' : 'desc' } : { key: colKey, dir: 'desc' } }
    })
  }

  return (
    <div className="min-h-screen bg-gray-950">
      <Nav title="League Leaders" />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <button onClick={() => navigate(-1)} className={`${backBtnCls} mb-6`}>← Back</button>

        <div className="flex items-end justify-between mb-8 flex-wrap gap-4">
          <div>
            <h1 className="text-4xl font-black text-white tracking-tight leading-none">League Leaders</h1>
            <p className="text-gray-500 text-sm mt-2 uppercase tracking-widest font-medium">{season} NFL Season</p>
          </div>
          <select
            value={season}
            onChange={e => setSearchParams(p => { p.set('season', String(e.target.value)); return p }, { replace: true })}
            className="bg-gray-800 border border-gray-700 text-white text-sm font-semibold rounded-lg px-4 py-2.5 focus:outline-none focus:border-indigo-500 cursor-pointer hover:border-gray-500 transition-colors"
          >
            {seasons.map(s => (
              <option key={s.season} value={s.season}>{s.season}</option>
            ))}
          </select>
        </div>

        {/* Awards section */}
        {(PAST_AWARDS[season] || (!loading && leaders.length > 0)) && (
          <AwardsSection season={season} leaders={leaders} />
        )}

        {/* Dashboard: category leaders across all stats */}
        {!loading && leaders.length > 0 && (
          <StatDashboard
            leaders={leaders}
            onPick={k => {
              setSearchParams(p => { p.set('mode', 'leaders'); p.set('tab', k); return p }, { replace: true })
            }}
          />
        )}

        {/* Mode toggle */}
        <div className="flex gap-1 mb-5 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
          <button
            onClick={() => setMode('leaders')}
            className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${mode === 'leaders' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}
          >
            Stat Leaders
          </button>
          <button
            onClick={() => setMode('positions')}
            className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${mode === 'positions' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}
          >
            By Position
          </button>
        </div>

        {mode === 'leaders' ? (
          <>
            {/* Stat leaders tab bar */}
            <div className="flex gap-1 mb-4 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit flex-wrap">
              {STAT_TABS.map(t => (
                <button key={t.key} onClick={() => setStatTab(t.key)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${statKey === t.key ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'}`}>
                  {t.label}
                </button>
              ))}
              <button onClick={() => setStatTab(WPA_KEY)}
                className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${isWpa ? 'bg-violet-700 text-white' : 'text-gray-400 hover:text-white'}`}>
                WPA
              </button>
            </div>

            {isWpa ? (
              <div>
                <div className="mb-3 flex items-center gap-2">
                  <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
                    {(['passing', 'rushing', 'receiving'] as WpaSubTab[]).map(s => (
                      <button key={s} onClick={() => setWpaSubTab(s)}
                        className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-colors ${wpaSubTab === s ? 'bg-violet-700 text-white' : 'text-gray-400 hover:text-white'}`}>
                        {s}
                      </button>
                    ))}
                  </div>
                  <span className="text-xs text-gray-600">
                    {wpaSubTab === 'passing' ? 'Air WPA credited to passer (≥50 att)' : wpaSubTab === 'rushing' ? 'WPA on rush plays (≥50 car)' : 'YAC WPA credited to receiver (≥20 rec)'}
                  </span>
                </div>
                <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                  {wpaLoading ? <p className="p-8 text-gray-500 text-sm">Loading…</p>
                    : !wpaData ? <p className="p-8 text-gray-600 text-sm">No WPA data for {season}.</p>
                    : <WpaTable players={wpaData[wpaSubTab]} contextLabel={wpaSubTab === 'passing' ? 'ATT' : wpaSubTab === 'rushing' ? 'CAR' : 'REC'} />
                  }
                </div>
              </div>
            ) : (
              <>
                {!loading && leaders.filter(statTab.filter).length >= 3 && STAT_PRIMARY[statTab.key] && (
                  <Podium players={leaders.filter(statTab.filter)} primary={STAT_PRIMARY[statTab.key]} />
                )}
                <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                  {loading ? <p className="p-8 text-gray-500 text-sm">Loading…</p>
                    : leaders.filter(statTab.filter).length === 0 ? <p className="p-8 text-gray-600 text-sm">No data for {season}.</p>
                    : <LeaderTable
                        players={leaders.filter(statTab.filter)}
                        cols={statTab.cols}
                        sort={sorts[statTab.key]}
                        onSort={key => handleSort(statTab.key, key)}
                      />
                  }
                </div>
              </>
            )}
          </>
        ) : (
          <>
            {/* By position tab bar */}
            <div className="flex gap-1 mb-4 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit flex-wrap">
              {POS_TABS.map(t => (
                <button key={t.key} onClick={() => setPosTab(t.key)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${posKey === t.key ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'}`}>
                  {t.label}
                </button>
              ))}
            </div>

            {!loading && leaders.filter(posTab.filter).length >= 3 && POS_PRIMARY[posTab.key] && (
              <Podium players={leaders.filter(posTab.filter)} primary={POS_PRIMARY[posTab.key]} />
            )}
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              {loading ? <p className="p-8 text-gray-500 text-sm">Loading…</p>
                : leaders.filter(posTab.filter).length === 0 ? <p className="p-8 text-gray-600 text-sm">No {posTab.label} data for {season}.</p>
                : <PosTable
                    players={leaders.filter(posTab.filter)}
                    cols={posTab.cols}
                    sort={sorts[posTab.key]}
                    onSort={key => handleSort(posTab.key, key)}
                  />
              }
            </div>
          </>
        )}

      </div>
    </div>
  )
}
