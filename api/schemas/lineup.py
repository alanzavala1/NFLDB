"""Response schemas for game lineup and player chart endpoints."""
from typing import Literal

from pydantic import BaseModel


class LineupPlayer(BaseModel):
    player_id: str | None
    pfr_player_id: str | None
    player_name: str
    team: str
    position: str | None
    position_group: str | None
    jersey_number: int | None
    headshot_url: str | None
    rating: float | None
    raw_score: float | None
    snaps: int
    snap_pct: float | None
    scored_td: bool = False


class LineupTeam(BaseModel):
    team: str
    side: Literal["away", "home"]
    avg_rating: float | None
    offense_personnel: str | None
    defense_personnel: str | None
    offense: list[LineupPlayer]
    defense: list[LineupPlayer]
    rotation: list[LineupPlayer]


class LineupScoringEvent(BaseModel):
    team: str | None
    player_id: str | None
    player_name: str | None
    kind: str
    qtr: int | None
    clock: str | None
    distance: int | None
    desc: str | None


class GameLineup(BaseModel):
    game_id: str
    season: int
    week: int
    away_team: str
    home_team: str
    join_match_rate: float | None
    scoring: list[LineupScoringEvent]
    teams: list[LineupTeam]


class PlayerChartEvent(BaseModel):
    play_id: float | None
    qtr: int | None
    clock: str | None
    role: str
    lane: str | None
    air_yards: float | None
    yards: float | None
    epa: float | None
    outcome: str
    desc: str | None


class PlayerChart(BaseModel):
    game_id: str
    player_id: str
    player_name: str | None
    team: str | None
    position: str | None
    role: str
    rating: float | None
    snap_pct: float | None
    stats: dict[str, float | int | str | None]
    events: list[PlayerChartEvent]
