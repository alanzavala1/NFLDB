"""Game rating availability and response assembly."""
import game_ratings_builder
from database import query_to_dict
from sql_helpers import PGS_GAME_CTE


def get_game_ratings(game_id: str) -> list[dict] | None:
    game = query_to_dict(
        "SELECT game_id FROM schedules WHERE game_id = ?",
        [game_id],
    )
    if not game:
        return None

    rows = game_ratings_builder.read_or_materialize(game_id)
    if not rows:
        return []

    return query_to_dict(
        f"""
        WITH {PGS_GAME_CTE},
        roster AS (
            SELECT player_id, season, position, player_name
            FROM rosters
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY player_id, season
                ORDER BY week DESC NULLS LAST, team
            ) = 1
        )
        SELECT
            r.player_id,
            COALESCE(pgs.player_name, ros.player_name) AS player_name,
            r.team,
            ros.position,
            r.position_group,
            r.rating,
            r.raw_score,
            r.plays_counted,
            r.epa_total,
            r.turnovers,
            r.def_events_score,
            r.fg_points
        FROM player_game_ratings r
        LEFT JOIN pgs_game pgs
          ON pgs.game_id = r.game_id AND pgs.player_id = r.player_id
        LEFT JOIN roster ros
          ON ros.player_id = r.player_id AND ros.season = r.season
        WHERE r.game_id = ?
        ORDER BY r.rating DESC NULLS LAST, r.raw_score DESC NULLS LAST, player_name
        """,
        [game_id, game_id],
    )
