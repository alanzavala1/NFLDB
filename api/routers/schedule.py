"""Schedule and game endpoints."""
from fastapi import APIRouter, HTTPException, Query

from database import query_to_dict
from schemas.schedule import Game, GameDetail, ScheduleWeek
from sql_helpers import PGS_STAT_SEL, ROSTER_CTE, safe_query, team_sql

router = APIRouter()


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
def get_schedule(season: int = Query(2025)):
    rows = query_to_dict(
        """
        SELECT
            game_id, season, game_type, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            away_qb_name, home_qb_name, spread_line, total_line,
            roof, surface, temp, wind, stadium, overtime, div_game
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
    season: int = Query(2025),
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
            div_game
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
            roof, surface, temp, wind, stadium
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
        q_rows = safe_query(
            """
            SELECT
                qtr,
                MAX(CASE WHEN posteam = ? THEN posteam_score
                         WHEN defteam  = ? THEN defteam_score END) AS away_cumul,
                MAX(CASE WHEN posteam = ? THEN posteam_score
                         WHEN defteam  = ? THEN defteam_score END) AS home_cumul
            FROM plays
            WHERE game_id = ?
            GROUP BY qtr
            ORDER BY qtr
            """,
            [away_team, away_team, home_team, home_team, game_id],
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
