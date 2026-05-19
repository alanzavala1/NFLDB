"""App-wide constants and configuration."""
from datetime import datetime

FIRST_SEASON = 1999
AUTO_LOAD_SEASONS = 5  # auto-queue this many recent seasons on startup


def _current_nfl_season() -> int:
    now = datetime.now()
    return now.year if now.month >= 9 else now.year - 1


CURRENT_SEASON = _current_nfl_season()


TEAM_NAMES: dict[str, str] = {
    'ARI': 'Arizona Cardinals',    'ATL': 'Atlanta Falcons',
    'BAL': 'Baltimore Ravens',     'BUF': 'Buffalo Bills',
    'CAR': 'Carolina Panthers',    'CHI': 'Chicago Bears',
    'CIN': 'Cincinnati Bengals',   'CLE': 'Cleveland Browns',
    'DAL': 'Dallas Cowboys',       'DEN': 'Denver Broncos',
    'DET': 'Detroit Lions',        'GB':  'Green Bay Packers',
    'HOU': 'Houston Texans',       'IND': 'Indianapolis Colts',
    'JAX': 'Jacksonville Jaguars', 'KC':  'Kansas City Chiefs',
    'LAC': 'Los Angeles Chargers', 'LA':  'Los Angeles Rams',
    'LV':  'Las Vegas Raiders',    'MIA': 'Miami Dolphins',
    'MIN': 'Minnesota Vikings',    'NE':  'New England Patriots',
    'NO':  'New Orleans Saints',   'NYG': 'New York Giants',
    'NYJ': 'New York Jets',        'PHI': 'Philadelphia Eagles',
    'PIT': 'Pittsburgh Steelers',  'SEA': 'Seattle Seahawks',
    'SF':  'San Francisco 49ers',  'TB':  'Tampa Bay Buccaneers',
    'TEN': 'Tennessee Titans',     'WAS': 'Washington Commanders',
    'OAK': 'Oakland Raiders',      'SD':  'San Diego Chargers',
    'STL': 'St. Louis Rams',       'JAC': 'Jacksonville Jaguars',
}

DIVISIONS: dict[str, str] = {
    'BUF': 'AFC East',  'MIA': 'AFC East',  'NE':  'AFC East',  'NYJ': 'AFC East',
    'BAL': 'AFC North', 'CIN': 'AFC North', 'CLE': 'AFC North', 'PIT': 'AFC North',
    'HOU': 'AFC South', 'IND': 'AFC South', 'JAX': 'AFC South', 'TEN': 'AFC South',
    'DEN': 'AFC West',  'KC':  'AFC West',  'LAC': 'AFC West',  'LV':  'AFC West',
    'DAL': 'NFC East',  'NYG': 'NFC East',  'PHI': 'NFC East',  'WAS': 'NFC East',
    'CHI': 'NFC North', 'DET': 'NFC North', 'GB':  'NFC North', 'MIN': 'NFC North',
    'ATL': 'NFC South', 'CAR': 'NFC South', 'NO':  'NFC South', 'TB':  'NFC South',
    'ARI': 'NFC West',  'LA':  'NFC West',  'SEA': 'NFC West',  'SF':  'NFC West',
    'OAK': 'AFC West',  'SD':  'AFC West',  'STL': 'NFC West',  'JAC': 'AFC South',
}
