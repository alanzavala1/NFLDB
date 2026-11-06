import type { GameDetail, GamePlayerStats, ScheduleWeek } from '../../types'

export function teamTotals(players: GamePlayerStats[]) {
  const sum = (fn: (p: GamePlayerStats) => number) => players.reduce((a, p) => a + fn(p), 0)
  return {
    totalYds:   sum(p => p.pass_yards + p.rush_yards),
    passCmp:    sum(p => p.completions),
    passAtt:    sum(p => p.attempts),
    passYds:    sum(p => p.pass_yards),
    passTDs:    sum(p => p.pass_tds),
    ints:       sum(p => p.interceptions_thrown),
    sacksTaken: sum(p => p.sacks_taken),
    rushCar:    sum(p => p.carries),
    rushYds:    sum(p => p.rush_yards),
    rushTDs:    sum(p => p.rush_tds),
    sacks:      sum(p => p.sacks),
    defInts:    sum(p => p.def_interceptions),
  }
}

export function selectSameRound(game: GameDetail | undefined, weeks: ScheduleWeek[] | undefined) {
  if (!game) return []
  const all = (weeks ?? []).flatMap(week => week.games)
  if (game.game_type === 'REG') return all.filter(candidate => candidate.week === game.week)
  const teams = new Set([game.away_team, game.home_team])
  return all.filter(candidate => candidate.game_type !== 'REG' && candidate.away_score != null && candidate.home_score != null)
    .filter(candidate => teams.has(candidate.away_team) || teams.has(candidate.home_team) || candidate.game_id === game.game_id)
}
