"""Schedule and game endpoints."""
from fastapi import APIRouter, HTTPException, Query

from config import CURRENT_SEASON, era_team_case
from database import query_to_dict
import game_ratings_builder
import ol_grades_builder
from schemas.lineup import GameLineup, PlayerChart
from schemas.ratings import GamePlayerRating
from schemas.schedule import Game, GameDetail, ScheduleWeek
from services.schedule import get_games as query_games, get_schedule as query_schedule
from services.game_detail import get_game_detail as query_game_detail
from services.game_ratings import get_game_ratings as query_game_ratings
from services.game_players import (
    position_group as _position_group,
    offense_personnel as _personnel_off,
    defense_personnel as _personnel_def,
    lineup_players as _lineup_players,
    rotation_players as _rotation_players,
)
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
    games = query_to_dict(
        """
        SELECT game_id, season, week, away_team, home_team, away_coach, home_coach
        FROM schedules
        WHERE game_id = ?
        """,
        [game_id],
    )
    if not games:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    game = games[0]

    # Ensure the derived ratings table exists before joining it. This is a no-op
    # once ratings have already been materialized by ingest.
    game_ratings_builder.read_or_materialize(game_id)

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

    ol_grades = ol_grades_builder.read_or_materialize(game_id)

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
