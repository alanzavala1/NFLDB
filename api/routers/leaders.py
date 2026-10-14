"""Season-level league endpoints: leaders, WPA leaders, standings, search."""

from fastapi import APIRouter, Query

from config import CURRENT_SEASON
from schemas.leaders import LeagueLeader, WpaLeaders
from schemas.schedule import SearchResult
from schemas.standings import DivisionStandings
from services.leaders import get_leaders as query_leaders
from services.search import search as query_search
from services.standings import get_standings as query_standings
from sql_helpers import ROSTER_CTE, safe_query

router = APIRouter()


@router.get("/leaders", response_model=list[LeagueLeader])
def get_leaders(season: int = Query(default=None)):
    return query_leaders(season)


@router.get("/wpa-leaders", response_model=WpaLeaders)
def get_wpa_leaders(season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON

    passing = safe_query(f"""
        WITH {ROSTER_CTE},
        stats AS (
            SELECT passer_player_id AS player_id,
                   MAX(passer_player_name) AS player_name,
                   ROUND(SUM(COALESCE(air_wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) FILTER (WHERE pass_attempt = 1) AS attempts
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND pass_attempt = 1 AND passer_player_id IS NOT NULL
            GROUP BY passer_player_id
            HAVING COUNT(*) FILTER (WHERE pass_attempt = 1) >= 50
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.attempts
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    rushing = safe_query(f"""
        WITH {ROSTER_CTE},
        stats AS (
            SELECT rusher_player_id AS player_id,
                   MAX(rusher_player_name) AS player_name,
                   ROUND(SUM(COALESCE(wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) AS carries
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND rush_attempt = 1 AND rusher_player_id IS NOT NULL
            GROUP BY rusher_player_id
            HAVING COUNT(*) >= 50
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.carries
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    receiving = safe_query(f"""
        WITH {ROSTER_CTE},
        stats AS (
            SELECT receiver_player_id AS player_id,
                   MAX(receiver_player_name) AS player_name,
                   ROUND(SUM(COALESCE(yac_wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) FILTER (WHERE complete_pass = 1) AS receptions
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND complete_pass = 1 AND receiver_player_id IS NOT NULL
            GROUP BY receiver_player_id
            HAVING COUNT(*) FILTER (WHERE complete_pass = 1) >= 20
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.receptions
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    return {"passing": passing, "rushing": rushing, "receiving": receiving}


@router.get("/standings", response_model=list[DivisionStandings])
def get_standings(season: int = Query(default=None)):
    return query_standings(season)


@router.get("/search", response_model=list[SearchResult])
def search(q: str = Query(..., min_length=1)):
    return query_search(q)
