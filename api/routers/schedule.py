"""Schedule and game endpoints."""
from fastapi import APIRouter, HTTPException, Query

from config import CURRENT_SEASON, era_team_case
from database import query_to_dict
import game_ratings_builder
import ol_grades_builder
from schemas.lineup import GameLineup, PlayerChart
from schemas.ratings import GamePlayerRating
from schemas.schedule import Game, GameDetail, ScheduleWeek
from sql_helpers import PGS_STAT_SEL, ROSTER_CTE, STAT_COLS, safe_query, team_sql

router = APIRouter()


OFFENSE_POS = {"QB", "RB", "FB", "WR", "TE", "HB"}
DEFENSE_POS = {"DE", "DT", "NT", "DL", "EDGE", "OLB", "ILB", "MLB", "LB", "CB", "DB", "FS", "SS", "S"}
PGS_GAME_CTE = f"""
        pgs_game AS (
            SELECT
                player_id,
                game_id,
                ANY_VALUE(player_name) AS player_name,
                CAST(ANY_VALUE(season) AS INTEGER) AS season,
                CAST(ANY_VALUE(week) AS INTEGER) AS week,
                ANY_VALUE(team) AS team,
                {", ".join(f"SUM(COALESCE({c}, 0)) AS {c}" for c in STAT_COLS)}
            FROM player_game_stats
            WHERE game_id = ?
            GROUP BY player_id, game_id
        )
"""


def _position_group(position: str | None) -> str | None:
    if not position:
        return None
    p = position.upper()
    if p == "QB":
        return "QB"
    if p in {"RB", "FB", "HB"}:
        return "RB"
    if p == "WR":
        return "WR"
    if p == "TE":
        return "TE"
    if p in DEFENSE_POS:
        return "DEF"
    if p == "K":
        return "K"
    return None


def _personnel_off(players: list[dict]) -> str | None:
    if not players:
        return None
    wr = sum(1 for p in players if (p.get("position") or "").upper() == "WR")
    te = sum(1 for p in players if (p.get("position") or "").upper() == "TE")
    rb = sum(1 for p in players if (p.get("position") or "").upper() in {"RB", "FB", "HB"})
    return f"{rb}{te} personnel" if rb or te or wr else "Offense"


def _personnel_def(players: list[dict]) -> str | None:
    if not players:
        return None
    dl = sum(1 for p in players if (p.get("position") or "").upper() in {"DE", "DT", "NT", "DL", "EDGE"})
    lb = sum(1 for p in players if (p.get("position") or "").upper() in {"OLB", "ILB", "MLB", "LB"})
    db = sum(1 for p in players if (p.get("position") or "").upper() in {"CB", "DB", "FS", "SS", "S", "NB"})
    if db >= 6:
        return "Dime"
    if db == 5:
        return "Nickel"
    if dl and lb:
        return f"{dl}-{lb}"
    return "Defense"


def _lineup_players(rows: list[dict], team: str, unit: str) -> list[dict]:
    snap_col = "offense_snaps" if unit == "offense" else "defense_snaps"
    pct_col = "offense_pct" if unit == "offense" else "defense_pct"
    unit_rows = [r for r in rows if r["team"] == team and (r.get(snap_col) or 0) > 0]
    unit_rows.sort(key=lambda r: (r.get(snap_col) or 0, r.get("rating") or -1, r.get("player_name") or ""), reverse=True)
    players = []
    for r in unit_rows[:11]:
        players.append({
            "player_id": r.get("player_id"),
            "pfr_player_id": r.get("pfr_player_id"),
            "player_name": r.get("player_name") or "Unknown",
            "team": team,
            "position": r.get("position"),
            "position_group": r.get("position_group") or _position_group(r.get("position")),
            "jersey_number": int(r["jersey_number"]) if r.get("jersey_number") is not None else None,
            "headshot_url": r.get("headshot_url"),
            "rating": r.get("rating"),
            "raw_score": r.get("raw_score"),
            "snaps": int(r.get(snap_col) or 0),
            "snap_pct": r.get(pct_col),
            "scored_td": bool(r.get("scored_td")),
        })
    return players


