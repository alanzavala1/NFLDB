import type { Page } from '@playwright/test'
import type { SeasonStatus, TeamGame, TeamProfile, TeamAnalyticsRow, TeamSplit, InjuryStatus, DepthChartEntry, RosterPlayer } from '../../src/types'
import { mockApi } from './scores'

export const teamGame: TeamGame = {
  game_id: '2023_01_BUF_MIA', season: 2023, game_type: 'REG', week: 1,
  gameday: '2023-09-10', gametime: '13:00', away_team: 'BUF', home_team: 'MIA',
  away_score: 24, home_score: 17, stadium: null, roof: null, surface: null,
  temp: null, wind: null, away_record: null, home_record: null,
}

export const teamProfile: TeamProfile = {
  team: 'BUF', season: 2023, games: [teamGame], leaders: [], playoff_leaders: [],
}

export const analyticsRow: TeamAnalyticsRow = {
  team: 'BUF', games: 1, wins: 1, losses: 0, ties: 0, pf_total: 24, pa_total: 17,
  ppg: 24, papg: 17, pt_diff_per_game: 7, pts_per_drive: null, pts_per_drive_allowed: null,
  total_drives: null, total_drives_allowed: null, rz_td_pct: null, rz_td_pct_allowed: null,
  off_turnovers_total: 0, def_takeaways_total: 1, turnover_diff_per_game: 1,
  off_plays_count: 40, off_epa_play: 0.25, off_pass_epa: null, off_rush_epa: null,
  off_success_pct: null, off_explosive_pct: null, proe: null, third_down_pct: null,
  def_epa_play: -0.1, def_pass_epa: null, def_rush_epa: null, def_success_pct: null,
  def_explosive_pct: null, def_sack_pct: null, third_down_stop_pct: null,
  ppg_rank: 3, pts_per_drive_rank: null, off_epa_play_rank: 3, off_pass_epa_rank: null,
  off_rush_epa_rank: null, off_success_rank: null, off_explosive_rank: null,
  third_down_rank: null, rz_td_rank: null, proe_rank: null, papg_rank: 3,
  pts_per_drive_allowed_rank: null, def_epa_play_rank: 3, def_pass_epa_rank: null,
  def_rush_epa_rank: null, def_success_rank: null, def_explosive_rank: null,
  third_down_stop_rank: null, rz_td_allowed_rank: null, def_sack_rank: null,
  pt_diff_rank: 3, to_diff_rank: 3,
}

export const teamSplit: TeamSplit = {
  side: 'offense', split_dim: 'game_script', split_value: 'leading', sort_order: 1,
  plays: 40, epa_play: 0.2, success_pct: 50, pass_rate: 60, yards_play: 5,
  explosive_pct: 10, pass_epa: 0.3, rush_epa: 0.1,
}
export const injury: InjuryStatus = {
  season: 2023, week: 1, team: 'BUF', report_primary_injury: 'Ankle', report_secondary_injury: null,
  report_status: 'Questionable', practice_primary_injury: null, practice_status: null,
  full_name: 'Injured quarterback', position: 'QB', gsis_id: 'injured',
}
export const starter: DepthChartEntry = {
  season: 2023, week: 1, team: 'BUF', formation: 'Offense', depth_position: 'QB', depth_team: '1',
  gsis_id: 'starter', full_name: 'Starting quarterback', position: 'QB', jersey_number: '17',
}
export const rosterPlayer: RosterPlayer = {
  player_id: 'test-player', player_name: 'Roster quarterback', position: 'QB', jersey_number: 17, headshot_url: null,
}

export async function mockTeamSections(page: Page) {
  await mockTeam(page, [{ season: 2023, status: 'loaded' }, { season: 2022, status: 'loaded' }])
  await page.route('**/api/team-analytics?*', route => route.fulfill({ json: {
    season: Number(new URL(route.request().url()).searchParams.get('season')),
    league: [analyticsRow, { ...analyticsRow, team: 'SF' }],
  } }))
  for (const [suffix, json] of [
    ['splits', [teamSplit]], ['injuries', [injury]], ['depth-chart', [starter]], ['roster', [rosterPlayer]],
  ] as const) await page.route(url => url.pathname.endsWith(`/teams/BUF/${suffix}`), route => route.fulfill({ json }))
}

export async function mockTeam(page: Page, seasons: SeasonStatus[] = [{ season: 2023, status: 'loaded' }]) {
  const reads = await mockApi(page, seasons)
  await page.route(url => /^\/api\/teams\/[^/]+(?:\/.*)?$/.test(url.pathname), route => {
    const url = new URL(route.request().url())
    reads.push(url.pathname)
    const season = Number(url.searchParams.get('season'))
    const team = url.pathname.split('/')[3]
    if (/^\/api\/teams\/[^/]+$/.test(url.pathname)) return route.fulfill({ json: {
      ...teamProfile, team, season,
      games: [{ ...teamGame, season, away_team: team, game_id: `${season}_01_${team}_MIA` }],
    } })
    return route.fulfill({ json: [] })
  })
  await page.route('**/api/team-analytics?*', route => route.fulfill({ json: { season: 2023, league: [] } }))
  return reads
}
