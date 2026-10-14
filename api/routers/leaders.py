"""Season-level league endpoints: leaders, WPA leaders, standings, search."""

from fastapi import APIRouter, Query

from config import CURRENT_SEASON
from database import query_to_dict
from schemas.leaders import LeagueLeader, WpaLeaders
from schemas.schedule import SearchResult
from schemas.standings import DivisionStandings
from services.search import search as query_search
from services.standings import get_standings as query_standings
from sql_helpers import ROSTER_CTE, safe_query

router = APIRouter()


@router.get("/leaders", response_model=list[LeagueLeader])
def get_leaders(season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON
    rows = query_to_dict(
        f"""
        WITH {ROSTER_CTE},
        stats AS (
            SELECT
                pgs.player_id,
                MAX(pgs.player_name)              AS player_name,
                COUNT(DISTINCT pgs.game_id)       AS games_played,
                SUM(pgs.attempts)                 AS attempts,
                SUM(pgs.completions)              AS completions,
                SUM(pgs.pass_yards)               AS pass_yards,
                SUM(pgs.pass_tds)                 AS pass_tds,
                SUM(pgs.interceptions_thrown)     AS interceptions_thrown,
                SUM(pgs.sacks_taken)              AS sacks_taken,
                SUM(pgs.carries)                  AS carries,
                SUM(pgs.rush_yards)               AS rush_yards,
                SUM(pgs.rush_tds)                 AS rush_tds,
                SUM(pgs.targets)                  AS targets,
                SUM(pgs.receptions)               AS receptions,
                SUM(pgs.rec_yards)                AS rec_yards,
                SUM(pgs.rec_tds)                  AS rec_tds,
                SUM(pgs.yac)                      AS yac,
                SUM(pgs.pass_epa)                 AS pass_epa,
                SUM(pgs.rush_epa)                 AS rush_epa,
                SUM(pgs.rec_epa)                  AS rec_epa,
                SUM(pgs.air_yards)                AS air_yards,
                SUM(pgs.solo_tackles)             AS solo_tackles,
                SUM(pgs.assist_tackles)           AS assist_tackles,
                SUM(pgs.tackles_for_loss)         AS tackles_for_loss,
                SUM(pgs.sacks)                    AS sacks,
                SUM(pgs.qb_hits)                  AS qb_hits,
                SUM(pgs.def_interceptions)        AS def_interceptions,
                SUM(pgs.pass_breakups)            AS pass_breakups,
                SUM(pgs.forced_fumbles)           AS forced_fumbles,
                SUM(pgs.fumble_recoveries)        AS fumble_recoveries,
                SUM(pgs.fg_att)                   AS fg_att,
                SUM(pgs.fg_made)                  AS fg_made,
                SUM(pgs.xp_att)                   AS xp_att,
                SUM(pgs.xp_made)                  AS xp_made,
                SUM(pgs.punts)                    AS punts,
                SUM(pgs.punt_yards)               AS punt_yards
            FROM player_game_stats pgs
            JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type = 'REG'
            WHERE pgs.season = ?
            GROUP BY pgs.player_id
        )
        SELECT s.*, r.position, r.team, r.headshot_url
        FROM stats s
        LEFT JOIN roster r ON r.player_id = s.player_id AND r.season = ?
        """,
        [season, season],
    )
    return rows


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
