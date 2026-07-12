"""Materialized per-game offensive line unit grades.

Public play-by-play attributes nothing to individual linemen, so the line is
graded as a unit on what it allows together: sack/QB-hit rate on dropbacks and
stuffed-run rate on carries. Raw scores are percentile-calibrated across all
loaded team-games and mapped through the same piecewise curve as
player_game_ratings, so a 6.5 line is league-average and 9+ is a top-2% game.
"""
from __future__ import annotations

import duckdb

from config import era_team_case
from database import get_connection, query_to_dict, write_lock

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS team_game_ol_grades (
    game_id         VARCHAR NOT NULL,
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    team            VARCHAR NOT NULL,
    grade           DOUBLE,
    raw_score       DOUBLE,
    dropbacks       INTEGER,
    sacks_allowed   INTEGER,
    qb_hits_allowed INTEGER,
    rushes          INTEGER,
    stuffed_rushes  INTEGER,
    PRIMARY KEY (game_id, team)
)
"""

_COLUMNS = (
    "game_id", "season", "week", "team", "grade", "raw_score",
    "dropbacks", "sacks_allowed", "qb_hits_allowed", "rushes", "stuffed_rushes",
)

# Keep in sync with the rating curve in game_ratings_builder._ratings_sql.
_CURVE_BREAKPOINTS = (
    (0.05, 3.0, 4.5),
    (0.25, 4.5, 5.7),
    (0.50, 5.7, 6.5),
    (0.75, 6.5, 7.3),
    (0.90, 7.3, 8.0),
    (0.98, 8.0, 9.0),
    (1.00, 9.0, 10.0),
)


def piecewise_curve_sql(p: str) -> str:
    """SQL CASE mapping a 0-1 percentile expression onto the 3.0-10.0 scale."""
    parts = []
    lo = 0.0
    for hi, r_lo, r_hi in _CURVE_BREAKPOINTS:
        cond = f"WHEN {p} <= {hi}" if hi < 1.0 else "ELSE"
        expr = f"{r_lo} + (({p} - {lo}) / ({hi} - {lo})) * ({r_hi} - {r_lo})"
        parts.append(f"{cond} THEN {expr}" if hi < 1.0 else f"{cond} {expr}")
        lo = hi
    return "CASE " + " ".join(parts) + " END"


def ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_TABLE_DDL)


def _has_column(conn: duckdb.DuckDBPyConnection, table: str, col: str) -> bool:
    try:
        return col in {r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()}
    except Exception:
        return False


def _grades_sql(conn: duckdb.DuckDBPyConnection) -> str:
    qb_hit = "COALESCE(qb_hit, 0)" if _has_column(conn, "plays", "qb_hit") else "0"
    team = era_team_case("posteam", "season")
    curve = piecewise_curve_sql("e.percentile")
    return f"""
    WITH unit AS (
        SELECT
            game_id,
            season,
            week,
            {team} AS team,
            SUM(CASE WHEN (COALESCE(pass_attempt,0) = 1 AND COALESCE(qb_spike,0) = 0)
                       OR COALESCE(sack,0) = 1 THEN 1 ELSE 0 END) AS dropbacks,
            SUM(COALESCE(sack, 0)) AS sacks_allowed,
            SUM(CASE WHEN (COALESCE(pass_attempt,0) = 1 OR COALESCE(sack,0) = 1)
                     THEN {qb_hit} ELSE 0 END) AS qb_hits_allowed,
            SUM(CASE WHEN COALESCE(rush_attempt,0) = 1 AND COALESCE(qb_kneel,0) = 0
                     THEN 1 ELSE 0 END) AS rushes,
            SUM(CASE WHEN COALESCE(rush_attempt,0) = 1 AND COALESCE(qb_kneel,0) = 0
                      AND COALESCE(yards_gained, 0) <= 0 THEN 1 ELSE 0 END) AS stuffed_rushes
        FROM plays
        WHERE posteam IS NOT NULL AND game_id IS NOT NULL
        GROUP BY game_id, season, week, {team}
    ),
    scored AS (
        SELECT *,
               -(
                   (sacks_allowed + 0.5 * qb_hits_allowed) / GREATEST(dropbacks, 1)
                   + CAST(stuffed_rushes AS DOUBLE) / GREATEST(rushes, 1)
               ) AS raw_score
        FROM unit
    ),
    eligible AS (
        SELECT *,
               PERCENT_RANK() OVER (ORDER BY raw_score) AS percentile
        FROM scored
        WHERE dropbacks + rushes >= 15
    )
    SELECT
        s.game_id,
        s.season,
        s.week,
        s.team,
        CASE WHEN e.percentile IS NULL THEN CAST(NULL AS DOUBLE)
             ELSE ROUND(GREATEST(3.0, LEAST(10.0, {curve})), 1)
        END AS grade,
        s.raw_score,
        s.dropbacks,
        s.sacks_allowed,
        s.qb_hits_allowed,
        s.rushes,
        s.stuffed_rushes
    FROM scored s
    LEFT JOIN eligible e ON e.game_id = s.game_id AND e.team = s.team
    """


def materialize(season: int | None = None) -> int:
    """Full-rebuild all OL unit grades and return rows written.

    Calibration is global across seasons, mirroring player_game_ratings.
    """
    del season
    with write_lock:
        conn = get_connection()
        ensure_table(conn)
        sql = _grades_sql(conn)
        conn.execute("DELETE FROM team_game_ol_grades")
        try:
            conn.execute(f"""
                INSERT INTO team_game_ol_grades ({", ".join(_COLUMNS)})
                SELECT {", ".join(_COLUMNS)}
                FROM ({sql})
            """)
        except Exception as e:
            print(f"team_game_ol_grades materialize failed: {e}")
            return 0
        return conn.execute("SELECT COUNT(*) FROM team_game_ol_grades").fetchone()[0]


def read(game_id: str) -> dict[str, dict]:
    """OL grade rows for one game, keyed by era-correct team abbreviation."""
    try:
        rows = query_to_dict(
            "SELECT * FROM team_game_ol_grades WHERE game_id = ?", [game_id]
        )
        return {r["team"]: r for r in rows}
    except Exception:
        return {}


def read_or_materialize(game_id: str) -> dict[str, dict]:
    rows = read(game_id)
    if rows:
        return rows
    if not write_lock.acquire(timeout=15):
        return {}
    try:
        rows = read(game_id)
        if rows:
            return rows
        if materialize() > 0:
            return read(game_id)
        return {}
    finally:
        write_lock.release()
