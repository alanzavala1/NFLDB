"""Schedule and game endpoints."""
from fastapi import APIRouter, HTTPException, Query

from config import CURRENT_SEASON
from schemas.lineup import GameLineup, PlayerChart
from schemas.ratings import GamePlayerRating
from schemas.schedule import Game, GameDetail, ScheduleWeek
from services.schedule import get_games as query_games, get_schedule as query_schedule
from services.game_detail import get_game_detail as query_game_detail
from services.game_ratings import get_game_ratings as query_game_ratings
from services.game_lineup import get_game_lineup as query_game_lineup
from services.game_player_chart import (
    GameNotFoundError,
    PlayerNotFoundError,
    get_game_player_chart as query_player_chart,
)

router = APIRouter()


@router.get("/schedule", response_model=list[ScheduleWeek])
def get_schedule(season: int = Query(default=CURRENT_SEASON)):
    return query_schedule(season)


@router.get("/games", response_model=list[Game])
def get_games(
    week: int = Query(..., ge=1, le=22),
    season: int = Query(default=CURRENT_SEASON),
):
    rows = query_games(week, season)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No games found for week {week}, season {season}")
    return rows


@router.get("/games/{game_id}", response_model=GameDetail)
def get_game(game_id: str):
    game = query_game_detail(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return game


@router.get("/games/{game_id}/ratings", response_model=list[GamePlayerRating])
def get_game_ratings(game_id: str):
    ratings = query_game_ratings(game_id)
    if ratings is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return ratings


@router.get("/games/{game_id}/lineup", response_model=GameLineup)
def get_game_lineup(game_id: str):
    lineup = query_game_lineup(game_id)
    if lineup is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return lineup


@router.get("/games/{game_id}/players/{player_id}/chart", response_model=PlayerChart)
def get_game_player_chart(game_id: str, player_id: str):
    try:
        return query_player_chart(game_id, player_id)
    except GameNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found") from exc
    except PlayerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found for game {game_id}") from exc
