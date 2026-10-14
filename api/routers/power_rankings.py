"""Weekly EPA power rankings endpoint."""
from fastapi import APIRouter, Query

from config import CURRENT_SEASON
from schemas.ratings import PowerRankingRow
from services.power_rankings import get_power_rankings as query_power_rankings

router = APIRouter()


@router.get("/power-rankings", response_model=list[PowerRankingRow])
def get_power_rankings(
    season: int = Query(default=CURRENT_SEASON),
    week: int | None = Query(default=None, ge=1, le=22),
):
    return query_power_rankings(season, week)
