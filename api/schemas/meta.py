"""Response schemas for the meta router (health, seasons)."""
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


SeasonState = Literal["loaded", "queued", "loading", "error", "available"]


class SeasonStatus(BaseModel):
    season: int
    status: SeasonState


class LoadSeasonResponse(BaseModel):
    season: int
    status: SeasonState
