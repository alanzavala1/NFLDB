"""Materialized player splits: the player's full stat line, conditioned on a
single situational dimension (down, pass depth, run gap, game script, ...).

Design (mirrors team_analytics_builder / comparables_builder):
  - One LONG-format table `player_splits`: one row per
    (player_id, season, category, split_dim, split_value).
  - A "split" is not a separate dataset — it's the same per-play data the
    main stat line comes from, aggregated under a condition. So overall
    always reconciles with the sum of its splits.
  - `materialize(season)` recomputes every player's splits for one season
    (called from ingest). The endpoint reads per player; if a player has no
    rows it lazily materializes their seasons, so the system self-heals.

Three categories share one table via the `category` column:
  - passing   — QBs, keyed off passer_player_id
  - rushing   — ball carriers, keyed off rusher_player_id
  - receiving — pass catchers, keyed off receiver_player_id
The metric columns are shared and category-overloaded (att = attempts /
carries / targets; cmp = completions / receptions; NULL where N/A).
"""
import duckdb

import splits_core as core
from config import DIVISIONS
from database import get_connection, query_to_dict

# Per-category minimum volume in a season for a player to be included — keeps
# trick plays and one-off backups out of the table.
_MIN_VOLUME = {"passing": 50, "rushing": 25, "receiving": 25}


_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS player_splits (
    player_id   VARCHAR NOT NULL,
    season      INTEGER NOT NULL,
    category    VARCHAR NOT NULL,   -- 'passing' | 'rushing' | 'receiving'
    split_dim   VARCHAR NOT NULL,
    split_value VARCHAR NOT NULL,
    sort_order  INTEGER,
    att           INTEGER,          -- attempts / carries / targets
    cmp           INTEGER,          -- completions / receptions (NULL for rushing)
    yards         INTEGER,
    td            INTEGER,
    interceptions INTEGER,          -- passing only
    air_yards     INTEGER,          -- passing / receiving
    yac           INTEGER,          -- passing / receiving
    first_downs   INTEGER,          -- plays that gained a first down / TD
    epa           DOUBLE,
    success_pct   DOUBLE,
    cpoe          DOUBLE,           -- passing only
    PRIMARY KEY (player_id, season, category, split_dim, split_value)
)
"""

_COLUMNS = ("player_id", "season", "category", "split_dim", "split_value",
            "sort_order", "att", "cmp", "yards", "td", "interceptions",
            "air_yards", "yac", "first_downs", "epa", "success_pct", "cpoe")


def ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Idempotent — safe to call on every ingest. Adds columns introduced
    after the initial ship so existing DBs evolve without a full rebuild."""
    conn.execute(_TABLE_DDL)
    existing = {r[1] for r in conn.execute("PRAGMA table_info(player_splits)").fetchall()}
    if "yac" not in existing:
        conn.execute("ALTER TABLE player_splits ADD COLUMN yac INTEGER")
    if "first_downs" not in existing:
        conn.execute("ALTER TABLE player_splits ADD COLUMN first_downs INTEGER")


# ── Dimension definitions ────────────────────────────────────────────────────
# Common dims + feature helpers live in splits_core; here we add the
# category-specific lead dimensions (depth/direction/gap).

_COMMON_DIMS = [core.DOWN_DIM, core.game_script_dim(1), core.QUARTER_DIM,
                core.SHOTGUN_DIM, core.FIELD_ZONE_DIM, core.HOME_AWAY_DIM,
                core.ROOF_DIM, core.SURFACE_DIM, core.NO_HUDDLE_DIM]


