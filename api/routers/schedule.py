"""Schedule and game endpoints."""
from fastapi import APIRouter, HTTPException, Query

from config import CURRENT_SEASON
from database import query_to_dict
import game_ratings_builder
from schemas.lineup import GameLineup, PlayerChart
from schemas.ratings import GamePlayerRating
from schemas.schedule import Game, GameDetail, ScheduleWeek
from services.schedule import get_games as query_games, get_schedule as query_schedule
from services.game_detail import get_game_detail as query_game_detail
from services.game_ratings import get_game_ratings as query_game_ratings
from services.game_lineup import get_game_lineup as query_game_lineup
from services.game_players import position_group as _position_group
from sql_helpers import PGS_GAME_CTE, safe_query

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
    game = query_to_dict(
        "SELECT game_id, season, away_team, home_team FROM schedules WHERE game_id = ?",
        [game_id],
    )
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    game = game[0]

    game_ratings_builder.read_or_materialize(game_id)

    profile = query_to_dict(
        f"""
        WITH {PGS_GAME_CTE}
        SELECT
            COALESCE(pgs.player_name, r.player_name) AS player_name,
            COALESCE(pgs.team, r.team) AS team,
            r.position,
            gr.rating,
            pgs.attempts, pgs.completions, pgs.pass_yards, pgs.pass_tds,
            pgs.interceptions_thrown, pgs.sacks_taken, pgs.pass_epa,
            pgs.targets, pgs.receptions, pgs.rec_yards, pgs.rec_tds,
            pgs.air_yards, pgs.yac, pgs.rec_epa,
            pgs.carries, pgs.rush_yards, pgs.rush_tds, pgs.rush_epa,
            pgs.solo_tackles, pgs.assist_tackles, pgs.tackles_for_loss,
            pgs.sacks, pgs.qb_hits, pgs.def_interceptions, pgs.pass_breakups,
            pgs.forced_fumbles, pgs.fumble_recoveries
        FROM (
            SELECT *
            FROM rosters
            WHERE player_id = ? AND season = ?
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY player_id, season
                ORDER BY week DESC NULLS LAST, team
            ) = 1
        ) r
        FULL OUTER JOIN pgs_game pgs
          ON pgs.player_id = r.player_id
        LEFT JOIN player_game_ratings gr
          ON gr.player_id = COALESCE(pgs.player_id, r.player_id)
         AND gr.game_id = ?
        WHERE COALESCE(pgs.player_id, r.player_id) = ?
        """,
        [game_id, player_id, game["season"], game_id, player_id],
    )
    if not profile:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found for game {game_id}")
    p = profile[0]

    counts = query_to_dict(
        """
        SELECT
            COUNT(*) FILTER (WHERE passer_player_id = ?) AS pass_plays,
            COUNT(*) FILTER (WHERE receiver_player_id = ?) AS target_plays,
            COUNT(*) FILTER (WHERE rusher_player_id = ?) AS rush_plays
        FROM plays
        WHERE game_id = ?
        """,
        [player_id, player_id, player_id, game_id],
    )[0]
    role_counts = (("passer", counts["pass_plays"] or 0), ("receiver", counts["target_plays"] or 0), ("rusher", counts["rush_plays"] or 0))
    role, role_count = max(role_counts, key=lambda item: item[1])
    if role_count == 0:
        position_group = _position_group(p.get("position"))
        role = "defender" if position_group == "DEF" else "kicker" if position_group == "K" else "player"

    events = query_to_dict(
        """
        SELECT
            play_id,
            CAST(qtr AS INTEGER) AS qtr,
            "time" AS clock,
            CASE WHEN passer_player_id = ? THEN 'passer'
                 WHEN receiver_player_id = ? THEN 'receiver'
                 ELSE 'rusher' END AS role,
            CASE WHEN rusher_player_id = ?
                    THEN TRIM(COALESCE(run_location, '') || ' ' || COALESCE(run_gap, ''))
                 ELSE pass_location END AS lane,
            air_yards,
            CASE WHEN rusher_player_id = ? THEN rushing_yards
                 WHEN receiver_player_id = ? THEN receiving_yards
                 ELSE passing_yards END AS yards,
            epa,
            CASE
                 WHEN receiver_player_id = ? AND COALESCE(touchdown, 0) = 1 THEN 'TD'
                 WHEN receiver_player_id = ? AND COALESCE(interception, 0) = 1 THEN 'INT'
                 WHEN receiver_player_id = ? AND COALESCE(complete_pass, 0) = 1 THEN 'Complete'
                 WHEN receiver_player_id = ? THEN 'Incomplete'
                 WHEN passer_player_id = ? AND COALESCE(touchdown, 0) = 1 THEN 'TD'
                 WHEN passer_player_id = ? AND COALESCE(interception, 0) = 1 THEN 'INT'
                 WHEN passer_player_id = ? AND COALESCE(fumble_lost, 0) = 1 THEN 'FUM'
                 WHEN passer_player_id = ? AND COALESCE(complete_pass, 0) = 1 THEN 'Complete'
                 WHEN passer_player_id = ? THEN 'Incomplete'
                 WHEN rusher_player_id = ? AND COALESCE(touchdown, 0) = 1 THEN 'TD'
                 WHEN rusher_player_id = ? AND COALESCE(fumble_lost, 0) = 1 THEN 'FUM'
                 WHEN rusher_player_id = ? THEN 'Run'
                 ELSE 'Play' END AS outcome,
            "desc" AS desc
        FROM plays
        WHERE game_id = ?
          AND (passer_player_id = ? OR receiver_player_id = ? OR rusher_player_id = ?)
        ORDER BY game_seconds_remaining DESC NULLS LAST, play_id
        LIMIT 80
        """,
        [
            player_id, player_id, player_id, player_id, player_id,
            player_id, player_id, player_id, player_id, player_id,
            player_id, player_id, player_id, player_id, player_id,
            player_id, player_id, game_id, player_id, player_id, player_id,
        ],
    )

    snap_rows = safe_query(
        """
        SELECT
            GREATEST(COALESCE(sc.offense_pct, 0), COALESCE(sc.defense_pct, 0), COALESCE(sc.st_pct, 0)) AS snap_pct
        FROM rosters r
        JOIN snap_counts sc
          ON sc.season = r.season
         AND sc.pfr_player_id = r.pfr_id
        WHERE r.player_id = ?
          AND sc.game_id = ?
        ORDER BY CASE WHEN r.team = sc.team THEN 0 ELSE 1 END, r.week DESC NULLS LAST
        LIMIT 1
        """,
        [player_id, game_id],
    )
    snap_pct = snap_rows[0]["snap_pct"] if snap_rows else None

    stats = {
        "attempts": p.get("attempts") or 0,
        "completions": p.get("completions") or 0,
        "pass_yards": p.get("pass_yards") or 0,
        "pass_tds": p.get("pass_tds") or 0,
        "interceptions_thrown": p.get("interceptions_thrown") or 0,
        "targets": p.get("targets") or 0,
        "receptions": p.get("receptions") or 0,
        "rec_yards": p.get("rec_yards") or 0,
        "rec_tds": p.get("rec_tds") or 0,
        "carries": p.get("carries") or 0,
        "rush_yards": p.get("rush_yards") or 0,
        "rush_tds": p.get("rush_tds") or 0,
        "pass_epa": p.get("pass_epa") or 0,
        "rec_epa": p.get("rec_epa") or 0,
        "rush_epa": p.get("rush_epa") or 0,
        "sacks": p.get("sacks") or 0,
        "tackles": (p.get("solo_tackles") or 0) + (p.get("assist_tackles") or 0),
        "def_interceptions": p.get("def_interceptions") or 0,
    }
    return {
        "game_id": game_id,
        "player_id": player_id,
        "player_name": p.get("player_name"),
        "team": p.get("team"),
        "position": p.get("position"),
        "role": role,
        "rating": p.get("rating"),
        "snap_pct": snap_pct,
        "stats": stats,
        "events": events,
    }
