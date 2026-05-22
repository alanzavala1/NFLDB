"""Materialized team analytics: precompute per-season metrics into a table
so /team-analytics doesn't run a 150-line CTE on every request.

Design:
  - One row per (season, team) in `team_season_analytics`.
  - Schema mirrors what the CTE emits, plus a `season` column for filtering.
  - The original CTE remains the single source of truth — `_analytics_sql()`
    builds it for one season; `materialize()` writes the result to the table.
  - Endpoint hits the table; if a row is missing it lazily materializes
    so the system self-heals.
  - The ingest pipeline calls `materialize()` after a season finishes so
    freshly-loaded data is query-fast from the first request.
"""
import duckdb

from database import get_connection, query_to_dict


# ── Table schema ─────────────────────────────────────────────────────────────

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS team_season_analytics (
    season INTEGER NOT NULL,
    team   VARCHAR NOT NULL,
    games  INTEGER, wins INTEGER, losses INTEGER, ties INTEGER,
    pf_total INTEGER, pa_total INTEGER,

    ppg DOUBLE, papg DOUBLE, pt_diff_per_game DOUBLE,
    pts_per_drive DOUBLE, pts_per_drive_allowed DOUBLE,
    rz_td_pct DOUBLE, rz_td_pct_allowed DOUBLE,
    turnover_diff_per_game DOUBLE,
    off_turnovers_total INTEGER, def_takeaways_total INTEGER,
    total_drives INTEGER, total_drives_allowed INTEGER,

    off_plays_count INTEGER,
    off_epa_play DOUBLE, off_pass_epa DOUBLE, off_rush_epa DOUBLE,
    off_success_pct DOUBLE, off_explosive_pct DOUBLE, proe DOUBLE,
    third_down_pct DOUBLE,

    def_epa_play DOUBLE, def_pass_epa DOUBLE, def_rush_epa DOUBLE,
    def_success_pct DOUBLE, def_explosive_pct DOUBLE, def_sack_pct DOUBLE,
    third_down_stop_pct DOUBLE,

    ppg_rank INTEGER, pts_per_drive_rank INTEGER, off_epa_play_rank INTEGER,
    off_pass_epa_rank INTEGER, off_rush_epa_rank INTEGER,
    off_success_rank INTEGER, off_explosive_rank INTEGER,
    third_down_rank INTEGER, rz_td_rank INTEGER, proe_rank INTEGER,

    papg_rank INTEGER, pts_per_drive_allowed_rank INTEGER,
    def_epa_play_rank INTEGER, def_pass_epa_rank INTEGER,
    def_rush_epa_rank INTEGER, def_success_rank INTEGER,
    def_explosive_rank INTEGER, third_down_stop_rank INTEGER,
    rz_td_allowed_rank INTEGER, def_sack_rank INTEGER,

    pt_diff_rank INTEGER, to_diff_rank INTEGER,

    PRIMARY KEY (season, team)
)
"""


def ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Idempotent — safe to call on every ingest."""
    conn.execute(_TABLE_DDL)


# ── The big aggregation SQL (lifted from the old routers/teams.py CTE) ──────