def _opponent_dims() -> list[tuple[str, str, str, str]]:
    """Opponent (defteam) and the opponent's division. DIVISIONS maps current
    AND historical abbreviations, so relocated teams (OAK/LV, SD/LAC, …) bucket
    correctly across 27 seasons."""
    order = ["AFC East", "AFC North", "AFC South", "AFC West",
             "NFC East", "NFC North", "NFC South", "NFC West"]
    div_when = " ".join(f"WHEN '{t}' THEN '{d}'" for t, d in DIVISIONS.items())
    div_sort_when = " ".join(f"WHEN '{t}' THEN {order.index(d) + 1}" for t, d in DIVISIONS.items())
    div_expr = f"CASE defteam {div_when} END"
    div_sort = f"CASE defteam {div_sort_when} END"
    return [
        # opponent has no natural integer order — sort_order NULL; the frontend
        # orders these rows by volume (most-faced first).
        ("opponent", "defteam", "CAST(NULL AS INTEGER)", "defteam IS NOT NULL"),
        ("opp_division", div_expr, div_sort, "defteam IS NOT NULL"),
    ]


_OPPONENT_DIMS = _opponent_dims()


def _category_dims(category: str) -> list[tuple[str, str, str, str]]:
    if category == "passing":
        lead = [("pass_depth", *core.DEPTH), ("pass_location", *core.PASS_DIR), core.PRESSURE_DIM]
    elif category == "rushing":
        lead = [
            ("run_gap", "run_gap", "CASE run_gap WHEN 'guard' THEN 1 WHEN 'tackle' THEN 2 WHEN 'end' THEN 3 END", "run_gap IS NOT NULL"),
            ("run_direction", *core.RUN_DIR),
        ]
    else:  # receiving
        lead = [("target_depth", *core.DEPTH), ("target_direction", *core.PASS_DIR), core.PRESSURE_DIM]
    return lead + _COMMON_DIMS + _OPPONENT_DIMS


# ── Per-category SQL ──────────────────────────────────────────────────────────

def _base_and_metrics(category: str, success_col: str) -> tuple[str, str]:
    """Return (base_select, metric_select) for a category. base_select feeds
    the `base` CTE; metric_select is the aggregation projection in each block."""
    if category == "passing":
        base = f"""
            passer_player_id AS player_id, defteam,
            down, pass_length, pass_location, score_differential, qtr, shotgun,
            yardline_100, posteam_type, first_down,
            qb_hit, roof, surface, no_huddle,
            complete_pass, passing_yards, pass_touchdown, interception,
            air_yards, yards_after_catch, epa, cpoe, {success_col}
        FROM plays
        WHERE {core.PASS_ATTEMPT} AND passer_player_id IS NOT NULL"""
        metrics = """
            COUNT(*)                          AS att,
            SUM(complete_pass)                AS cmp,
            SUM(COALESCE(passing_yards, 0))   AS yards,
            SUM(pass_touchdown)               AS td,
            SUM(interception)                 AS interceptions,
            SUM(COALESCE(air_yards, 0))       AS air_yards,
            SUM(COALESCE(yards_after_catch, 0)) AS yac,
            SUM(COALESCE(first_down, 0))      AS first_downs,
            ROUND(AVG(epa), 4)                AS epa,
            ROUND(100.0 * AVG(success), 1)    AS success_pct,
            ROUND(AVG(cpoe), 2)               AS cpoe"""
    elif category == "rushing":
        base = f"""
            rusher_player_id AS player_id, defteam,
            down, run_gap, run_location, score_differential, qtr, shotgun,
            yardline_100, posteam_type, first_down,
            roof, surface, no_huddle,
            rushing_yards, rush_touchdown, epa, {success_col}
        FROM plays
        WHERE rush_attempt = 1 AND rusher_player_id IS NOT NULL"""
        metrics = """
            COUNT(*)                       AS att,
            CAST(NULL AS BIGINT)           AS cmp,
            SUM(COALESCE(rushing_yards, 0)) AS yards,
            SUM(rush_touchdown)            AS td,
            CAST(NULL AS BIGINT)           AS interceptions,
            CAST(NULL AS BIGINT)           AS air_yards,
            CAST(NULL AS BIGINT)           AS yac,
            SUM(COALESCE(first_down, 0))   AS first_downs,
            ROUND(AVG(epa), 4)             AS epa,
            ROUND(100.0 * AVG(success), 1) AS success_pct,
            CAST(NULL AS DOUBLE)           AS cpoe"""
    else:  # receiving
        base = f"""
            receiver_player_id AS player_id, defteam,
            down, pass_length, pass_location, score_differential, qtr, shotgun,
            yardline_100, posteam_type, first_down,
            qb_hit, roof, surface, no_huddle,
            complete_pass, receiving_yards, pass_touchdown,
            air_yards, yards_after_catch, epa, {success_col}
        FROM plays
        WHERE {core.PASS_ATTEMPT} AND receiver_player_id IS NOT NULL"""
        metrics = """
            COUNT(*)                            AS att,
            SUM(complete_pass)                  AS cmp,
            SUM(COALESCE(receiving_yards, 0))   AS yards,
            SUM(pass_touchdown)                 AS td,
            CAST(NULL AS BIGINT)                AS interceptions,
            SUM(COALESCE(air_yards, 0))         AS air_yards,
            SUM(COALESCE(yards_after_catch, 0)) AS yac,
            SUM(COALESCE(first_down, 0))        AS first_downs,
            ROUND(AVG(epa), 4)                  AS epa,
            ROUND(100.0 * AVG(success), 1)      AS success_pct,
            CAST(NULL AS DOUBLE)                AS cpoe"""
    return base, metrics


