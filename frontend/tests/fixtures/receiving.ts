import type { Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import type { PlayerReceivingSplits, PlayerSplit, ReceivingRow, ReceivingSeason } from '../../src/types'
import { mockSplits } from './splits'
import { playerProfile } from './playerProfile'

// Real responses captured read-only from the 28-season verified receiving copy.
export const receivingFixtures = (JSON.parse(readFileSync(new URL('./receivingSplits.json', import.meta.url), 'utf8')) as {
  players: Record<'gibbs' | 'jefferson' | 'gonzalez' | 'partial', PlayerReceivingSplits>
}).players
export const receivingScope: PlayerReceivingSplits['scope'] = 'Qualified regular-season receiving; observed production on supplied games'

export function preparedSeason(row: PlayerSplit): ReceivingSeason {
  const dimension = row.split_dim === 'overall' ? 'down' : row.split_dim
  const explained: ReceivingRow = { ...row, interceptions: null, cpoe: null, unavailable_metrics: {} }
  for (const field of ['att', 'cmp', 'yards', 'td', 'yac', 'air_yards', 'first_downs', 'epa', 'success_pct'] as const) {
    if (explained[field] == null) explained.unavailable_metrics[field] = 'Unavailable for this season.'
  }
  return { season: row.season, status: 'prepared', reason: null,
    overall: { ...explained, split_dim: 'overall', split_value: 'all' },
    rows: [{ ...explained, split_dim: dimension,
      split_value: row.split_dim === 'overall' ? '1' : row.split_value }],
    game_coverage: { status: 'complete', supplied_games: 1, recorded_completed_games: 1,
      missing_game_ids: [], unconfirmed_game_ids: [], reason: null },
    views: { [dimension]: { status: 'complete', reason: null, definition: 'Existing situational split definition',
      excluded: { att: row.att == null ? null : 0, cmp: 0, yards: 0, td: 0, yac: row.yac == null ? null : 0, first_downs: 0 } } },
  }
}

export async function mockReceiving(page: Page, data: PlayerReceivingSplits[] = [receivingFixtures.gibbs]) {
  await mockSplits(page)
  await page.route('**/api/seasons', route => route.fulfill({ json: [2026, 2024, 2009, 2004].map(season => ({ season, status: 'loaded' })) }))
  await page.route(url => /^\/api\/players\/[^/]+\/receiving-splits$/.test(url.pathname), route => {
    const id = new URL(route.request().url()).pathname.split('/').at(-2)!
    return route.fulfill({ json: data.find(item => item.player_id === id) ?? { player_id: id, scope: receivingScope, seasons: [] } })
  })
  await page.route(url => /^\/api\/players\/[^/]+$/.test(url.pathname), route => {
    const id = new URL(route.request().url()).pathname.split('/').at(-1)!
    const names: Record<string, string> = { '00-0039139': 'Jahmyr Gibbs', '00-0036322': 'Justin Jefferson', '00-0006101': 'Tony Gonzalez', '00-0039337': 'Current receiver' }
    // Intentionally unrelated legacy game-log numbers: receiving totals must
    // come from the prepared response, even if this profile is stale/empty.
    return route.fulfill({ json: { ...playerProfile, player_id: id, player_name: names[id] ?? id, position: 'WR', games: [] } })
  })
}
