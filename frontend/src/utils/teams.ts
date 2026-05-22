// Maps nfl_data_py abbreviations → ESPN logo abbreviations.
// nfl_data_py uses 3-letter alternates for some teams in the rosters table
// (BLT/CLV/ARZ/HST/SL) that don't match the standard codes used elsewhere
// — normalize them to the schedules-table abbreviations ESPN serves.
const ABBREV_MAP: Record<string, string> = {
  // Current
  LA: 'LAR',
  // Historical relocations
  STL: 'LAR',   // St. Louis Rams
  SD:  'LAC',   // San Diego Chargers
  OAK: 'LV',    // Oakland Raiders
  // Legacy names that ESPN still serves
  JAC: 'JAX',
  // Alternate abbreviations that appear in the rosters table
  BLT: 'BAL',   // Baltimore Ravens
  CLV: 'CLE',   // Cleveland Browns
  ARZ: 'ARI',   // Arizona Cardinals
  HST: 'HOU',   // Houston Texans
  SL:  'LAR',   // St. Louis Rams (now Rams)
}

export function teamLogoUrl(team: string): string {
  const abbrev = ABBREV_MAP[team] ?? team
  return `https://a.espncdn.com/i/teamlogos/nfl/500/${abbrev.toLowerCase()}.png`
}

const TEAM_NAMES: Record<string, string> = {
  ARI: 'Arizona Cardinals',    ATL: 'Atlanta Falcons',
  BAL: 'Baltimore Ravens',     BUF: 'Buffalo Bills',
  CAR: 'Carolina Panthers',    CHI: 'Chicago Bears',
  CIN: 'Cincinnati Bengals',   CLE: 'Cleveland Browns',
  DAL: 'Dallas Cowboys',       DEN: 'Denver Broncos',
  DET: 'Detroit Lions',        GB:  'Green Bay Packers',
  HOU: 'Houston Texans',       IND: 'Indianapolis Colts',
  JAX: 'Jacksonville Jaguars', KC:  'Kansas City Chiefs',
  LAC: 'Los Angeles Chargers', LA:  'Los Angeles Rams',
  LV:  'Las Vegas Raiders',    MIA: 'Miami Dolphins',
  MIN: 'Minnesota Vikings',    NE:  'New England Patriots',
  NO:  'New Orleans Saints',   NYG: 'New York Giants',
  NYJ: 'New York Jets',        PHI: 'Philadelphia Eagles',
  PIT: 'Pittsburgh Steelers',  SEA: 'Seattle Seahawks',
  SF:  'San Francisco 49ers',  TB:  'Tampa Bay Buccaneers',
  TEN: 'Tennessee Titans',     WAS: 'Washington Commanders',
  // Historical
  OAK: 'Oakland Raiders',      SD:  'San Diego Chargers',
  STL: 'St. Louis Rams',       JAC: 'Jacksonville Jaguars',
  // Alternate abbreviations that appear in the rosters table
  BLT: 'Baltimore Ravens',     CLV: 'Cleveland Browns',
  ARZ: 'Arizona Cardinals',    HST: 'Houston Texans',
  SL:  'St. Louis Rams',
}

export function teamName(abbrev: string): string {
  return TEAM_NAMES[abbrev] ?? abbrev
}

export const CONFERENCES: Record<string, Record<string, string[]>> = {
  AFC: {
    East:  ['BUF', 'MIA', 'NE',  'NYJ'],
    North: ['BAL', 'CIN', 'CLE', 'PIT'],
    South: ['HOU', 'IND', 'JAX', 'TEN'],
    West:  ['DEN', 'KC',  'LV',  'LAC'],
  },
  NFC: {
    East:  ['DAL', 'NYG', 'PHI', 'WAS'],
    North: ['CHI', 'DET', 'GB',  'MIN'],
    South: ['ATL', 'CAR', 'NO',  'TB'],
    West:  ['ARI', 'LA',  'SEA', 'SF'],
  },
}

/** Returns the team a player appeared for most in a set of games. */
export function primaryTeam(teams: string[]): string {
  const counts: Record<string, number> = {}
  for (const t of teams) counts[t] = (counts[t] ?? 0) + 1
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0]
}
