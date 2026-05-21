"""Response schemas for the teams router."""
from pydantic import BaseModel


class RosterPlayer(BaseModel):
    """A player on a team's roster for a given season."""
    player_id: str
    player_name: str
    position: str | None
    jersey_number: int | None
    headshot_url: str | None


class TeamGame(BaseModel):
    """A team's schedule row inside /teams/{team}. Records walked forward
    by attach_records() are required (always set on this endpoint)."""
    game_id: str
    season: int
    week: int
    gameday: str | None
    gametime: str | None
    away_team: str
    home_team: str
    away_score: int | None
    home_score: int | None
    stadium: str | None
    roof: str | None
    surface: str | None
    temp: int | None
    wind: int | None
    away_record: str | None
    home_record: str | None


class TeamLeader(BaseModel):
    """Per-player season totals for one team. Returned twice on /teams/{team}:
    once for regular season (leaders), once for playoffs (playoff_leaders)."""
    player_id: str
    player_name: str
    position: str | None
    jersey_number: int | None
    headshot_url: str | None
    games_played: int

    attempts: float
    completions: float
    pass_yards: float
    pass_tds: float
    interceptions_thrown: float
    sacks_taken: float
    pass_epa: float

    carries: float
    rush_yards: float
    rush_tds: float
    rush_epa: float

    targets: float
    receptions: float
    rec_yards: float
    rec_tds: float
    air_yards: float
    yac: float
    rec_epa: float

    solo_tackles: float
    assist_tackles: float
    tackles_for_loss: float
    sacks: float
    qb_hits: float
    def_interceptions: float
    pass_breakups: float
    forced_fumbles: float
    fumble_recoveries: float


class TeamProfile(BaseModel):
    """Response for /teams/{team}?season=…"""
    team: str
    season: int
    games: list[TeamGame]
    leaders: list[TeamLeader]
    playoff_leaders: list[TeamLeader]
