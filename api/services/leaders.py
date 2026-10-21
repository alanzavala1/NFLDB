"""Regular-season player totals shared by HTTP and assistant consumers."""
from config import CURRENT_SEASON
from database import query_to_dict
from sql_helpers import ROSTER_CTE
from services.receiving_coverage import mask_target_fields


def get_leaders(season: int | None = None) -> list[dict]:
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
    return [mask_target_fields(row, season) for row in rows]