def _category_sql(category: str, season: int, available: set[str]) -> str:
    """Long-format splits SELECT for one category + season."""
    s = int(season)
    min_vol = _MIN_VOLUME[category]

    base_select, metric_select = _base_and_metrics(category, core.success_col(available))
    union = core.union_blocks(_category_dims(category), metric_select, "player_id")

    return f"""
    WITH base AS (
        SELECT {base_select}
          AND season = {s} AND season_type = 'REG'
          {core.two_pt_filter(available)}
    ),
    qualified AS (
        SELECT player_id FROM base GROUP BY player_id HAVING COUNT(*) >= {min_vol}
    ),
    b AS (
        SELECT base.* FROM base JOIN qualified USING (player_id)
    )
    {union}
    """


# ── Materialize + read API ───────────────────────────────────────────────────

def materialize(season: int) -> int:
    """Compute all-category splits for one season and persist. Returns rows written."""
    conn = get_connection()
    ensure_table(conn)
    s = int(season)

    try:
        available = {r[0] for r in conn.execute("DESCRIBE plays").fetchall()}
    except Exception:
        available = set()

    conn.execute("DELETE FROM player_splits WHERE season = ?", [s])
    cols = ", ".join(_COLUMNS)
    for category in ("passing", "rushing", "receiving"):
        sql = _category_sql(category, s, available)
        try:
            conn.execute(f"""
                INSERT INTO player_splits ({cols})
                SELECT player_id, {s} AS season, '{category}' AS category,
                       split_dim, split_value, sort_order,
                       att, cmp, yards, td, interceptions, air_yards, yac,
                       first_downs, epa, success_pct, cpoe
                FROM ({sql})
            """)
        except Exception as e:
            print(f"player_splits[{category}] materialize failed for season {s}: {e}")

    return conn.execute(
        "SELECT COUNT(*) FROM player_splits WHERE season = ?", [s]
    ).fetchone()[0]


def read(player_id: str) -> list[dict]:
    """All split rows for a player, newest season first."""
    try:
        return query_to_dict("""
            SELECT season, category, split_dim, split_value, sort_order,
                   att, cmp, yards, td, interceptions, air_yards, yac,
                   first_downs, epa, success_pct, cpoe
            FROM player_splits
            WHERE player_id = ?
            ORDER BY season DESC, category, split_dim, sort_order
        """, [player_id])
    except Exception:
        return []


def read_or_materialize(player_id: str) -> list[dict]:
    """Endpoint entry point: read; if the player has no rows, lazily build the
    seasons they appear in, then re-read. Self-heals a cold table."""
    rows = read(player_id)
    if rows:
        return rows
    try:
        seasons = [r["season"] for r in query_to_dict("""
            SELECT DISTINCT season FROM plays
            WHERE passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?
        """, [player_id, player_id, player_id])]
    except Exception:
        seasons = []
    if not seasons:
        return []
    for s in seasons:
        materialize(s)
    return read(player_id)
