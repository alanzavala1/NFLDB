import type { PassingRow, PassingSeason, PlayerPassingSplits, PlayerSplit } from '../../src/types'

export const passingScope = 'Qualified regular-season passing; observed production on supplied games' as const

// Small transport/layout fixture, not a statistical reference. Population and
// rounding regressions use explicit components and captured API examples.
export function passingFixture(rows: PlayerSplit[], player = 'test-player'): PlayerPassingSplits {
  const seasons: PassingSeason[] = [...new Set(rows.filter(row => row.category === 'passing').map(row => row.season))].sort().map(season => {
    const selected: PassingRow[] = rows.filter(row => row.category === 'passing' && row.season === season).map(row => ({
      ...row, unavailable_metrics: {}, aggregation: {
        epa_sum: row.epa == null ? null : row.epa * row.att!, successes: row.success_pct == null ? null : row.success_pct * row.att! / 100,
        cpoe_sum: row.cpoe == null ? 0 : row.cpoe * row.att!, cpoe_count: row.cpoe == null ? 0 : row.att!,
      },
    }))
    const down = selected.filter(row => row.split_dim === 'down')
    const sum = (field: 'att' | 'cmp' | 'yards' | 'td' | 'interceptions' | 'first_downs' | 'air_yards' | 'yac') => down.reduce((total, row) => total + (row[field] ?? 0), 0)
    const att = sum('att')
    const aggregation = { epa_sum: down.reduce((total, row) => total + row.aggregation.epa_sum!, 0),
      successes: down.reduce((total, row) => total + row.aggregation.successes!, 0),
      cpoe_sum: down.reduce((total, row) => total + row.aggregation.cpoe_sum!, 0),
      cpoe_count: down.reduce((total, row) => total + row.aggregation.cpoe_count!, 0) }
    const overall: PassingRow = { ...down[0], split_dim: 'overall', split_value: 'all', sort_order: 1,
      att, cmp: sum('cmp'), yards: sum('yards'), td: sum('td'), interceptions: sum('interceptions'), first_downs: sum('first_downs'),
      air_yards: sum('air_yards'), yac: sum('yac'), aggregation,
      epa: aggregation.epa_sum / att, success_pct: aggregation.successes / att * 100,
      cpoe: aggregation.cpoe_sum / aggregation.cpoe_count }
    selected.push({ ...overall, split_dim: 'opponent', split_value: 'MIA', sort_order: null })
    const countFields = ['att', 'cmp', 'yards', 'td', 'interceptions', 'first_downs'] as const
    const views = Object.fromEntries([...new Set(selected.map(row => row.split_dim))].map(dimension => {
      const group = selected.filter(row => row.split_dim === dimension)
      const excluded = { ...Object.fromEntries(countFields.map(field => [field, overall[field]! - group.reduce((total, row) => total + row[field]!, 0)])), sacks: 0 } as PassingSeason['views'][string]['excluded']
      const partial = Object.values(excluded).some(value => value !== 0)
      return [dimension, { status: partial ? 'partial' : 'complete', reason: partial ? 'Some plays lack supported context.' : null,
        definition: 'Recorded play context.', excluded }]
    })) as PassingSeason['views']
    return { season, status: 'prepared', reason: null, overall, rows: selected, views,
      game_coverage: { status: 'complete', supplied_games: 1, recorded_completed_games: 1,
        missing_game_ids: [], unconfirmed_game_ids: [], reason: null } }
  })
  return { player_id: player, scope: passingScope, seasons }
}