def _analytics_sql(conn: duckdb.DuckDBPyConnection, season: int) -> str:
    """Build the per-season analytics CTE.

    Feature-detects optional plays columns (success, pass_oe, td_team,
    qb_kneel, qb_spike, two_point_attempt) and degrades gracefully when
    they're missing (e.g. very old seasons).
    """
    try:
        available = {r[0] for r in conn.execute("DESCRIBE plays").fetchall()}
    except Exception:
        available = set()

    has_success   = "success"           in available
    has_pass_oe   = "pass_oe"           in available
    has_td_team   = "td_team"           in available
    has_qb_kneel  = "qb_kneel"          in available
    has_qb_spike  = "qb_spike"          in available
    has_two_pt    = "two_point_attempt" in available

    play_filter = "play_type IN ('pass', 'run')"
    if has_qb_kneel: play_filter += " AND COALESCE(qb_kneel, 0) = 0"
    if has_qb_spike: play_filter += " AND COALESCE(qb_spike, 0) = 0"
    if has_two_pt:   play_filter += " AND COALESCE(two_point_attempt, 0) = 0"

    success_expr = "AVG(success)" if has_success else "AVG(CASE WHEN epa > 0 THEN 1.0 ELSE 0.0 END)"
    # pass_oe is already 100 * (pass - xpass), i.e. percentage points. Do not multiply by 100.
    proe_expr    = "AVG(pass_oe)" if has_pass_oe else "CAST(NULL AS DOUBLE)"

    # Offensive TD on a drive: the offense scored (excludes defensive TDs on turnovers)
    if has_td_team:
        off_td_expr = "MAX(CASE WHEN touchdown = 1 AND td_team = posteam THEN 1 ELSE 0 END)"
    else:
        off_td_expr = """MAX(CASE
            WHEN touchdown = 1
              AND COALESCE(interception, 0) = 0
              AND COALESCE(fumble_lost,   0) = 0
              AND (rush_attempt = 1 OR complete_pass = 1)
            THEN 1 ELSE 0 END)"""

    s = int(season)

    return f"""
    WITH
    off_plays AS (
        SELECT posteam AS team, game_id, drive, epa,
               pass_attempt, rush_attempt, sack, yards_gained,
               third_down_converted, third_down_failed
               {', success' if has_success else ''}
               {', pass_oe' if has_pass_oe else ''}
        FROM plays
        WHERE season = {s} AND season_type = 'REG'
          AND posteam IS NOT NULL
          AND {play_filter}
    ),
    def_plays AS (
        SELECT defteam AS team, game_id, epa,
               pass_attempt, rush_attempt, sack, yards_gained,
               third_down_converted, third_down_failed
               {', success' if has_success else ''}
        FROM plays
        WHERE season = {s} AND season_type = 'REG'
          AND defteam IS NOT NULL
          AND {play_filter}
    ),
    team_record AS (
        SELECT team,
               SUM(pf) AS pf_total, SUM(pa) AS pa_total,
               SUM(w) AS wins, SUM(l) AS losses, SUM(t) AS ties,
               COUNT(*) AS games
        FROM (
            SELECT away_team AS team, away_score AS pf, home_score AS pa,
                   CASE WHEN away_score > home_score THEN 1 ELSE 0 END AS w,
                   CASE WHEN away_score < home_score THEN 1 ELSE 0 END AS l,
                   CASE WHEN away_score = home_score THEN 1 ELSE 0 END AS t
            FROM schedules
            WHERE season = {s} AND game_type = 'REG' AND away_score IS NOT NULL
            UNION ALL
            SELECT home_team AS team, home_score AS pf, away_score AS pa,
                   CASE WHEN home_score > away_score THEN 1 ELSE 0 END AS w,
                   CASE WHEN home_score < away_score THEN 1 ELSE 0 END AS l,
                   CASE WHEN home_score = away_score THEN 1 ELSE 0 END AS t
            FROM schedules
            WHERE season = {s} AND game_type = 'REG' AND home_score IS NOT NULL
        )
        GROUP BY team
    ),
    off_drives AS (
        SELECT posteam AS team, game_id, drive,
               MAX(CASE WHEN COALESCE(yardline_100, 999) <= 20 THEN 1 ELSE 0 END) AS reached_rz,
               {off_td_expr} AS scored_td,
               SUM(CASE WHEN play_type IN ('pass', 'run') THEN 1 ELSE 0 END) AS scrimmage_plays
        FROM plays
        WHERE season = {s} AND season_type = 'REG'
          AND posteam IS NOT NULL AND drive IS NOT NULL
        GROUP BY posteam, game_id, drive
        HAVING SUM(CASE WHEN play_type IN ('pass', 'run') THEN 1 ELSE 0 END) >= 1
    ),
    def_drives AS (
        SELECT defteam AS team, game_id, drive,
               MAX(CASE WHEN COALESCE(yardline_100, 999) <= 20 THEN 1 ELSE 0 END) AS allowed_rz,
               {off_td_expr} AS allowed_td
        FROM plays
        WHERE season = {s} AND season_type = 'REG'
          AND defteam IS NOT NULL AND drive IS NOT NULL
        GROUP BY defteam, game_id, drive
        HAVING SUM(CASE WHEN play_type IN ('pass', 'run') THEN 1 ELSE 0 END) >= 1
    ),
    off_drive_agg AS (
        SELECT team,
               COUNT(*) AS total_drives,
               SUM(reached_rz) AS rz_trips,
               SUM(CASE WHEN reached_rz = 1 AND scored_td = 1 THEN 1 ELSE 0 END) AS rz_tds
        FROM off_drives GROUP BY team
    ),
    def_drive_agg AS (
        SELECT team,
               COUNT(*) AS total_drives_allowed,
               SUM(allowed_rz) AS rz_trips_allowed,
               SUM(CASE WHEN allowed_rz = 1 AND allowed_td = 1 THEN 1 ELSE 0 END) AS rz_tds_allowed
        FROM def_drives GROUP BY team
    ),
    off_turnovers AS (
        SELECT posteam AS team,
               SUM(CASE WHEN COALESCE(interception, 0) = 1 OR COALESCE(fumble_lost, 0) = 1 THEN 1 ELSE 0 END) AS turnovers
        FROM plays
        WHERE season = {s} AND season_type = 'REG'
          AND posteam IS NOT NULL
          AND play_type IN ('pass', 'run')
        GROUP BY posteam
    ),
    def_takeaways AS (
        SELECT defteam AS team,
               SUM(CASE WHEN COALESCE(interception, 0) = 1 OR COALESCE(fumble_lost, 0) = 1 THEN 1 ELSE 0 END) AS takeaways
        FROM plays
        WHERE season = {s} AND season_type = 'REG'
          AND defteam IS NOT NULL
          AND play_type IN ('pass', 'run')
        GROUP BY defteam
    ),
    off_agg AS (
        SELECT team,
            COUNT(*) AS off_plays_count,
            AVG(epa)                                                  AS off_epa_play,
            AVG(epa) FILTER (WHERE pass_attempt = 1 OR sack = 1)      AS off_pass_epa,
            AVG(epa) FILTER (WHERE rush_attempt = 1)                  AS off_rush_epa,
            100.0 * {success_expr}                                    AS off_success_pct,
            100.0 * AVG(CASE
                WHEN (pass_attempt = 1 AND yards_gained >= 20)
                  OR (rush_attempt = 1 AND yards_gained >= 10)
                THEN 1.0 ELSE 0.0 END)                                AS off_explosive_pct,
            {proe_expr}                                               AS proe,
            100.0 * SUM(third_down_converted)
                  / NULLIF(SUM(third_down_converted) + SUM(third_down_failed), 0) AS third_down_pct
        FROM off_plays GROUP BY team
    ),
    def_agg AS (
        SELECT team,
            AVG(epa)                                                  AS def_epa_play,
            AVG(epa) FILTER (WHERE pass_attempt = 1 OR sack = 1)      AS def_pass_epa,
            AVG(epa) FILTER (WHERE rush_attempt = 1)                  AS def_rush_epa,
            100.0 * {success_expr}                                    AS def_success_pct,
            100.0 * AVG(CASE
                WHEN (pass_attempt = 1 AND yards_gained >= 20)
                  OR (rush_attempt = 1 AND yards_gained >= 10)
                THEN 1.0 ELSE 0.0 END)                                AS def_explosive_pct,
            100.0 * SUM(CASE WHEN sack = 1 THEN 1 ELSE 0 END)
                  / NULLIF(SUM(CASE WHEN pass_attempt = 1 OR sack = 1 THEN 1 ELSE 0 END), 0) AS def_sack_pct,
            100.0 * SUM(third_down_failed)
                  / NULLIF(SUM(third_down_converted) + SUM(third_down_failed), 0) AS third_down_stop_pct
        FROM def_plays GROUP BY team
    ),
    combined AS (
        SELECT
            tr.team, tr.games, tr.wins, tr.losses, tr.ties,
            tr.pf_total, tr.pa_total,
            tr.pf_total::DOUBLE / NULLIF(tr.games, 0)                     AS ppg,
            tr.pa_total::DOUBLE / NULLIF(tr.games, 0)                     AS papg,
            (tr.pf_total - tr.pa_total)::DOUBLE / NULLIF(tr.games, 0)     AS pt_diff_per_game,
            tr.pf_total::DOUBLE / NULLIF(od.total_drives, 0)              AS pts_per_drive,
            tr.pa_total::DOUBLE / NULLIF(dd.total_drives_allowed, 0)      AS pts_per_drive_allowed,
            100.0 * od.rz_tds       / NULLIF(od.rz_trips, 0)              AS rz_td_pct,
            100.0 * dd.rz_tds_allowed / NULLIF(dd.rz_trips_allowed, 0)    AS rz_td_pct_allowed,
            (COALESCE(dt.takeaways, 0) - COALESCE(ot.turnovers, 0))::DOUBLE
                  / NULLIF(tr.games, 0)                                   AS turnover_diff_per_game,
            COALESCE(ot.turnovers, 0)  AS off_turnovers_total,
            COALESCE(dt.takeaways, 0)  AS def_takeaways_total,
            od.total_drives, dd.total_drives_allowed,
            oa.off_plays_count,
            oa.off_epa_play, oa.off_pass_epa, oa.off_rush_epa,
            oa.off_success_pct, oa.off_explosive_pct, oa.proe,
            oa.third_down_pct,
            da.def_epa_play, da.def_pass_epa, da.def_rush_epa,
            da.def_success_pct, da.def_explosive_pct, da.def_sack_pct,
            da.third_down_stop_pct
        FROM team_record tr
        LEFT JOIN off_agg       oa USING (team)
        LEFT JOIN def_agg       da USING (team)
        LEFT JOIN off_drive_agg od USING (team)
        LEFT JOIN def_drive_agg dd USING (team)
        LEFT JOIN off_turnovers ot USING (team)
        LEFT JOIN def_takeaways dt USING (team)
    )
    SELECT
        c.team, c.games, c.wins, c.losses, c.ties,
        c.pf_total, c.pa_total,
        c.ppg, c.papg, c.pt_diff_per_game,
        c.pts_per_drive, c.pts_per_drive_allowed,
        c.rz_td_pct, c.rz_td_pct_allowed,
        c.turnover_diff_per_game,
        c.off_turnovers_total, c.def_takeaways_total,
        c.total_drives, c.total_drives_allowed,
        c.off_plays_count,
        c.off_epa_play, c.off_pass_epa, c.off_rush_epa,
        c.off_success_pct, c.off_explosive_pct, c.proe,
        c.third_down_pct,
        c.def_epa_play, c.def_pass_epa, c.def_rush_epa,
        c.def_success_pct, c.def_explosive_pct, c.def_sack_pct,
        c.third_down_stop_pct,
        -- Offense ranks (higher = better → DESC)
        RANK() OVER (ORDER BY c.ppg                  DESC NULLS LAST) AS ppg_rank,
        RANK() OVER (ORDER BY c.pts_per_drive        DESC NULLS LAST) AS pts_per_drive_rank,
        RANK() OVER (ORDER BY c.off_epa_play         DESC NULLS LAST) AS off_epa_play_rank,
        RANK() OVER (ORDER BY c.off_pass_epa         DESC NULLS LAST) AS off_pass_epa_rank,
        RANK() OVER (ORDER BY c.off_rush_epa         DESC NULLS LAST) AS off_rush_epa_rank,
        RANK() OVER (ORDER BY c.off_success_pct      DESC NULLS LAST) AS off_success_rank,
        RANK() OVER (ORDER BY c.off_explosive_pct    DESC NULLS LAST) AS off_explosive_rank,
        RANK() OVER (ORDER BY c.third_down_pct       DESC NULLS LAST) AS third_down_rank,
        RANK() OVER (ORDER BY c.rz_td_pct            DESC NULLS LAST) AS rz_td_rank,
        RANK() OVER (ORDER BY c.proe                 DESC NULLS LAST) AS proe_rank,
        -- Defense ranks (lower = better → ASC, so rank 1 = best defense)
        RANK() OVER (ORDER BY c.papg                  ASC  NULLS LAST) AS papg_rank,
        RANK() OVER (ORDER BY c.pts_per_drive_allowed ASC  NULLS LAST) AS pts_per_drive_allowed_rank,
        RANK() OVER (ORDER BY c.def_epa_play          ASC  NULLS LAST) AS def_epa_play_rank,
        RANK() OVER (ORDER BY c.def_pass_epa          ASC  NULLS LAST) AS def_pass_epa_rank,
        RANK() OVER (ORDER BY c.def_rush_epa          ASC  NULLS LAST) AS def_rush_epa_rank,
        RANK() OVER (ORDER BY c.def_success_pct       ASC  NULLS LAST) AS def_success_rank,
        RANK() OVER (ORDER BY c.def_explosive_pct     ASC  NULLS LAST) AS def_explosive_rank,
        RANK() OVER (ORDER BY c.third_down_stop_pct   DESC NULLS LAST) AS third_down_stop_rank,
        RANK() OVER (ORDER BY c.rz_td_pct_allowed     ASC  NULLS LAST) AS rz_td_allowed_rank,
        RANK() OVER (ORDER BY c.def_sack_pct          DESC NULLS LAST) AS def_sack_rank,
        -- Overall
        RANK() OVER (ORDER BY c.pt_diff_per_game     DESC NULLS LAST) AS pt_diff_rank,
        RANK() OVER (ORDER BY c.turnover_diff_per_game DESC NULLS LAST) AS to_diff_rank
    FROM combined c
    WHERE c.team IS NOT NULL
    ORDER BY c.team
    """


