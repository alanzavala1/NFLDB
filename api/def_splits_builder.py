"""Materialized defensive player splits: a defender's event line (tackles,
sacks, TFL, QB hits, INTs, pass breakups, forced fumbles) conditioned on a
single situational dimension.

Unlike the offensive splits (one player id per play), a play credits several
defenders across several stat columns. We UNION the per-defender slot columns
(the same ones that feed game-log defensive stats) into one long "events"
stream — one row per (defender, play, credited stat) — then aggregate per
defender and dimension. Counts only: nflfastR has no coverage/assignment data,
so completion-allowed-style metrics aren't possible.

Perspective is the defense's: game script is flipped (defender leads when the
offense trails), home/away is the offense's flipped, and "opponent" is the
offense faced (posteam).
"""
import duckdb

import splits_core as core
from config import DIVISIONS
from database import get_connection, query_to_dict

# Minimum credited events in a season to include a defender (keeps one-off
# special-teamers and spot appearances out).
_MIN_EVENTS = 20

# (slot player-id column, stat bucket, weight). Mirrors DEFENSIVE_SLOTS in
# ingest.py. Fumble recoveries are intentionally excluded — they can be credited
# to offensive players too, so they're not cleanly "defense".
_SLOTS = [
    ("solo_tackle_1_player_id", "solo", 1.0),
    ("solo_tackle_2_player_id", "solo", 1.0),
    ("assist_tackle_1_player_id", "assist", 1.0),
    ("assist_tackle_2_player_id", "assist", 1.0),
    ("assist_tackle_3_player_id", "assist", 1.0),
    ("assist_tackle_4_player_id", "assist", 1.0),
    ("tackle_for_loss_1_player_id", "tfl", 1.0),
    ("tackle_for_loss_2_player_id", "tfl", 1.0),
    ("qb_hit_1_player_id", "qb_hit", 1.0),
    ("qb_hit_2_player_id", "qb_hit", 1.0),
    ("sack_player_id", "sack", 1.0),
    ("half_sack_1_player_id", "sack", 0.5),
    ("half_sack_2_player_id", "sack", 0.5),
    ("interception_player_id", "intc", 1.0),
    ("pass_defense_1_player_id", "pbu", 1.0),
    ("pass_defense_2_player_id", "pbu", 1.0),
    ("forced_fumble_player_1_player_id", "ff", 1.0),
    ("forced_fumble_player_2_player_id", "ff", 1.0),
]
_BUCKETS = ["solo", "assist", "tfl", "sack", "qb_hit", "intc", "pbu", "ff"]

# Situational columns each slot row carries (so dimensions can read them).
_SIT_COLS = ["posteam", "down", "qtr", "yardline_100", "score_differential",
             "posteam_type", "roof", "surface", "no_huddle", "wp",
             "pass_attempt", "rush_attempt"]


