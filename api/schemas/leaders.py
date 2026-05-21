"""Response schemas for /leaders, /wpa-leaders, /players/{id}/comparables."""
from pydantic import BaseModel


class LeagueLeader(BaseModel):
    """One row per player in /leaders. Stat fields are season totals from
    SUM() over player_game_stats, returned as DOUBLE.

    All stat fields are required-and-non-null: the underlying columns have
    DEFAULT 0, so SUM(...) is always a number (0.0 for non-applicable
    stats like RB pass_yards). Roster-joined fields (position/team) may be
    null because the join is LEFT and roster data can be missing.
    """
    player_id: str
    player_name: str
    position: str | None
    team: str | None
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
    yac: float
    air_yards: float
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

    fg_att: float
    fg_made: float
    xp_att: float
    xp_made: float
    punts: float
    punt_yards: float


class WpaLeader(BaseModel):
    """One row in passing/rushing/receiving WPA leaders.

    The volume column (attempts/carries/receptions) varies per sub-list.
    Only one is populated per row — the others are simply absent from
    the SQL projection, so they remain optional + None.
    """
    player_id: str
    player_name: str
    position: str | None
    team: str | None
    headshot_url: str | None
    wpa: float
    games_played: int

    # Volume column — exactly one of these is set per row by the SQL
    attempts:   int | None = None  # passing
    carries:    int | None = None  # rushing
    receptions: int | None = None  # receiving


class WpaLeaders(BaseModel):
    """The full /wpa-leaders payload: three sub-lists."""
    passing:   list[WpaLeader]
    rushing:   list[WpaLeader]
    receiving: list[WpaLeader]


class PlayerComparable(BaseModel):
    """Cosine-similarity neighbor returned by /players/{id}/comparables."""
    player_id: str
    player_name: str
    position: str | None
    team: str | None
    headshot_url: str | None
    similarity: float
    games: int
    first_season: int
    last_season: int

    # Career totals (raw, not per-game)
    pass_yards: float
    pass_tds: float
    rush_yards: float
    rush_tds: float
    carries: float
    rec_yards: float
    rec_tds: float
    targets: float
    att: float
    cmp: float
    ints: float
