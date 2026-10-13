import type { Page } from '@playwright/test'
import type { SeasonStatus, TeamGame, TeamProfile } from '../../src/types'
import { mockApi } from './scores'

export const teamGame: TeamGame = {
  game_id: '2023_01_BUF_MIA', season: 2023, week: 1,
  gameday: '2023-09-10', gametime: '13:00', away_team: 'BUF', home_team: 'MIA',
  away_score: 24, home_score: 17, stadium: null, roof: null, surface: null,
  temp: null, wind: null, away_record: null, home_record: null,
}

export const teamProfile: TeamProfile = {
  team: 'BUF', season: 2023, games: [teamGame], leaders: [], playoff_leaders: [],
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
