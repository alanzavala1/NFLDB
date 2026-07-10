"""Materialized per-game player ratings.

The table is intentionally play-derived and full-rebuilt: ratings are
percentile-calibrated across all seasons, so adding a new season can move the
whole scale slightly. Endpoints read the materialized table and lazily rebuild
if it is missing.
"""
from __future__ import annotations

import duckdb

from config import era_team_case
from database import get_connection, query_to_dict, write_lock


_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS player_game_ratings (
    player_id       VARCHAR NOT NULL,
    game_id         VARCHAR NOT NULL,
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    team            VARCHAR,
    position_group  VARCHAR NOT NULL,
    rating          DOUBLE,
    raw_score       DOUBLE,
    plays_counted   INTEGER,
    epa_total       DOUBLE,
    turnovers       DOUBLE,
    def_events_score DOUBLE,
    fg_points       DOUBLE,
    PRIMARY KEY (player_id, game_id)
)
"""

_COLUMNS = (
    "player_id", "game_id", "season", "week", "team", "position_group",
    "rating", "raw_score", "plays_counted", "epa_total", "turnovers",
    "def_events_score", "fg_points",
)

_DEF_COMPONENTS = (
    ("solo_tackles", 0.4),
    ("assist_tackles", 0.2),
    ("tackles_for_loss", 0.6),
    ("qb_hits", 0.5),
    ("sacks", 1.6),
    ("def_interceptions", 2.4),
    ("pass_breakups", 1.0),
    ("forced_fumbles", 1.5),
    ("fumble_recoveries", 1.0),
    ("def_tds", 3.0),
)


def ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_TABLE_DDL)


def _columns(conn: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    try:
        return {r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()}
    except Exception:
        return set()


def _roster_cte() -> str:
    return """
    roster AS (
        SELECT
            player_id,
            season,
            team,
            position,
            player_name,
            CASE
                WHEN UPPER(position) = 'QB' THEN 'QB'
                WHEN UPPER(position) IN ('RB', 'FB', 'HB') THEN 'RB'
                WHEN UPPER(position) = 'WR' THEN 'WR'
                WHEN UPPER(position) = 'TE' THEN 'TE'
                WHEN UPPER(position) IN ('K', 'PK') THEN 'K'
                WHEN UPPER(position) IN (
                    'CB', 'DB', 'DE', 'DL', 'DT', 'EDGE', 'FS', 'ILB',
                    'LB', 'MLB', 'NT', 'OLB', 'S', 'SS'
                ) THEN 'DEF'
                ELSE NULL
            END AS roster_group
        FROM rosters
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY player_id, season
            ORDER BY week DESC NULLS LAST, team
        ) = 1
    )"""


def _defense_source_sql(pgs_cols: set[str], weekly_cols: set[str]) -> str:
    """Return a DEF candidate SELECT.

    player_game_stats is preferred because it is already one row per player
    game. The weekly fallback is only used if a future source carries defensive
    event columns there.
    """
    pgs_has_def = any(col in pgs_cols for col, _ in _DEF_COMPONENTS)
    if pgs_has_def:
        def col(name: str) -> str:
            return f"COALESCE(pgs.{name}, 0)" if name in pgs_cols else "0"

        raw_expr = " + ".join(f"{weight} * {col(name)}" for name, weight in _DEF_COMPONENTS)
        count_expr = " + ".join(col(name) for name, _ in _DEF_COMPONENTS)
        team_expr = era_team_case("pgs.team", "pgs.season")
        return f"""
        SELECT
            pgs.player_id,
            pgs.game_id,
            CAST(pgs.season AS INTEGER) AS season,
            CAST(pgs.week AS INTEGER) AS week,
            COALESCE({team_expr}, r.team) AS team,
            'DEF' AS position_group,
            CAST({raw_expr} AS DOUBLE) AS raw_score,
            CAST(ROUND({count_expr}) AS INTEGER) AS plays_counted,
            CAST(NULL AS DOUBLE) AS epa_total,
            CAST(NULL AS DOUBLE) AS turnovers,
            CAST({raw_expr} AS DOUBLE) AS def_events_score,
            CAST(NULL AS DOUBLE) AS fg_points,
            5 AS family_priority
        FROM player_game_stats pgs
        LEFT JOIN roster r ON r.player_id = pgs.player_id AND r.season = pgs.season
        WHERE COALESCE(r.roster_group, 'DEF') = 'DEF'
           OR ({raw_expr}) > 0
        """

    weekly_has_def = any(col in weekly_cols for col, _ in _DEF_COMPONENTS)
    if not weekly_has_def:
        return """
        SELECT
            CAST(NULL AS VARCHAR) AS player_id,
            CAST(NULL AS VARCHAR) AS game_id,
            CAST(NULL AS INTEGER) AS season,
            CAST(NULL AS INTEGER) AS week,
            CAST(NULL AS VARCHAR) AS team,
            CAST(NULL AS VARCHAR) AS position_group,
            CAST(NULL AS DOUBLE) AS raw_score,
            CAST(NULL AS INTEGER) AS plays_counted,
            CAST(NULL AS DOUBLE) AS epa_total,
            CAST(NULL AS DOUBLE) AS turnovers,
            CAST(NULL AS DOUBLE) AS def_events_score,
            CAST(NULL AS DOUBLE) AS fg_points,
            CAST(NULL AS INTEGER) AS family_priority
        WHERE 1 = 0
        """

    def wcol(name: str) -> str:
        return f"COALESCE(w.{name}, 0)" if name in weekly_cols else "0"

    raw_expr = " + ".join(f"{weight} * {wcol(name)}" for name, weight in _DEF_COMPONENTS)
    count_expr = " + ".join(wcol(name) for name, _ in _DEF_COMPONENTS)
    team_expr = era_team_case("w.recent_team", "w.season")
    name_col = "player_display_name" if "player_display_name" in weekly_cols else "player_name"
    return f"""
    SELECT
        w.player_id,
        sch.game_id,
        CAST(w.season AS INTEGER) AS season,
        CAST(w.week AS INTEGER) AS week,
        {team_expr} AS team,
        'DEF' AS position_group,
        CAST({raw_expr} AS DOUBLE) AS raw_score,
        CAST(ROUND({count_expr}) AS INTEGER) AS plays_counted,
        CAST(NULL AS DOUBLE) AS epa_total,
        CAST(NULL AS DOUBLE) AS turnovers,
        CAST({raw_expr} AS DOUBLE) AS def_events_score,
        CAST(NULL AS DOUBLE) AS fg_points,
        5 AS family_priority
    FROM weekly_player_stats w
    LEFT JOIN schedules sch
      ON sch.season = w.season AND sch.week = w.week
     AND (sch.home_team = {team_expr} OR sch.away_team = {team_expr})
    LEFT JOIN roster r ON r.player_id = w.player_id AND r.season = w.season
    WHERE w.player_id IS NOT NULL
      AND sch.game_id IS NOT NULL
      AND (COALESCE(r.roster_group, 'DEF') = 'DEF' OR ({raw_expr}) > 0)
      AND w.{name_col} IS NOT NULL
    """


def _ratings_sql(conn: duckdb.DuckDBPyConnection) -> str:
    plays_cols = _columns(conn, "plays")
    pgs_cols = _columns(conn, "player_game_stats")
    weekly_cols = _columns(conn, "weekly_player_stats")

    if not plays_cols:
        return "SELECT * FROM player_game_ratings WHERE 1 = 0"

    two_pt_filter = "AND COALESCE(two_point_attempt, 0) = 0" if "two_point_attempt" in plays_cols else ""
    qb_epa = "qb_epa" if "qb_epa" in plays_cols else "epa"
    off_team = era_team_case("posteam", "season")

    defense_sql = _defense_source_sql(pgs_cols, weekly_cols)

    return f"""
    WITH
    {_roster_cte()},
    qb AS (
        SELECT
            passer_player_id AS player_id,
            game_id,
            CAST(season AS INTEGER) AS season,
            CAST(week AS INTEGER) AS week,
            {off_team} AS team,
            'QB' AS position_group,
            CAST(SUM(COALESCE({qb_epa}, 0)) AS DOUBLE) AS raw_score,
            CAST(COUNT(*) AS INTEGER) AS plays_counted,
            CAST(SUM(COALESCE({qb_epa}, 0)) AS DOUBLE) AS epa_total,
            CAST(SUM(CASE WHEN COALESCE(interception, 0) = 1 OR COALESCE(fumble_lost, 0) = 1 THEN 1 ELSE 0 END) AS DOUBLE) AS turnovers,
            CAST(NULL AS DOUBLE) AS def_events_score,
            CAST(NULL AS DOUBLE) AS fg_points,
            1 AS family_priority
        FROM plays
        WHERE passer_player_id IS NOT NULL
          AND (COALESCE(pass_attempt, 0) = 1 OR COALESCE(sack, 0) = 1)
          {two_pt_filter}
        GROUP BY passer_player_id, game_id, season, week, {off_team}
    ),
    qb_candidates AS (
        SELECT qb.*
        FROM qb
        JOIN roster r ON r.player_id = qb.player_id AND r.season = qb.season
        WHERE r.roster_group = 'QB'
    ),
    skill_events AS (
        SELECT
            rusher_player_id AS player_id,
            game_id,
            CAST(season AS INTEGER) AS season,
            CAST(week AS INTEGER) AS week,
            {off_team} AS team,
            CAST(COALESCE(epa, 0) AS DOUBLE) AS epa,
            CASE WHEN COALESCE(fumble_lost, 0) = 1 THEN 1 ELSE 0 END AS fumble_lost
        FROM plays
        WHERE rusher_player_id IS NOT NULL
          AND COALESCE(rush_attempt, 0) = 1
          {two_pt_filter}
        UNION ALL
        SELECT
            receiver_player_id AS player_id,
            game_id,
            CAST(season AS INTEGER) AS season,
            CAST(week AS INTEGER) AS week,
            {off_team} AS team,
            CAST(COALESCE(epa, 0) AS DOUBLE) AS epa,
            CASE WHEN COALESCE(fumble_lost, 0) = 1 THEN 1 ELSE 0 END AS fumble_lost
        FROM plays
        WHERE receiver_player_id IS NOT NULL
          AND COALESCE(pass_attempt, 0) = 1
          {two_pt_filter}
    ),
    skill AS (
        SELECT
            e.player_id,
            e.game_id,
            e.season,
            e.week,
            e.team,
            r.roster_group AS position_group,
            CAST(SUM(e.epa) - 2.0 * SUM(e.fumble_lost) AS DOUBLE) AS raw_score,
            CAST(COUNT(*) AS INTEGER) AS plays_counted,
            CAST(SUM(e.epa) AS DOUBLE) AS epa_total,
            CAST(SUM(e.fumble_lost) AS DOUBLE) AS turnovers,
            CAST(NULL AS DOUBLE) AS def_events_score,
            CAST(NULL AS DOUBLE) AS fg_points,
            CASE r.roster_group WHEN 'RB' THEN 2 WHEN 'WR' THEN 3 ELSE 4 END AS family_priority
        FROM skill_events e
        JOIN roster r ON r.player_id = e.player_id AND r.season = e.season
        WHERE r.roster_group IN ('RB', 'WR', 'TE')
        GROUP BY e.player_id, e.game_id, e.season, e.week, e.team, r.roster_group
    ),
    defense AS (
        {defense_sql}
    ),
    fg_rates AS (
        SELECT
            CASE
                WHEN kick_distance < 30 THEN '<30'
                WHEN kick_distance < 40 THEN '30-39'
                WHEN kick_distance < 50 THEN '40-49'
                ELSE '50+'
            END AS bucket,
            AVG(CASE WHEN field_goal_result = 'made' THEN 1.0 ELSE 0.0 END) AS expected_make
        FROM plays
        WHERE COALESCE(field_goal_attempt, 0) = 1
          AND kick_distance IS NOT NULL
          AND field_goal_result IS NOT NULL
        GROUP BY bucket
    ),
    kick_events AS (
        SELECT
            kicker_player_id AS player_id,
            game_id,
            CAST(season AS INTEGER) AS season,
            CAST(week AS INTEGER) AS week,
            {off_team} AS team,
            CAST((CASE
                WHEN field_goal_result = 'made' THEN 1.0 - COALESCE(fr.expected_make, 0.75)
                ELSE -COALESCE(fr.expected_make, 0.75)
            END) * 3.0 AS DOUBLE) AS points,
            1 AS kicks
        FROM plays p
        LEFT JOIN fg_rates fr ON fr.bucket = CASE
            WHEN p.kick_distance < 30 THEN '<30'
            WHEN p.kick_distance < 40 THEN '30-39'
            WHEN p.kick_distance < 50 THEN '40-49'
            ELSE '50+'
        END
        WHERE kicker_player_id IS NOT NULL
          AND COALESCE(field_goal_attempt, 0) = 1
          AND field_goal_result IS NOT NULL
        UNION ALL
        SELECT
            kicker_player_id AS player_id,
            game_id,
            CAST(season AS INTEGER) AS season,
            CAST(week AS INTEGER) AS week,
            {off_team} AS team,
            CAST(CASE WHEN extra_point_result = 'good' THEN 0.5 ELSE -1.0 END AS DOUBLE) AS points,
            1 AS kicks
        FROM plays
        WHERE kicker_player_id IS NOT NULL
          AND COALESCE(extra_point_attempt, 0) = 1
          AND extra_point_result IS NOT NULL
    ),
    kicking AS (
        SELECT
            k.player_id,
            k.game_id,
            k.season,
            k.week,
            k.team,
            'K' AS position_group,
            CAST(SUM(k.points) AS DOUBLE) AS raw_score,
            CAST(SUM(k.kicks) AS INTEGER) AS plays_counted,
            CAST(NULL AS DOUBLE) AS epa_total,
            CAST(NULL AS DOUBLE) AS turnovers,
            CAST(NULL AS DOUBLE) AS def_events_score,
            CAST(SUM(k.points) AS DOUBLE) AS fg_points,
            6 AS family_priority
        FROM kick_events k
        JOIN roster r ON r.player_id = k.player_id AND r.season = k.season
        WHERE r.roster_group = 'K'
        GROUP BY k.player_id, k.game_id, k.season, k.week, k.team
    ),
    candidates AS (
        SELECT * FROM qb_candidates
        UNION ALL SELECT * FROM skill
        UNION ALL SELECT * FROM defense
        UNION ALL SELECT * FROM kicking
    ),
    deduped AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY player_id, game_id
                   ORDER BY family_priority, plays_counted DESC, raw_score DESC
               ) AS rn
        FROM candidates
        WHERE player_id IS NOT NULL AND game_id IS NOT NULL
    ),
    eligible AS (
        SELECT *,
               PERCENT_RANK() OVER (PARTITION BY position_group ORDER BY raw_score) AS percentile
        FROM deduped
        WHERE rn = 1
          AND (
              (position_group = 'QB' AND plays_counted >= 10)
           OR (position_group IN ('RB', 'WR', 'TE') AND plays_counted >= 3)
           OR (position_group = 'DEF' AND raw_score > 0)
           OR (position_group = 'K' AND plays_counted >= 1)
          )
    )
    SELECT
        d.player_id,
        d.game_id,
        d.season,
        d.week,
        d.team,
        d.position_group,
        CASE
            WHEN e.percentile IS NULL THEN CAST(NULL AS DOUBLE)
            ELSE ROUND(GREATEST(3.0, LEAST(10.0, 3.0 + 7.0 * e.percentile)), 1)
        END AS rating,
        d.raw_score,
        d.plays_counted,
        d.epa_total,
        d.turnovers,
        d.def_events_score,
        d.fg_points
    FROM deduped d
    LEFT JOIN eligible e
      ON e.player_id = d.player_id
     AND e.game_id = d.game_id
     AND e.position_group = d.position_group
    WHERE d.rn = 1
    """


def materialize(season: int | None = None) -> int:
    """Full-rebuild all player-game ratings and return rows written.

    `season` is accepted for ingest API symmetry, but calibration is global,
    so the table is rebuilt across every loaded season.
    """
    del season
    with write_lock:
        conn = get_connection()
        ensure_table(conn)
        sql = _ratings_sql(conn)
        conn.execute("DELETE FROM player_game_ratings")
        try:
            conn.execute(f"""
                INSERT INTO player_game_ratings ({", ".join(_COLUMNS)})
                SELECT {", ".join(_COLUMNS)}
                FROM ({sql})
            """)
        except Exception as e:
            print(f"player_game_ratings materialize failed: {e}")
            return 0
        return conn.execute("SELECT COUNT(*) FROM player_game_ratings").fetchone()[0]


def read(game_id: str) -> list[dict]:
    try:
        return query_to_dict(
            """
            SELECT *
            FROM player_game_ratings
            WHERE game_id = ?
            ORDER BY rating DESC NULLS LAST, raw_score DESC NULLS LAST, player_id
            """,
            [game_id],
        )
    except Exception:
        return []


def read_or_materialize(game_id: str) -> list[dict]:
    rows = read(game_id)
    if rows:
        return rows
    if not write_lock.acquire(timeout=15):
        return []
    try:
        rows = read(game_id)
        if rows:
            return rows
        if materialize() > 0:
            return read(game_id)
        return []
    finally:
        write_lock.release()
