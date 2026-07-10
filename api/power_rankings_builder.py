"""Materialized weekly EPA team power rankings."""
from __future__ import annotations

import duckdb

from config import era_team_case
from database import get_connection, query_to_dict, write_lock


_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS team_power_rankings (
    season        INTEGER NOT NULL,
    week          INTEGER NOT NULL,
    team          VARCHAR NOT NULL,
    off_epa_play  DOUBLE,
    def_epa_play  DOUBLE,
    net_epa_play  DOUBLE,
    score         DOUBLE,
    rank          INTEGER,
    prev_rank     INTEGER,
    movement      INTEGER,
    PRIMARY KEY (season, week, team)
)
"""

_COLUMNS = (
    "season", "week", "team", "off_epa_play", "def_epa_play",
    "net_epa_play", "score", "rank", "prev_rank", "movement",
)


def ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_TABLE_DDL)


def _columns(conn: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    try:
        return {r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()}
    except Exception:
        return set()


def _rankings_sql(conn: duckdb.DuckDBPyConnection, season: int) -> str:
    plays_cols = _columns(conn, "plays")
    if not plays_cols:
        return "SELECT * FROM team_power_rankings WHERE 1 = 0"

    play_filter = "play_type IN ('pass', 'run')"
    if "qb_kneel" in plays_cols:
        play_filter += " AND COALESCE(qb_kneel, 0) = 0"
    if "qb_spike" in plays_cols:
        play_filter += " AND COALESCE(qb_spike, 0) = 0"
    if "two_point_attempt" in plays_cols:
        play_filter += " AND COALESCE(two_point_attempt, 0) = 0"

    off_team = era_team_case("p.posteam", "p.season")
    def_team = era_team_case("p.defteam", "p.season")
    s = int(season)

    return f"""
    WITH
    completed_games AS (
        SELECT game_id, CAST(season AS INTEGER) AS season, CAST(week AS INTEGER) AS week
        FROM schedules
        WHERE season = {s}
          AND away_score IS NOT NULL
          AND home_score IS NOT NULL
    ),
    weeks AS (
        SELECT DISTINCT season, week
        FROM completed_games
    ),
    teams AS (
        SELECT DISTINCT CAST(season AS INTEGER) AS season, away_team AS team
        FROM schedules
        WHERE season = {s}
        UNION
        SELECT DISTINCT CAST(season AS INTEGER) AS season, home_team AS team
        FROM schedules
        WHERE season = {s}
    ),
    team_weeks AS (
        SELECT w.season, w.week, t.team
        FROM weeks w
        JOIN teams t USING (season)
    ),
    base_plays AS (
        SELECT
            cg.season,
            cg.week,
            {off_team} AS off_team,
            {def_team} AS def_team,
            COALESCE(p.epa, 0) AS epa
        FROM plays p
        JOIN completed_games cg ON cg.game_id = p.game_id
        WHERE p.season = {s}
          AND p.posteam IS NOT NULL
          AND p.defteam IS NOT NULL
          AND {play_filter}
    ),
    weekly_off AS (
        SELECT season, week, off_team AS team,
               SUM(epa) AS sum_epa,
               COUNT(*) AS plays
        FROM base_plays
        GROUP BY season, week, off_team
    ),
    weekly_def AS (
        SELECT season, week, def_team AS team,
               SUM(epa) AS sum_epa,
               COUNT(*) AS plays
        FROM base_plays
        GROUP BY season, week, def_team
    ),
    cumulative AS (
        SELECT
            tw.season,
            tw.week,
            tw.team,
            SUM(COALESCE(wo.sum_epa, 0)) OVER (
                PARTITION BY tw.season, tw.team
                ORDER BY tw.week
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS off_epa_sum,
            SUM(COALESCE(wo.plays, 0)) OVER (
                PARTITION BY tw.season, tw.team
                ORDER BY tw.week
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS off_plays,
            SUM(COALESCE(wd.sum_epa, 0)) OVER (
                PARTITION BY tw.season, tw.team
                ORDER BY tw.week
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS def_epa_sum,
            SUM(COALESCE(wd.plays, 0)) OVER (
                PARTITION BY tw.season, tw.team
                ORDER BY tw.week
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS def_plays
        FROM team_weeks tw
        LEFT JOIN weekly_off wo
          ON wo.season = tw.season AND wo.week = tw.week AND wo.team = tw.team
        LEFT JOIN weekly_def wd
          ON wd.season = tw.season AND wd.week = tw.week AND wd.team = tw.team
    ),
    metrics AS (
        SELECT
            season,
            week,
            team,
            off_epa_sum / NULLIF(off_plays + 150, 0) AS off_epa_play,
            def_epa_sum / NULLIF(def_plays + 150, 0) AS def_epa_play,
            off_epa_sum / NULLIF(off_plays + 150, 0)
              - def_epa_sum / NULLIF(def_plays + 150, 0) AS net_epa_play,
            off_epa_sum / NULLIF(off_plays + 150, 0)
              - def_epa_sum / NULLIF(def_plays + 150, 0) AS score
        FROM cumulative
    ),
    ranked AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY season, week
                ORDER BY score DESC NULLS LAST, team
            ) AS rank
        FROM metrics
    ),
    with_prev AS (
        SELECT
            *,
            LAG(rank) OVER (PARTITION BY season, team ORDER BY week) AS prev_rank
        FROM ranked
    )
    SELECT
        season,
        week,
        team,
        off_epa_play,
        def_epa_play,
        net_epa_play,
        score,
        rank,
        prev_rank,
        CASE WHEN prev_rank IS NULL THEN NULL ELSE prev_rank - rank END AS movement
    FROM with_prev
    """


def materialize(season: int) -> int:
    """Compute one season's weekly rankings and persist them."""
    with write_lock:
        conn = get_connection()
        ensure_table(conn)
        s = int(season)
        sql = _rankings_sql(conn, s)
        conn.execute("DELETE FROM team_power_rankings WHERE season = ?", [s])
        try:
            conn.execute(f"""
                INSERT INTO team_power_rankings ({", ".join(_COLUMNS)})
                SELECT {", ".join(_COLUMNS)}
                FROM ({sql})
            """)
        except Exception as e:
            print(f"team_power_rankings materialize failed for season {s}: {e}")
            return 0
        return conn.execute(
            "SELECT COUNT(*) FROM team_power_rankings WHERE season = ?", [s]
        ).fetchone()[0]


def latest_week(season: int) -> int | None:
    try:
        row = query_to_dict(
            "SELECT MAX(week) AS week FROM team_power_rankings WHERE season = ?",
            [int(season)],
        )[0]
        return row["week"]
    except Exception:
        return None


def read(season: int, week: int | None = None) -> list[dict]:
    try:
        s = int(season)
        w = int(week) if week is not None else latest_week(s)
        if w is None:
            return []
        return query_to_dict(
            """
            SELECT season, week, team, off_epa_play, def_epa_play,
                   net_epa_play, score, rank, prev_rank, movement
            FROM team_power_rankings
            WHERE season = ? AND week = ?
            ORDER BY rank
            """,
            [s, w],
        )
    except Exception:
        return []


def read_or_materialize(season: int, week: int | None = None) -> list[dict]:
    rows = read(season, week)
    if rows:
        return rows
    if not write_lock.acquire(timeout=15):
        return []
    try:
        rows = read(season, week)
        if rows:
            return rows
        if materialize(season) > 0:
            return read(season, week)
        return []
    finally:
        write_lock.release()
