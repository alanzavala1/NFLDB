"""Response schemas for game ratings and power rankings."""
from pydantic import BaseModel


class GamePlayerRating(BaseModel):
    player_id: str
    player_name: str | None
    team: str | None
    position: str | None
    position_group: str
    rating: float | None
    raw_score: float | None
    plays_counted: int | None
    epa_total: float | None
    turnovers: float | None
    def_events_score: float | None
    fg_points: float | None


class PowerRankingRow(BaseModel):
    rank: int
    team: str
    record: str
    net_epa_play: float | None
    movement: int | None
