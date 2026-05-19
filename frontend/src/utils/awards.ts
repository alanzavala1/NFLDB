export type AwardKey = 'MVP' | 'OPOY' | 'DPOY' | 'OROY' | 'DROY' | 'CPOY' | 'COACH'

export interface AwardWinner { award: AwardKey; player: string; team: string; pos: string }

export const AWARD_ORDER: AwardKey[] = ['MVP', 'OPOY', 'DPOY', 'OROY', 'DROY', 'CPOY']

export const AWARD_LABEL: Record<AwardKey, string> = {
  MVP:   'MVP',
  OPOY:  'Offensive POY',
  DPOY:  'Defensive POY',
  OROY:  'Off. Rookie of the Year',
  DROY:  'Def. Rookie of the Year',
  CPOY:  'Comeback POY',
  COACH: 'Coach of the Year',
}

export const PAST_AWARDS: Record<number, AwardWinner[]> = {
  2024: [
    { award: 'MVP',  player: 'Josh Allen',         team: 'BUF', pos: 'QB'   },
    { award: 'OPOY', player: 'Saquon Barkley',     team: 'PHI', pos: 'RB'   },
    { award: 'DPOY', player: 'Patrick Surtain II', team: 'DEN', pos: 'CB'   },
    { award: 'OROY', player: 'Jayden Daniels',     team: 'WAS', pos: 'QB'   },
    { award: 'DROY', player: 'Jared Verse',        team: 'LAR', pos: 'EDGE' },
    { award: 'CPOY', player: 'Joe Burrow',         team: 'CIN', pos: 'QB'   },
  ],
  2023: [
    { award: 'MVP',  player: 'Lamar Jackson',         team: 'BAL', pos: 'QB'   },
    { award: 'OPOY', player: 'Christian McCaffrey',   team: 'SF',  pos: 'RB'   },
    { award: 'DPOY', player: 'Myles Garrett',         team: 'CLE', pos: 'DE'   },
    { award: 'OROY', player: 'C.J. Stroud',           team: 'HOU', pos: 'QB'   },
    { award: 'DROY', player: 'Will Anderson Jr.',     team: 'HOU', pos: 'EDGE' },
    { award: 'CPOY', player: 'Damar Hamlin',          team: 'BUF', pos: 'S'    },
  ],
  2022: [
    { award: 'MVP',  player: 'Patrick Mahomes',    team: 'KC',  pos: 'QB' },
    { award: 'OPOY', player: 'Justin Jefferson',   team: 'MIN', pos: 'WR' },
    { award: 'DPOY', player: 'Nick Bosa',          team: 'SF',  pos: 'DE' },
    { award: 'OROY', player: 'Garrett Wilson',     team: 'NYJ', pos: 'WR' },
    { award: 'DROY', player: 'Sauce Gardner',      team: 'NYJ', pos: 'CB' },
    { award: 'CPOY', player: 'Geno Smith',         team: 'SEA', pos: 'QB' },
  ],
  2021: [
    { award: 'MVP',  player: 'Aaron Rodgers',     team: 'GB',  pos: 'QB' },
    { award: 'OPOY', player: 'Cooper Kupp',       team: 'LAR', pos: 'WR' },
    { award: 'DPOY', player: 'T.J. Watt',         team: 'PIT', pos: 'LB' },
    { award: 'OROY', player: "Ja'Marr Chase",     team: 'CIN', pos: 'WR' },
    { award: 'DROY', player: 'Micah Parsons',     team: 'DAL', pos: 'LB' },
    { award: 'CPOY', player: 'Joe Burrow',        team: 'CIN', pos: 'QB' },
  ],
  2020: [
    { award: 'MVP',  player: 'Aaron Rodgers',  team: 'GB',  pos: 'QB' },
    { award: 'OPOY', player: 'Derrick Henry',  team: 'TEN', pos: 'RB' },
    { award: 'DPOY', player: 'Aaron Donald',   team: 'LAR', pos: 'DT' },
    { award: 'OROY', player: 'Justin Herbert', team: 'LAC', pos: 'QB' },
    { award: 'DROY', player: 'Chase Young',    team: 'WAS', pos: 'DE' },
    { award: 'CPOY', player: 'Alex Smith',     team: 'WAS', pos: 'QB' },
  ],
  2019: [
    { award: 'MVP',  player: 'Lamar Jackson',     team: 'BAL', pos: 'QB' },
    { award: 'OPOY', player: 'Michael Thomas',    team: 'NO',  pos: 'WR' },
    { award: 'DPOY', player: 'Stephon Gilmore',   team: 'NE',  pos: 'CB' },
    { award: 'OROY', player: 'Kyler Murray',     team: 'ARI', pos: 'QB' },
    { award: 'DROY', player: 'Nick Bosa',         team: 'SF',  pos: 'DE' },
    { award: 'CPOY', player: 'Ryan Tannehill',    team: 'TEN', pos: 'QB' },
  ],
}

// Super Bowl winners by SEASON (e.g. 2024 season → SB LIX in Feb 2025)
export const SB_CHAMPS: Record<number, { team: string; opponent: string; score: string }> = {
  2024: { team: 'PHI', opponent: 'KC',  score: '40-22' },
  2023: { team: 'KC',  opponent: 'SF',  score: '25-22' },
  2022: { team: 'KC',  opponent: 'PHI', score: '38-35' },
  2021: { team: 'LAR', opponent: 'CIN', score: '23-20' },
  2020: { team: 'TB',  opponent: 'KC',  score: '31-9'  },
  2019: { team: 'KC',  opponent: 'SF',  score: '31-20' },
}
