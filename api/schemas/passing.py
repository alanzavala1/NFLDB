"""Prepared passing summaries; components permit exact cross-row aggregation."""
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict

from schemas.players import PlayerSplit
from schemas.receiving import ReceivingGameCoverage


class PassingAggregation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, strict=True)
    epa_sum: float | None = Field(description="Verified QB EPA including sacks; not rate times attempts.")
    successes: int | None = Field(ge=0, description="Verified positive-EPA passing attempts.")
    cpoe_sum: float | None
    cpoe_count: int | None = Field(ge=0, description="Number of provider-modeled CPOE observations.")


class PassingRow(PlayerSplit):
    unavailable_metrics: dict[str, str]
    aggregation: PassingAggregation


class PassingCounts(BaseModel):
    att: int
    cmp: int
    yards: int
    td: int
    interceptions: int
    first_downs: int
    sacks: int


class PassingViewCoverage(BaseModel):
    status: Literal["complete", "partial", "unavailable"]
    reason: str | None
    definition: str
    excluded: PassingCounts = Field(description="Only this passer's production outside the classified view.")


class PassingSeason(BaseModel):
    season: int
    status: Literal["prepared", "unverified"]
    reason: str | None
    overall: PassingRow | None
    rows: list[PassingRow]
    game_coverage: ReceivingGameCoverage | None
    views: dict[str, PassingViewCoverage]


class PlayerPassingSplits(BaseModel):
    player_id: str
    scope: Literal["Qualified regular-season passing; observed production on supplied games"]
    seasons: list[PassingSeason]
