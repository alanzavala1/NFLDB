import { CURRENT_NFL_SEASON } from '../../api'
import type { Example } from './types'

export const SEASONS = Array.from({ length: CURRENT_NFL_SEASON - 1998 }, (_, i) => CURRENT_NFL_SEASON - i)

export const PLAYER_EXAMPLES: Example[] = [
  { label: 'Allen vs Mahomes', names: ['Josh Allen', 'Patrick Mahomes'], cat: 'passing' },
  { label: 'Jefferson vs Chase', names: ['Justin Jefferson', "Ja'Marr Chase"], cat: 'receiving' },
  { label: 'Henry vs Barkley', names: ['Derrick Henry', 'Saquon Barkley'], cat: 'rushing' },
]

export const TEAM_EXAMPLES: Example[] = [
  { label: 'Seahawks vs Patriots', teams: ['SEA', 'NE'] },
  { label: 'Chiefs vs Bills', teams: ['KC', 'BUF'] },
]

const ENTITY_COLORS = ['99,102,241', '20,184,166', '245,158,11', '56,189,248', '244,63,94', '168,85,247']

export const entityColor = (i: number) => ENTITY_COLORS[i % ENTITY_COLORS.length]

// Curated "key stats" per category/side — keeps the side-by-side narrow.
export const KEY_METRICS: Record<string, string[]> = {
  passing: ['ya', 'td', 'int', 'conv', 'cpoe', 'epa', 'succ'],
  rushing: ['ypc', 'td', 'conv', 'epa', 'succ'],
  receiving: ['ypr', 'td', 'conv', 'epa', 'succ'],
  defense: ['tackles', 'tfl', 'sacks', 'qb_hits', 'int'],  // player defense
  team_offense: ['epa', 'succ', 'ypp', 'expl'],
  team_defense: ['epa', 'succ', 'ypp', 'expl'],
}

// Game-based sections (Season / Opponent) read like a box score, so their
// key columns lead with total yards and the headline rate (passer rating).
export const GAME_METRICS: Record<string, string[]> = {
  passing: ['yds', 'td', 'int', 'rate', 'epa'],
  rushing: ['yds', 'td', 'ypc', 'epa'],
  receiving: ['rec', 'yds', 'td', 'ypr', 'epa'],
}
