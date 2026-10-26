"""Materialized player splits: the player's full stat line, conditioned on a
single situational dimension (down, pass depth, run gap, game script, ...).

Design (mirrors team_analytics_builder / comparables_builder):
  - One LONG-format table `player_splits`: one row per
    (player_id, season, category, split_dim, split_value).
  - A split groups a classified play population. Missing context can exclude
    production, so whole receiving references and coverage are stored separately.
  - `materialize(season)` recomputes every player's splits for one season
    (called from ingest). The endpoint reads per player; if a player has no
    rows it lazily materializes their seasons, so the system self-heals.

Three categories share one table via the `category` column:
  - passing   — QBs, keyed off passer_player_id
  - rushing   — ball carriers, keyed off rusher_player_id
  - receiving — official recipient credits in captured-input builds; original
    receiver attempt plays still determine the existing admission threshold
The metric columns are shared and category-overloaded (att = attempts /
carries / targets; cmp = completions / receptions; NULL where N/A).
"""
from data_errors import is_missing_data_error
import duckdb

import splits_core as core
from config import DIVISIONS, era_team_case
from database import get_connection, query_to_dict, write_lock

# plays labels every season with the modern franchise abbreviation; opponent
# split values should show the era one ('vs OAK', not 'vs LV', in 2005).
# plays-qualified because the passing base LEFT JOINs ftn_charting.
_ERA_DEFTEAM = era_team_case("plays.defteam", "plays.season")

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

_COLUMNS = core.PLAYER_COLUMNS


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
                core.ROOF_DIM, core.SURFACE_DIM, core.NO_HUDDLE_DIM,
                core.GAME_STATE_DIM]


def _opponent_dims() -> list[tuple[str, str, str, str]]:
    """Opponent and current-franchise division, including historical aliases.

    This preserves current division membership for old seasons; it does not
    reconstruct pre-2002 alignment.
    """
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


def _category_dims(category: str, has_ftn: bool = False) -> list[tuple[str, str, str, str]]:
    if category == "passing":
        lead = [("pass_depth", *core.DEPTH), ("pass_location", *core.PASS_DIR), core.PRESSURE_DIM]
        if has_ftn:
            lead += [core.PLAY_ACTION_DIM, core.BLITZ_DIM]
    elif category == "rushing":
        lead = [
            ("run_gap", "run_gap", "CASE run_gap WHEN 'guard' THEN 1 WHEN 'tackle' THEN 2 WHEN 'end' THEN 3 END", "run_gap IS NOT NULL"),
            ("run_direction", *core.RUN_DIR),
        ]
        if has_ftn:
            lead += [core.BOX_DIM]
    else:  # receiving
        lead = [("target_depth", *core.DEPTH), ("target_direction", *core.PASS_DIR), core.PRESSURE_DIM]
        if has_ftn:
            lead += [core.PLAY_ACTION_DIM, core.BLITZ_DIM]
    return lead + _COMMON_DIMS + _OPPONENT_DIMS


# ── Per-category SQL ──────────────────────────────────────────────────────────

def _base_source(category: str, has_ftn: bool = False) -> str:
    """One source predicate for both complete split rows and admission-only SQL."""
    ftn_join = ("LEFT JOIN ftn_charting f ON plays.game_id = f.game_id AND plays.play_id = f.play_id"
                if has_ftn else "")
    condition = {
        "passing": "(pass_attempt = 1 OR COALESCE(sack, 0) = 1) AND passer_player_id IS NOT NULL",
        "rushing": "rush_attempt = 1 AND rusher_player_id IS NOT NULL",
        "receiving": f"{core.PASS_ATTEMPT} AND receiver_player_id IS NOT NULL",
    }[category]
    return f"FROM plays {ftn_join} WHERE {condition}"


