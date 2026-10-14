"""Passing, rushing and receiving WPA leaders from regular-season plays."""
from config import CURRENT_SEASON
from sql_helpers import ROSTER_CTE, safe_query


def get_wpa_leaders(season: int | None = None) -> dict[str, list[dict]]:
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