def _rotation_players(rows: list[dict], team: str, starters: set[str | None]) -> list[dict]:
    rot = []
    for r in rows:
        if r["team"] != team or r.get("player_id") in starters:
            continue
        snaps = max(r.get("offense_snaps") or 0, r.get("defense_snaps") or 0, r.get("st_snaps") or 0)
        if snaps <= 0:
            continue
        pct = max(r.get("offense_pct") or 0, r.get("defense_pct") or 0, r.get("st_pct") or 0)
        rot.append({
            "player_id": r.get("player_id"),
            "pfr_player_id": r.get("pfr_player_id"),
            "player_name": r.get("player_name") or "Unknown",
            "team": team,
            "position": r.get("position"),
            "position_group": r.get("position_group") or _position_group(r.get("position")),
            "jersey_number": int(r["jersey_number"]) if r.get("jersey_number") is not None else None,
            "headshot_url": r.get("headshot_url"),
            "rating": r.get("rating"),
            "raw_score": r.get("raw_score"),
            "snaps": int(snaps),
            "snap_pct": pct,
            "scored_td": bool(r.get("scored_td")),
        })
    rot.sort(key=lambda r: (r["rating"] is not None, r["rating"] or -1, r["snaps"]), reverse=True)
    return rot[:10]


def attach_records(games: list[dict]) -> list[dict]:
    """Add away_record / home_record (entering each game) by walking weeks in order."""
    team_records: dict[str, tuple[int, int, int]] = {}  # team -> (W, L, T)

    def fmt(wlt: tuple[int, int, int]) -> str:
        w, l, t = wlt
        return f"{w}-{l}-{t}" if t else f"{w}-{l}"

    by_week: dict[int, list[dict]] = {}
    for g in games:
        by_week.setdefault(g["week"], []).append(g)

    for week in sorted(by_week):
        for g in by_week[week]:
            g["away_record"] = fmt(team_records.get(g["away_team"], (0, 0, 0)))
            g["home_record"] = fmt(team_records.get(g["home_team"], (0, 0, 0)))

        for g in by_week[week]:
            a, h = g["away_team"], g["home_team"]
            as_, hs = g["away_score"], g["home_score"]
            if as_ is None or hs is None:
                continue
            aw, al, at = team_records.get(a, (0, 0, 0))
            hw, hl, ht = team_records.get(h, (0, 0, 0))
            if as_ > hs:
                team_records[a] = (aw + 1, al, at)
                team_records[h] = (hw, hl + 1, ht)
            elif hs > as_:
                team_records[a] = (aw, al + 1, at)
                team_records[h] = (hw + 1, hl, ht)
            else:
                team_records[a] = (aw, al, at + 1)
                team_records[h] = (hw, hl, ht + 1)

    return games


@router.get("/schedule", response_model=list[ScheduleWeek])
def get_schedule(season: int = Query(default=CURRENT_SEASON)):
    rows = query_to_dict(
        """
        SELECT
            game_id, season, game_type, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            away_qb_name, home_qb_name, spread_line, total_line,
            roof, surface, temp, wind, stadium, overtime, div_game,
            away_coach, home_coach
        FROM schedules
        WHERE season = ?
        ORDER BY week, gametime
        """,
        [season],
    )
    attach_records(rows)
    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row["week"], []).append(row)
    return [{"week": w, "games": games} for w, games in sorted(grouped.items())]


