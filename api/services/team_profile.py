"""Team schedule and player totals for HTTP and assistant profile consumers."""
from database import query_to_dict
from services.schedule_records import attach_records
from sql_helpers import ROSTER_CTE
from services.receiving_coverage import mask_receiving_fields


_LEADER_COLS = """
        COUNT(DISTINCT pgs.game_id)   AS games_played,
        SUM(pgs.attempts)             AS attempts,
        SUM(pgs.completions)          AS completions,
        SUM(pgs.pass_yards)           AS pass_yards,
        SUM(pgs.pass_tds)             AS pass_tds,
        SUM(pgs.interceptions_thrown) AS interceptions_thrown,
        SUM(pgs.sacks_taken)          AS sacks_taken,
        SUM(pgs.pass_epa)             AS pass_epa,
        SUM(pgs.carries)              AS carries,
        SUM(pgs.rush_yards)           AS rush_yards,
        SUM(pgs.rush_tds)             AS rush_tds,
        SUM(pgs.rush_epa)             AS rush_epa,
        SUM(pgs.targets)              AS targets,
        SUM(pgs.receptions)           AS receptions,
        SUM(pgs.rec_yards)            AS rec_yards,
        SUM(pgs.rec_tds)              AS rec_tds,
        SUM(pgs.air_yards)            AS air_yards,
        SUM(pgs.yac)                  AS yac,
        SUM(pgs.rec_epa)              AS rec_epa,
        SUM(pgs.solo_tackles)         AS solo_tackles,
        SUM(pgs.assist_tackles)       AS assist_tackles,
        SUM(pgs.sacks)                AS sacks,
        SUM(pgs.tackles_for_loss)     AS tackles_for_loss,
        SUM(pgs.qb_hits)              AS qb_hits,
        SUM(pgs.def_interceptions)    AS def_interceptions,
        SUM(pgs.pass_breakups)        AS pass_breakups,
        SUM(pgs.forced_fumbles)       AS forced_fumbles,
        SUM(pgs.fumble_recoveries)    AS fumble_recoveries
"""


def get_team_profile(team: str, season: int) -> dict | None:
    games = query_to_dict(
        """
        SELECT
            game_id, season, game_type, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            stadium, roof, surface, temp, wind
        FROM schedules
        WHERE season = ? AND (away_team = ? OR home_team = ?)
        ORDER BY week
        """,
        [season, team, team],
    )
    if not games:
        return None

    attach_records(games)

    leaders = query_to_dict(
        f"""
        WITH {ROSTER_CTE}
        SELECT
            pgs.player_id,
            arg_max(pgs.player_name, length(pgs.player_name)) AS player_name,
            any_value(r.position)      AS position,
            any_value(r.headshot_url)  AS headshot_url,
            any_value(r.jersey_number) AS jersey_number,
            {_LEADER_COLS}
        FROM player_game_stats pgs
        LEFT JOIN roster r ON pgs.player_id = r.player_id AND r.season = pgs.season
        JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type = 'REG'
        WHERE pgs.season = ? AND pgs.team = ?
        GROUP BY pgs.player_id
        """,
        [season, team],
    )

    playoff_leaders = query_to_dict(
        f"""
        WITH {ROSTER_CTE}
        SELECT
            pgs.player_id,
            arg_max(pgs.player_name, length(pgs.player_name)) AS player_name,
            any_value(r.position)      AS position,
            any_value(r.headshot_url)  AS headshot_url,
            any_value(r.jersey_number) AS jersey_number,
            {_LEADER_COLS}
        FROM player_game_stats pgs
        LEFT JOIN roster r ON pgs.player_id = r.player_id AND r.season = pgs.season
        JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type != 'REG'
        WHERE pgs.season = ? AND pgs.team = ?
        GROUP BY pgs.player_id
        """,
        [season, team],
    )

    return {
        "team": team, "season": season, "games": games,
        "leaders": [mask_receiving_fields(row, season) for row in leaders],
        "playoff_leaders": [mask_receiving_fields(row, season) for row in playoff_leaders],
    }
