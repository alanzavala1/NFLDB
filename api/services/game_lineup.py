"""Snap-based game lineups, scoring events and team averages."""
import ol_grades_builder
from config import era_team_case
from database import query_to_dict
from services.game_players import (
    offense_personnel as _personnel_off,
    defense_personnel as _personnel_def,
    lineup_players as _lineup_players,
    rotation_players as _rotation_players,
)
from sql_helpers import PGS_GAME_CTE, safe_query


def get_game_lineup(game_id: str) -> dict | None:
    games = query_to_dict(
        """
        SELECT game_id, season, week, away_team, home_team, away_coach, home_coach
        FROM schedules
        WHERE game_id = ?
        """,
        [game_id],
    )
    if not games:
        return None
    game = games[0]

    team_expr = era_team_case("sc.team", "sc.season")
    snap_rows = query_to_dict(
        f"""
        WITH game AS (
            SELECT season, away_team, home_team
            FROM schedules
            WHERE game_id = ?
        ),
        snap_base AS (
            SELECT
                sc.*,
                {team_expr} AS era_team,
                LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(sc.player, '\\\\b(jr|sr|ii|iii|iv|v)\\\\b', '', 'gi'), '[^a-zA-Z0-9 ]', '', 'g'))) AS snap_name_key,
                CASE
                    WHEN UPPER(sc.position) IN ('G','T','C','OL','LT','LG','RG','RT') THEN 'OL'
                    WHEN UPPER(sc.position) IN ('DT','DE','DL','NT','EDGE') THEN 'DL'
                    WHEN UPPER(sc.position) IN ('CB','DB','FS','SS','S','NB') THEN 'DB'
                    WHEN UPPER(sc.position) IN ('LB','ILB','OLB','MLB') THEN 'LB'
                    WHEN UPPER(sc.position) IN ('RB','FB','HB') THEN 'RB'
                    ELSE UPPER(sc.position)
                END AS snap_pos_key
            FROM snap_counts sc
            JOIN game ON game.season = sc.season
            WHERE sc.game_id = ?
              AND {team_expr} IN (game.away_team, game.home_team)
        ),
        roster_season AS (
            SELECT
                r.*,
                LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(r.player_name, '\\\\b(jr|sr|ii|iii|iv|v)\\\\b', '', 'gi'), '[^a-zA-Z0-9 ]', '', 'g'))) AS roster_name_key,
                LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(COALESCE(r.football_name, r.player_name), '\\\\b(jr|sr|ii|iii|iv|v)\\\\b', '', 'gi'), '[^a-zA-Z0-9 ]', '', 'g'))) AS football_name_key,
                CASE
                    WHEN UPPER(r.position) IN ('G','T','C','OL','LT','LG','RG','RT') THEN 'OL'
                    WHEN UPPER(r.position) IN ('DT','DE','DL','NT','EDGE') THEN 'DL'
                    WHEN UPPER(r.position) IN ('CB','DB','FS','SS','S','NB') THEN 'DB'
                    WHEN UPPER(r.position) IN ('LB','ILB','OLB','MLB') THEN 'LB'
                    WHEN UPPER(r.position) IN ('RB','FB','HB') THEN 'RB'
                    ELSE UPPER(r.position)
                END AS roster_pos_key
            FROM rosters r
            JOIN game ON game.season = r.season
        ),
        pfr_match AS (
            SELECT *
            FROM (
                SELECT
                    sb.pfr_player_id,
                    sb.player AS snap_player,
                    sb.era_team,
                    r.player_id,
                    r.player_name,
                    r.position,
                    CAST(r.jersey_number AS INTEGER) AS jersey_number,
                    r.headshot_url,
                    ROW_NUMBER() OVER (
                        PARTITION BY sb.game_id, sb.pfr_player_id, sb.player, sb.era_team
                        ORDER BY
                            CASE WHEN r.team = sb.era_team THEN 0
                                 WHEN r.team IN ((SELECT away_team FROM game), (SELECT home_team FROM game)) THEN 1
                                 ELSE 2 END,
                            r.week DESC NULLS LAST
                    ) AS rn
                FROM snap_base sb
                JOIN roster_season r
                  ON r.pfr_id = sb.pfr_player_id
            )
            WHERE rn = 1
        ),
        id_map_match AS (
            SELECT *
            FROM (
                SELECT
                    sb.pfr_player_id,
                    sb.player AS snap_player,
                    sb.era_team,
                    COALESCE(r.player_id, im.gsis_id) AS player_id,
                    COALESCE(r.player_name, im.name) AS player_name,
                    COALESCE(r.position, im.position) AS position,
                    CAST(r.jersey_number AS INTEGER) AS jersey_number,
                    r.headshot_url,
                    ROW_NUMBER() OVER (
                        PARTITION BY sb.game_id, sb.pfr_player_id, sb.player, sb.era_team
                        ORDER BY
                            CASE WHEN r.team = sb.era_team THEN 0
                                 WHEN im.team = sb.era_team THEN 1
                                 ELSE 2 END,
                            im.db_season DESC NULLS LAST,
                            r.week DESC NULLS LAST
                    ) AS rn
                FROM snap_base sb
                JOIN id_map im
                  ON im.pfr_id = sb.pfr_player_id
                 AND im.gsis_id IS NOT NULL
                LEFT JOIN roster_season r
                  ON r.player_id = im.gsis_id
            )
            WHERE rn = 1
        ),
        name_match AS (
            SELECT *
            FROM (
                SELECT
                    sb.pfr_player_id,
                    sb.player AS snap_player,
                    sb.era_team,
                    r.player_id,
                    r.player_name,
                    r.position,
                    CAST(r.jersey_number AS INTEGER) AS jersey_number,
                    r.headshot_url,
                    ROW_NUMBER() OVER (
                        PARTITION BY sb.game_id, sb.pfr_player_id, sb.player, sb.era_team
                        ORDER BY
                            CASE WHEN r.team = sb.era_team THEN 0
                                 WHEN r.team IN ((SELECT away_team FROM game), (SELECT home_team FROM game)) THEN 1
                                 ELSE 2 END,
                            r.week DESC NULLS LAST
                    ) AS rn
                FROM snap_base sb
                JOIN roster_season r
                  ON sb.snap_pos_key = r.roster_pos_key
                 AND sb.snap_name_key IN (r.roster_name_key, r.football_name_key)
            )
            WHERE rn = 1
        ),
        joined AS (
            SELECT
                sb.game_id,
                sb.pfr_player_id,
                sb.player AS snap_player_name,
                sb.era_team AS team,
                sb.position AS snap_position,
                sb.offense_snaps,
                sb.offense_pct,
                sb.defense_snaps,
                sb.defense_pct,
                sb.st_snaps,
                sb.st_pct,
                COALESCE(pm.player_id, imm.player_id, nm.player_id) AS player_id,
                COALESCE(pm.player_name, imm.player_name, nm.player_name) AS roster_player_name,
                COALESCE(pm.position, imm.position, nm.position) AS roster_position,
                COALESCE(pm.jersey_number, imm.jersey_number, nm.jersey_number) AS jersey_number,
                COALESCE(pm.headshot_url, imm.headshot_url, nm.headshot_url) AS headshot_url
            FROM snap_base sb
            LEFT JOIN pfr_match pm
              ON pm.pfr_player_id = sb.pfr_player_id
             AND pm.snap_player = sb.player
             AND pm.era_team = sb.era_team
            LEFT JOIN id_map_match imm
              ON imm.pfr_player_id = sb.pfr_player_id
             AND imm.snap_player = sb.player
             AND imm.era_team = sb.era_team
            LEFT JOIN name_match nm
              ON nm.pfr_player_id = sb.pfr_player_id
             AND nm.snap_player = sb.player
             AND nm.era_team = sb.era_team
        )
        SELECT
            j.pfr_player_id,
            j.team,
            j.player_id,
            COALESCE(j.roster_player_name, j.snap_player_name) AS player_name,
            COALESCE(j.roster_position, j.snap_position) AS position,
            CAST(j.jersey_number AS INTEGER) AS jersey_number,
            j.headshot_url,
            j.offense_snaps,
            j.offense_pct,
            j.defense_snaps,
            j.defense_pct,
            j.st_snaps,
            j.st_pct,
            gr.position_group,
            gr.rating,
            gr.raw_score,
            gr.plays_counted,
            CASE WHEN td.player_id IS NOT NULL THEN 1 ELSE 0 END AS scored_td
        FROM joined j
        LEFT JOIN player_game_ratings gr
          ON gr.game_id = ?
         AND gr.player_id = j.player_id
        LEFT JOIN (
            SELECT DISTINCT td_player_id AS player_id
            FROM plays
            WHERE game_id = ?
              AND COALESCE(touchdown, 0) = 1
              AND td_player_id IS NOT NULL
        ) td
          ON td.player_id = j.player_id
        ORDER BY j.team, j.offense_snaps DESC NULLS LAST, j.defense_snaps DESC NULLS LAST
        """,
        [game_id, game_id, game_id, game_id],
    )

    matched = sum(1 for r in snap_rows if r.get("pfr_player_id") and r.get("player_id"))
    eligible = sum(1 for r in snap_rows if r.get("pfr_player_id"))
    match_rate = round(matched / eligible, 4) if eligible else None

    scoring = safe_query(
        f"""
        WITH {PGS_GAME_CTE},
        roster_names AS (
            SELECT player_id, season, ANY_VALUE(player_name) AS player_name
            FROM rosters
            GROUP BY player_id, season
        )
        SELECT
            CASE WHEN COALESCE(p.touchdown, 0) = 1 THEN COALESCE(p.td_team, p.posteam)
                 ELSE p.posteam END AS team,
            CASE WHEN COALESCE(p.touchdown, 0) = 1 THEN p.td_player_id
                 ELSE p.kicker_player_id END AS player_id,
            CASE WHEN COALESCE(p.touchdown, 0) = 1
                    THEN COALESCE(pgs.player_name, rn.player_name)
                 ELSE p.kicker_player_name END AS player_name,
            CASE WHEN COALESCE(p.touchdown, 0) = 1 THEN 'TD'
                 WHEN p.field_goal_result = 'made' THEN 'FG'
                 ELSE 'SCORE' END AS kind,
            CAST(p.qtr AS INTEGER) AS qtr,
            p."time" AS clock,
            CAST(p.kick_distance AS INTEGER) AS distance,
            p."desc" AS desc
        FROM plays p
        LEFT JOIN pgs_game pgs
          ON pgs.game_id = p.game_id
         AND pgs.player_id = p.td_player_id
        LEFT JOIN roster_names rn
          ON rn.player_id = p.td_player_id
         AND rn.season = p.season
        WHERE p.game_id = ?
          AND (COALESCE(p.touchdown, 0) = 1 OR p.field_goal_result = 'made')
        ORDER BY p.game_seconds_remaining DESC NULLS LAST, p.play_id
        """,
        [game_id, game_id],
    )

    ol_grades = ol_grades_builder.read(game_id)

    def _avg(players: list[dict]) -> float | None:
        vals = [p["rating"] for p in players if p.get("rating") is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    teams = []
    for side, team in (("away", game["away_team"]), ("home", game["home_team"])):
        off = _lineup_players(snap_rows, team, "offense")
        defense = _lineup_players(snap_rows, team, "defense")
        starter_ids = {p["player_id"] for p in off + defense if p.get("player_id")}
        ratings = [r["rating"] for r in snap_rows if r["team"] == team and r.get("rating") is not None]
        ol_row = ol_grades.get(team) or {}
        teams.append({
            "team": team,
            "side": side,
            "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
            "offense_avg": _avg(off),
            "defense_avg": _avg(defense),
            "ol_grade": ol_row.get("grade"),
            "offense_personnel": _personnel_off(off),
            "defense_personnel": _personnel_def(defense),
            "offense": off,
            "defense": defense,
            "rotation": _rotation_players(snap_rows, team, starter_ids),
        })

    return {
        **game,
        "join_match_rate": match_rate,
        "scoring": scoring,
        "teams": teams,
    }