@router.get("/games", response_model=list[Game])
def get_games(
    week: int = Query(..., ge=1, le=22),
    season: int = Query(default=CURRENT_SEASON),
):
    rows = query_to_dict(
        """
        SELECT
            game_id,
            season,
            game_type,
            week,
            gameday,
            gametime,
            away_team,
            home_team,
            away_score,
            home_score,
            away_qb_name,
            home_qb_name,
            spread_line,
            total_line,
            roof,
            surface,
            temp,
            wind,
            stadium,
            overtime,
            div_game,
            away_coach,
            home_coach
        FROM schedules
        WHERE week = ? AND season = ?
        ORDER BY gametime
        """,
        [week, season],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No games found for week {week}, season {season}")
    return rows


@router.get("/games/{game_id}", response_model=GameDetail)
def get_game(game_id: str):
    games = query_to_dict(
        """
        SELECT
            game_id, season, game_type, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            away_qb_name, home_qb_name,
            spread_line, total_line, overtime, div_game,
            roof, surface, temp, wind, stadium,
            away_coach, home_coach
        FROM schedules
        WHERE game_id = ?
        """,
        [game_id],
    )
    if not games:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    game = games[0]

    # Compute each team's record entering this game
    prior = query_to_dict(
        """
        SELECT away_team, home_team, away_score, home_score, week
        FROM schedules
        WHERE season = ? AND week < ? AND away_score IS NOT NULL
        ORDER BY week
        """,
        [game["season"], game["week"]],
    )
    attach_records(prior + [game])  # mutates game in-place

    away_team = game["away_team"]
    home_team = game["home_team"]
    team_sel, team_rank = team_sql("?", "?")

    players = query_to_dict(
        f"""
        WITH {ROSTER_CTE},
        ranked AS (
            SELECT
                pgs.player_id,
                pgs.player_name,
                {team_sel} AS team,
                pgs.week,
                r.position, r.jersey_number, r.headshot_url,
                {PGS_STAT_SEL},
                ROW_NUMBER() OVER (
                    PARTITION BY pgs.player_id
                    ORDER BY {team_rank}
                ) AS rn
            FROM player_game_stats pgs
            LEFT JOIN roster r ON r.player_id = pgs.player_id AND r.season = pgs.season
            WHERE pgs.game_id = ?
        )
        SELECT * EXCLUDE (rn)
        FROM ranked
        WHERE rn = 1
        ORDER BY team, position, player_name
        """,
        [away_team, home_team, away_team, home_team,
         away_team, home_team, away_team, home_team, away_team, home_team,
         game_id],
    )

    # Quarter-by-quarter scores from play-by-play
    quarter_scores = []
    try:
        # total_away_score / total_home_score are the running scores *after* each
        # play, so MAX per quarter is the true end-of-quarter score. (posteam_score
        # / defteam_score are pre-snap scores — a score on a quarter's final play
        # would leak into the next quarter's delta.)
        q_rows = safe_query(
            """
            SELECT
                qtr,
                MAX(total_away_score) AS away_cumul,
                MAX(total_home_score) AS home_cumul
            FROM plays
            WHERE game_id = ?
            GROUP BY qtr
            ORDER BY qtr
            """,
            [game_id],
        )
        away_prev = home_prev = 0
        for row in q_rows:
            ac = int(row["away_cumul"] or 0)
            hc = int(row["home_cumul"] or 0)
            quarter_scores.append({"qtr": int(row["qtr"]), "away": ac - away_prev, "home": hc - home_prev})
            away_prev, home_prev = ac, hc
    except Exception:
        pass

    win_prob = safe_query(
        """
        SELECT
            game_seconds_remaining,
            qtr,
            ROUND(home_wp, 4)   AS home_wp,
            COALESCE(touchdown,    0) AS touchdown,
            COALESCE(interception, 0) AS interception,
            COALESCE(fumble_lost,  0) AS fumble_lost,
            posteam,
            "desc"              AS desc
        FROM plays
        WHERE game_id = ?
          AND home_wp IS NOT NULL
          AND game_seconds_remaining IS NOT NULL
        ORDER BY game_seconds_remaining DESC
        """,
        [game_id],
    )

    # Team box-score line from play-by-play (first downs, conversions, EPA, etc.)
    ts_rows = safe_query(
        """
        SELECT posteam AS team,
            COUNT(*) FILTER (WHERE play_type IN ('pass', 'run'))            AS plays,
            CAST(SUM(COALESCE(first_down, 0)) AS INTEGER)                   AS first_downs,
            -- conversion attempts only (excludes punts / FGs that also have down=4)
            CAST(COUNT(*) FILTER (WHERE COALESCE(third_down_converted, 0) = 1 OR COALESCE(third_down_failed, 0) = 1) AS INTEGER) AS third_att,
            CAST(SUM(COALESCE(third_down_converted, 0)) AS INTEGER)        AS third_conv,
            CAST(COUNT(*) FILTER (WHERE COALESCE(fourth_down_converted, 0) = 1 OR COALESCE(fourth_down_failed, 0) = 1) AS INTEGER) AS fourth_att,
            CAST(SUM(COALESCE(fourth_down_converted, 0)) AS INTEGER)       AS fourth_conv,
            CAST(SUM(COALESCE(interception, 0)) + SUM(COALESCE(fumble_lost, 0)) AS INTEGER) AS turnovers,
            ROUND(AVG(epa) FILTER (WHERE play_type IN ('pass', 'run')), 3)  AS epa_play,
            ROUND(100.0 * AVG(success) FILTER (WHERE play_type IN ('pass', 'run')), 1) AS success_pct
        FROM plays
        WHERE game_id = ? AND posteam IS NOT NULL
        GROUP BY posteam
        """,
        [game_id],
    )
    pen_rows = safe_query(
        """
        SELECT penalty_team AS team, COUNT(*) AS penalties,
               CAST(SUM(COALESCE(penalty_yards, 0)) AS INTEGER) AS penalty_yards
        FROM plays
        WHERE game_id = ? AND COALESCE(penalty, 0) = 1 AND penalty_team IS NOT NULL
        GROUP BY penalty_team
        """,
        [game_id],
    )
    pen_by_team = {r["team"]: r for r in pen_rows}
    team_stats = []
    for r in ts_rows:
        p = pen_by_team.get(r["team"], {})
        team_stats.append({**r, "penalties": p.get("penalties", 0) or 0,
                           "penalty_yards": p.get("penalty_yards", 0) or 0})

    # Scoring summary: each scoring play (sp=1); fold the PAT into its TD and
    # use the post-PAT running score (total_*_score is cumulative after the play).
    sp_rows = safe_query(
        """
        SELECT qtr, "time" AS clock, "desc" AS desc,
               -- the team that actually scored: td_team on a TD (handles pick-
               -- sixes / fumble returns), the defense on a safety, else posteam
               CASE WHEN COALESCE(touchdown, 0) = 1 THEN COALESCE(td_team, posteam)
                    WHEN COALESCE(safety, 0) = 1   THEN defteam
                    ELSE posteam END AS team,
               CAST(COALESCE(total_away_score, 0) AS INTEGER) AS away_score,
               CAST(COALESCE(total_home_score, 0) AS INTEGER) AS home_score,
               COALESCE(touchdown, 0)        AS is_td,
               field_goal_result            AS fg,
               COALESCE(safety, 0)           AS is_saf,
               extra_point_result           AS xp,
               two_point_conv_result        AS two_pt
        FROM plays
        WHERE game_id = ? AND COALESCE(sp, 0) = 1
        ORDER BY game_seconds_remaining DESC, qtr
        """,
        [game_id],
    )
    scoring = []
    for r in sp_rows:
        is_pat = r["xp"] is not None or r["two_pt"] is not None
        if is_pat and scoring:  # roll the extra point / 2pt into the preceding TD
            scoring[-1]["away_score"] = r["away_score"]
            scoring[-1]["home_score"] = r["home_score"]
            continue
        kind = "TD" if r["is_td"] else "FG" if r["fg"] == "made" else "SAF" if r["is_saf"] else "SCORE"
        scoring.append({"qtr": int(r["qtr"]), "clock": r["clock"], "team": r["team"],
                        "kind": kind, "desc": r["desc"],
                        "away_score": r["away_score"], "home_score": r["home_score"]})

    return {
        **game,
        "away": [p for p in players if p["team"] == away_team],
        "home": [p for p in players if p["team"] == home_team],
        "quarter_scores": quarter_scores,
        "win_prob": win_prob,
        "team_stats": team_stats,
        "scoring": scoring,
    }


@router.get("/games/{game_id}/ratings", response_model=list[GamePlayerRating])
def get_game_ratings(game_id: str):
    game = query_to_dict(
        "SELECT game_id FROM schedules WHERE game_id = ?",
        [game_id],
    )
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

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