# ── Materialize + read API ───────────────────────────────────────────────────

def materialize(season: int) -> int:
    """Compute analytics for one season and persist to the table.

    Returns the number of rows written. Safe to call repeatedly — DELETE
    + INSERT replaces any existing rows for the season.
    """
    conn = get_connection()
    ensure_table(conn)

    sql = _analytics_sql(conn, season)
    s = int(season)

    conn.execute("DELETE FROM team_season_analytics WHERE season = ?", [s])
    try:
        conn.execute(
            f"INSERT INTO team_season_analytics SELECT {s} AS season, * FROM ({sql})"
        )
    except Exception as e:
        print(f"team-analytics materialize failed for season {s}: {e}")
        return 0

    return conn.execute(
        "SELECT COUNT(*) FROM team_season_analytics WHERE season = ?", [s]
    ).fetchone()[0]


def read(season: int) -> list[dict]:
    """Read the materialized rows for a season. Returns [] if none exist."""
    try:
        return query_to_dict(
            "SELECT * EXCLUDE (season) FROM team_season_analytics WHERE season = ? ORDER BY team",
            [int(season)],
        )
    except Exception:
        return []


def read_or_materialize(season: int) -> list[dict]:
    """Endpoint entry point: read from table; lazily materialize if empty.

    This is what makes the system self-healing: if the table is missing
    (fresh DB, or migrated without ingest), the first request computes
    and persists for subsequent ones.
    """
    rows = read(season)
    if rows:
        return rows
    if materialize(season) > 0:
        return read(season)
    return []