def _base_and_metrics(category: str, success_col: str, has_ftn: bool = False) -> tuple[str, str]:
    """Return (base_select, metric_select) for a category. base_select feeds
    the `base` CTE; metric_select is the aggregation projection in each block.
    When has_ftn, the per-play FTN charting columns are joined in (2022+)."""
    # FTN charting (play-action, pass-rush count, box count) lives in its own
    # table joined by game_id + play_id; null for pre-2022 / unmatched plays.
    ftn_cols = "is_play_action, n_pass_rushers, n_defense_box," if has_ftn else ""
    if category == "passing":
        # Keep the dropback base for official counting stats (older valid
        # attempts can lack play_type). Filter only the EPA numerator to the
        # provider's pass/qb_spike play types, using `qb_epa` to reproduce EPA that
        # Leaders/Player show (provider-selected qb_epa divided by attempts). All
        # counting metrics stay attempt-only (att = comp/incomp/int) via FILTER;
        # sack rows contribute only their qb_epa to the EPA numerator.
        #
        # Two-point conversion dropbacks carry no `down`, so every split
        # dimension keyed on down excludes them by construction. That is not a
        # bug, but it is the reason splits EPA is a subtotal rather than a
        # season total — see test_passing_epa_matches_leaders_definition, which
        # has to add them back to compare against the official weekly figure.
        base = f"""
            passer_player_id AS player_id, {_ERA_DEFTEAM} AS defteam,
            down, pass_length, pass_location, score_differential, qtr, shotgun,
            yardline_100, posteam_type, first_down,
            qb_hit, roof, surface, no_huddle, wp, {ftn_cols}
            complete_pass, incomplete_pass, interception, sack, play_type,
            passing_yards, pass_touchdown,
            air_yards, yards_after_catch, epa, qb_epa, cpoe, {success_col}
        {_base_source(category, has_ftn)}"""
        metrics = f"""
            COUNT(*) FILTER (WHERE {core.PASS_ATTEMPT})        AS att,
            SUM(complete_pass)                AS cmp,
            SUM(COALESCE(passing_yards, 0))   AS yards,
            SUM(pass_touchdown)               AS td,
            SUM(interception)                 AS interceptions,
            SUM(COALESCE(air_yards, 0))       AS air_yards,
            SUM(COALESCE(yards_after_catch, 0)) AS yac,
            SUM(COALESCE(first_down, 0)) FILTER (WHERE {core.PASS_ATTEMPT}) AS first_downs,
            ROUND(SUM(qb_epa) FILTER (WHERE {core.PASSING_EPA_PLAY}) /
                  NULLIF(COUNT(*) FILTER (WHERE {core.PASS_ATTEMPT}), 0), 4) AS epa,
            ROUND(100.0 * AVG(success) FILTER (WHERE {core.PASS_ATTEMPT}), 1) AS success_pct,
            ROUND(AVG(cpoe), 2)               AS cpoe"""
    elif category == "rushing":
        base = f"""
            rusher_player_id AS player_id, {_ERA_DEFTEAM} AS defteam,
            down, run_gap, run_location, score_differential, qtr, shotgun,
            yardline_100, posteam_type, first_down,
            roof, surface, no_huddle, wp, {ftn_cols}
            rushing_yards, rush_touchdown, epa, {success_col}
        {_base_source(category, has_ftn)}"""
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
            receiver_player_id AS player_id, {_ERA_DEFTEAM} AS defteam,
            down, pass_length, pass_location, score_differential, qtr, shotgun,
            yardline_100, posteam_type, first_down,
            qb_hit, roof, surface, no_huddle, wp, {ftn_cols}
            complete_pass, receiving_yards, pass_touchdown,
            air_yards, yards_after_catch, epa, {success_col}
        {_base_source(category, has_ftn)}"""
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


def _ftn_available(conn) -> bool:
    """True if the FTN charting table exists (so the builder can join it)."""
    try:
        return any(r[0] == "ftn_charting" for r in conn.execute("SHOW TABLES").fetchall())
    except Exception as _data_error:
        if not is_missing_data_error(_data_error):
            raise
        return False


def qualification_ctes(category: str, season: int, available: set[str], has_ftn: bool = False,
                       *, minimal: bool = False) -> str:
    """Shared admission; minimal mode needs only identity and eligibility fields.

    The normal base retains metric/context columns for split materialization.
    Both modes use the same source predicate, season/scope and volume threshold.
    """
    if minimal:
        identity = {"passing": "passer_player_id", "rushing": "rusher_player_id",
                    "receiving": "receiver_player_id"}[category]
        base_select = f"{identity} AS player_id {_base_source(category, has_ftn)}"
    else:
        base_select, _ = _base_and_metrics(category, core.success_col(available), has_ftn)
    return f"""
    WITH base AS (
        SELECT {base_select}
          AND plays.season = {int(season)} AND plays.season_type = 'REG'
          {core.two_pt_filter(available)}
    ),
    qualified AS (
        SELECT player_id FROM base GROUP BY player_id HAVING COUNT(*) >= {_MIN_VOLUME[category]}
    )
    """


def _category_sql(category: str, season: int, available: set[str], has_ftn: bool = False) -> str:
    """Long-format splits SELECT for one category + season."""
    _, metric_select = _base_and_metrics(category, core.success_col(available), has_ftn)
    union = core.union_blocks(_category_dims(category, has_ftn), metric_select, "player_id")
    return f"""
    {qualification_ctes(category, season, available, has_ftn)},
    b AS (
        SELECT base.* FROM base JOIN qualified USING (player_id)
    )
    {union}
    """


# ── Materialize + read API ───────────────────────────────────────────────────

def materialize(season: int, *, receiving_inputs=None) -> int:
    """Compute all-category splits for one season and persist. Returns rows written.

    Holds the write lock: called from the ingest worker (which already owns it)
    and from lazy request-thread materialization (which must wait its turn).
    Captured inputs select official receiving with atomic coverage/reference
    writes. Input-free compatibility builds cannot overwrite an official snapshot.
    """
    with write_lock:
        return _materialize_locked(int(season), receiving_inputs=receiving_inputs)


def _materialize_locked(s: int, *, receiving_inputs=None) -> int:
    conn = get_connection()
    from pipeline.receiving_build import has_official_receiving, prepare_receiving, store_receiving
    if receiving_inputs is None and has_official_receiving(conn):
        raise RuntimeError("Official receiving splits require captured offline inputs; legacy rebuilding is disabled")
    prepared = prepare_receiving(conn, s, receiving_inputs) if receiving_inputs is not None else None
    ensure_table(conn)

    try:
        available = {r[0] for r in conn.execute("DESCRIBE plays").fetchall()}
    except Exception as _data_error:
        if not is_missing_data_error(_data_error):
            raise
        available = set()
    has_ftn = _ftn_available(conn)

    if prepared is not None:
        conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM player_splits WHERE season = ?", [s])
        cols = ", ".join(_COLUMNS)
        categories = ("passing", "rushing") if prepared is not None else ("passing", "rushing", "receiving")
        for category in categories:
            sql = _category_sql(category, s, available, has_ftn)
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
                if prepared is not None or not is_missing_data_error(e):
                    raise
                print(f"player_splits[{category}] materialize failed for season {s}: {e}")
        if prepared is not None:
            store_receiving(conn, s, prepared)
            conn.execute("COMMIT")
    except BaseException:
        if prepared is not None:
            conn.execute("ROLLBACK")
        raise

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
    except Exception as _data_error:
        if not is_missing_data_error(_data_error):
            raise
        return []


def read_or_materialize(player_id: str) -> list[dict]:
    """Endpoint entry point: read; if the player has no rows, lazily build any
    of their seasons that were never materialized, then re-read.

    Two guards keep this cheap and safe:
      - Only seasons absent from player_splits are built. A season that's
        already materialized but has no rows for this player means the player
        didn't meet the volume floor — rebuilding wouldn't change that.
      - Building takes the write lock (bounded wait, then give up and return
        empty rather than hang the request behind a long ingest) and re-reads
        after acquiring, since a concurrent request may have built the same
        seasons while we waited.
    """
    rows = read(player_id)
    if rows:
        return rows
    try:
        seasons = {r["season"] for r in query_to_dict("""
            SELECT DISTINCT season FROM plays
            WHERE passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?
        """, [player_id, player_id, player_id])}
    except Exception as _data_error:
        if not is_missing_data_error(_data_error):
            raise
        seasons = set()
    if not seasons:
        return []
    if not write_lock.acquire(timeout=15):
        return []
    try:
        rows = read(player_id)
        if rows:
            return rows
        try:
            built = {r["season"] for r in query_to_dict(
                "SELECT DISTINCT season FROM player_splits")}
        except Exception as _data_error:
            if not is_missing_data_error(_data_error):
                raise
            built = set()
        for s in sorted(seasons - built, reverse=True):
            materialize(s)
    finally:
        write_lock.release()
    return read(player_id)
