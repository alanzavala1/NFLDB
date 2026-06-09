"""Response schemas for /schedule, /games, /games/{id}.

Convention: fields the SQL always SELECTs are required-but-nullable
(`T | None` with no default). Fields that are conditionally attached
(like records walked forward by attach_records()) carry a `= None`
default so they can be absent.
"""
from typing import Literal

from pydantic import BaseModel


class Game(BaseModel):
    """A scheduled game; scores are null for unplayed games."""
    game_id: str
    season: int
    game_type: str
    week: int
    gameday: str | None
    gametime: str | None
    away_team: str
    home_team: str
    away_score: int | None
    home_score: int | None
    away_qb_name: str | None
    home_qb_name: str | None
    spread_line: float | None
    total_line: float | None
    roof: str | None
    surface: str | None
    temp: int | None
    wind: int | None
    stadium: str | None
    overtime: int | None
    div_game: int | None
    # attach_records populates these on /schedule and /games/{id}; absent on /games
    away_record: str | None = None
    home_record: str | None = None


class ScheduleWeek(BaseModel):
    """A week of games returned by /schedule."""
    week: int
    games: list[Game]


class GamePlayerStats(BaseModel):
    """Per-game player line returned in /games/{id} under away[] / home[].

    Stat columns come back as DOUBLE from DuckDB (DEFAULT 0), so they are
    floats even when conceptually counts (touchdowns, attempts, etc.).
    """
    player_id: str
    player_name: str
    team: str
    week: int
    position: str | None
    jersey_number: int | None
    headshot_url: str | None

    # All STAT_COLS, mirroring sql_helpers.STAT_COLS exactly. Always present
    # in the response (player_game_stats columns have DEFAULT 0 in the schema).
    attempts: float
    completions: float
    pass_yards: float
    pass_tds: float
    interceptions_thrown: float
    sacks_taken: float
    pass_epa: float

    targets: float
    receptions: float
    rec_yards: float
    rec_tds: float
    air_yards: float
    yac: float
    rec_epa: float

    carries: float
    rush_yards: float
    rush_tds: float
    rush_epa: float

    solo_tackles: float
    assist_tackles: float
    tackles_for_loss: float
    sacks: float
    qb_hits: float
    def_interceptions: float
    pass_breakups: float
    forced_fumbles: float
    fumble_recoveries: float

    fg_att: float
    fg_made: float
    xp_att: float
    xp_made: float

    punts: float
    punt_yards: float

    punt_returns: float
    punt_return_yards: float
    punt_return_tds: float


class QuarterScore(BaseModel):
    qtr: int
    away: int
    home: int


class WinProbPlay(BaseModel):
    game_seconds_remaining: int
    qtr: int
    home_wp: float
    touchdown: int
    interception: int
    fumble_lost: int
    posteam: str | None
    desc: str | None


class TeamGameStats(BaseModel):
    """Team-level box-score line for one game, computed from play-by-play."""
    team: str
    plays: int
    first_downs: int
    third_att: int
    third_conv: int
    fourth_att: int
    fourth_conv: int
    penalties: int
    penalty_yards: int
    turnovers: int
    epa_play: float | None
    success_pct: float | None


class ScoringPlay(BaseModel):
    qtr: int
    clock: str | None       # game clock, e.g. "02:52"
    team: str | None        # scoring team (posteam on the play)
    kind: str               # 'TD' | 'FG' | 'SAF' | 'SCORE'
    desc: str | None
    away_score: int
    home_score: int


class GameDetail(Game):
    """Game detail returned by /games/{id}: game header + rosters + scoring + WP."""
    away: list[GamePlayerStats]
    home: list[GamePlayerStats]
    quarter_scores: list[QuarterScore]
    win_prob: list[WinProbPlay]
    team_stats: list[TeamGameStats]
    scoring: list[ScoringPlay]


SearchResultType = Literal["player", "team"]


class SearchResult(BaseModel):
    """A single search hit. `type` discriminates player vs team."""
    type: SearchResultType
    id: str
    name: str
    position: str | None
    team: str | None
    headshot_url: str | None
