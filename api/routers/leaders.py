"""Season-level league endpoints: leaders, WPA leaders, standings, search."""

from fastapi import APIRouter, Query

from schemas.leaders import LeagueLeader, WpaLeaders
from schemas.schedule import SearchResult
from schemas.standings import DivisionStandings
from services.leaders import get_leaders as query_leaders
from services.search import search as query_search
from services.standings import get_standings as query_standings
from services.wpa_leaders import get_wpa_leaders as query_wpa_leaders

router = APIRouter()


@router.get("/leaders", response_model=list[LeagueLeader])
def get_leaders(season: int = Query(default=None)):
    return query_leaders(season)


@router.get("/wpa-leaders", response_model=WpaLeaders)
def get_wpa_leaders(season: int = Query(default=None)):
    return query_wpa_leaders(season)


@router.get("/standings", response_model=list[DivisionStandings])
def get_standings(season: int = Query(default=None)):
    return query_standings(season)


@router.get("/search", response_model=list[SearchResult])
def search(q: str = Query(..., min_length=1)):
    return query_search(q)
