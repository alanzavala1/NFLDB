"""Player data functions; HTTP-independent selection and assembly."""
from sql_helpers import safe_query


def _get_ngs(player_id: str, cpoe_fallback: dict | None = None) -> dict:
    """Aggregate NGS weekly data by season for a player.

    `cpoe_fallback` is {season: cpoe} derived from play-by-play (see
    _get_pbp_stats). NGS tracking starts at 2016 — without the fallback,
    pre-2016 QBs (Favre, Romo, Brees through 2015, etc.) would have an empty
    cell where every other QB has a value. The NGS value wins when present
    (tracking-based, more authoritative); plays-derived only fills the gaps.
    """
    result: dict[int, dict] = {}

    for row in safe_query("""
        SELECT season,
            ROUND(AVG(avg_time_to_throw), 2)                         AS avg_time_to_throw,
            ROUND(AVG(avg_intended_air_yards), 1)                     AS adot,
            ROUND(AVG(avg_completed_air_yards), 1)                    AS avg_completed_air_yards,
            ROUND(AVG(completion_percentage_above_expectation), 1)    AS cpoe,
            ROUND(AVG(aggressiveness), 1)                             AS aggressiveness,
            ROUND(AVG(expected_completion_percentage), 1)             AS expected_cmp_pct,
            ROUND(AVG(passer_rating), 1)                              AS ngs_passer_rating
        FROM ngs_passing
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    for row in safe_query("""
        SELECT season,
            ROUND(SUM(rush_yards_over_expected), 1)                   AS rush_yoe,
            ROUND(AVG(rush_yards_over_expected_per_att), 2)           AS rush_yoe_per_att,
            ROUND(AVG(efficiency), 1)                                 AS rush_efficiency,
            ROUND(AVG(avg_time_to_los), 2)                            AS avg_time_to_los,
            ROUND(AVG(percent_attempts_gte_eight_defenders), 1)       AS pct_vs_8_defenders
        FROM ngs_rushing
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    for row in safe_query("""
        SELECT season,
            ROUND(AVG(avg_separation), 2)                             AS avg_separation,
            ROUND(AVG(avg_cushion), 2)                                AS avg_cushion,
            ROUND(AVG(avg_intended_air_yards), 1)                     AS avg_target_depth,
            ROUND(AVG(avg_yac), 2)                                    AS avg_yac,
            ROUND(AVG(avg_yac_above_expectation), 2)                  AS avg_yac_above_exp,
            ROUND(AVG(catch_percentage), 1)                           AS catch_pct,
            ROUND(AVG(percent_share_of_intended_air_yards), 1)        AS air_yards_share
        FROM ngs_receiving
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    for s, cpoe in (cpoe_fallback or {}).items():
        d = result.setdefault(s, {})
        if d.get("cpoe") is None:
            d["cpoe"] = cpoe

    return result