_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS defense_splits (
    player_id     VARCHAR NOT NULL,
    season        INTEGER NOT NULL,
    split_dim     VARCHAR NOT NULL,
    split_value   VARCHAR NOT NULL,
    sort_order    INTEGER,
    tackles       DOUBLE,
    solo          INTEGER,
    assists       INTEGER,
    tfl           INTEGER,
    sacks         DOUBLE,
    qb_hits       INTEGER,
    interceptions INTEGER,
    pass_breakups INTEGER,
    forced_fumbles INTEGER,
    PRIMARY KEY (player_id, season, split_dim, split_value)
)
"""

_COLUMNS = ("player_id", "season", "split_dim", "split_value", "sort_order",
            "tackles", "solo", "assists", "tfl", "sacks", "qb_hits",
            "interceptions", "pass_breakups", "forced_fumbles")


def ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_TABLE_DDL)


# ── Dimensions (defense perspective) ─────────────────────────────────────────

def _vs_play_dim() -> tuple[str, str, str, str]:
    return (
        "vs_play",
        "CASE WHEN pass_attempt = 1 THEN 'vs_pass' WHEN rush_attempt = 1 THEN 'vs_run' END",
        "CASE WHEN pass_attempt = 1 THEN 1 ELSE 2 END",
        "pass_attempt = 1 OR rush_attempt = 1",
    )


def _def_home_away_dim() -> tuple[str, str, str, str]:
    # Offense's posteam_type flipped: the defender is home when the offense is away.
    return (
        "home_away",
        "CASE WHEN posteam_type = 'away' THEN 'home' ELSE 'away' END",
        "CASE WHEN posteam_type = 'away' THEN 1 ELSE 2 END",
        "posteam_type IS NOT NULL",
    )


def _opponent_dims() -> list[tuple[str, str, str, str]]:
    """Opponent = the offense faced (posteam) and its division."""
    order = ["AFC East", "AFC North", "AFC South", "AFC West",
             "NFC East", "NFC North", "NFC South", "NFC West"]
    div_when = " ".join(f"WHEN '{t}' THEN '{d}'" for t, d in DIVISIONS.items())
    div_sort_when = " ".join(f"WHEN '{t}' THEN {order.index(d) + 1}" for t, d in DIVISIONS.items())
    return [
        ("opponent", "posteam", "CAST(NULL AS INTEGER)", "posteam IS NOT NULL"),
        ("opp_division", f"CASE posteam {div_when} END", f"CASE posteam {div_sort_when} END", "posteam IS NOT NULL"),
    ]


def _dims() -> list[tuple[str, str, str, str]]:
    return [
        _vs_play_dim(),
        core.DOWN_DIM,
        core.game_script_dim(-1),   # flipped: defense leads when offense trails
        core.QUARTER_DIM,
        core.FIELD_ZONE_DIM,        # red_zone = goal-line defense
        _def_home_away_dim(),
        core.ROOF_DIM,
        core.SURFACE_DIM,
        core.NO_HUDDLE_DIM,
        core.GAME_STATE_DIM,        # wp band is symmetric, so valid for defense
        *_opponent_dims(),
    ]


# ── SQL ──────────────────────────────────────────────────────────────────────

_METRICS = """
    SUM(solo) + SUM(assist) AS tackles,
    CAST(SUM(solo) AS INTEGER)     AS solo,
    CAST(SUM(assist) AS INTEGER)   AS assists,
    CAST(SUM(tfl) AS INTEGER)      AS tfl,
    SUM(sack)                      AS sacks,
    CAST(SUM(qb_hit) AS INTEGER)   AS qb_hits,
    CAST(SUM(intc) AS INTEGER)     AS interceptions,
    CAST(SUM(pbu) AS INTEGER)      AS pass_breakups,
    CAST(SUM(ff) AS INTEGER)       AS forced_fumbles"""


def _events_union(season: int) -> str:
    """One SELECT per defender slot, UNION ALL'd into the events stream."""
    sit = ", ".join(_SIT_COLS)
    blocks = []
    for id_col, bucket, weight in _SLOTS:
        vec = ", ".join(f"{weight if b == bucket else 0} AS {b}" for b in _BUCKETS)
        blocks.append(f"""
        SELECT {id_col} AS player_id, {sit}, {vec}
        FROM plays
        WHERE {id_col} IS NOT NULL AND season = {int(season)} AND season_type = 'REG'""")
    return "\n        UNION ALL\n".join(blocks)


def _season_sql(season: int) -> str:
    union = core.union_blocks(_dims(), _METRICS, "player_id")
    return f"""
    WITH base AS ({_events_union(season)}),
    qualified AS (
        SELECT player_id FROM base GROUP BY player_id HAVING COUNT(*) >= {_MIN_EVENTS}
    ),
    b AS (SELECT base.* FROM base JOIN qualified USING (player_id))
    {union}
    """


# ── Materialize + read API ───────────────────────────────────────────────────

def materialize(season: int) -> int:
    conn = get_connection()
    ensure_table(conn)
    s = int(season)
    conn.execute("DELETE FROM defense_splits WHERE season = ?", [s])
    cols = ", ".join(_COLUMNS)
    try:
        conn.execute(f"""
            INSERT INTO defense_splits ({cols})
            SELECT player_id, {s} AS season, split_dim, split_value, sort_order,
                   tackles, solo, assists, tfl, sacks, qb_hits, interceptions,
                   pass_breakups, forced_fumbles
            FROM ({_season_sql(s)})
        """)
    except Exception as e:
        print(f"defense_splits materialize failed for season {s}: {e}")
    return conn.execute("SELECT COUNT(*) FROM defense_splits WHERE season = ?", [s]).fetchone()[0]


def read(player_id: str) -> list[dict]:
    try:
        return query_to_dict("""
            SELECT season, split_dim, split_value, sort_order,
                   tackles, solo, assists, tfl, sacks, qb_hits,
                   interceptions, pass_breakups, forced_fumbles
            FROM defense_splits
            WHERE player_id = ?
            ORDER BY season DESC, split_dim, sort_order
        """, [player_id])
    except Exception:
        return []


def read_or_materialize(player_id: str) -> list[dict]:
    rows = read(player_id)
    if rows:
        return rows
    try:
        seasons = [r["season"] for r in query_to_dict(
            "SELECT DISTINCT season FROM plays "
            "WHERE solo_tackle_1_player_id = ? OR assist_tackle_1_player_id = ? "
            "OR sack_player_id = ? OR interception_player_id = ?",
            [player_id, player_id, player_id, player_id])]
    except Exception:
        seasons = []
    for s in seasons:
        materialize(s)
    return read(player_id)
