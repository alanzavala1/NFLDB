"""Coverage-aware receiving contract, additive to the existing split list."""
from typing import Literal

from pydantic import BaseModel, Field

from schemas.players import PlayerSplit


class ReceivingRow(PlayerSplit):
    """EPA per original target; success is percent of targets with EPA > 0."""
    unavailable_metrics: dict[str, str]


class ReceivingCounts(BaseModel):
    att: int | None
    cmp: int
    yards: int
    td: int
    yac: int | None
    first_downs: int


class ReceivingViewCoverage(BaseModel):
    status: Literal["complete", "partial", "unavailable"] = Field(
        description="Context coverage of all supplied season plays, not just this receiver.")
    reason: str | None
    definition: str
    excluded: ReceivingCounts = Field(description="Only this receiver's verified production outside the view.")


class ReceivingGameCoverage(BaseModel):
    """Supplied games versus recorded final scores; not a source freshness certificate."""
    status: Literal["complete", "partial"]
    supplied_games: int
    recorded_completed_games: int
    missing_game_ids: list[str]
    unconfirmed_game_ids: list[str]
    reason: str | None


class ReceivingSeason(BaseModel):
    season: int
    status: Literal["prepared", "unverified"]
    reason: str | None
    overall: ReceivingRow | None
    rows: list[ReceivingRow]
    game_coverage: ReceivingGameCoverage | None
    views: dict[str, ReceivingViewCoverage]


class PlayerReceivingSplits(BaseModel):
    player_id: str
    scope: Literal["Qualified regular-season receiving; observed production on supplied games"]
    seasons: list[ReceivingSeason]
