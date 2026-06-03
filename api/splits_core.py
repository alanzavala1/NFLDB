"""Shared scaffolding for situational "splits" tables.

A split is an entity's stat line conditioned on one play-level dimension.
Player splits and team splits share: the dimension vocabulary, feature
detection of optional `plays` columns, and the UNION-of-dimensions SQL
assembly. Each domain supplies its own base query (entity key + row filter),
metric projection, and any domain-specific lead dimensions.

Dimension tuples are (dim_name, value_expr, sort_expr, extra_filter); the
exprs read columns from the `b` CTE the caller wraps the blocks in. A few
lead dims (depth/direction) are stored name-less as 3-tuples because the
caller names them differently per category (pass_depth vs target_depth).
"""

# ── Fixed-name dimensions (4-tuples) ─────────────────────────────────────────

DOWN_DIM = (
    "down",
    "CAST(CAST(down AS INTEGER) AS VARCHAR)", "CAST(down AS INTEGER)",
    "down IN (1, 2, 3, 4)",
)
QUARTER_DIM = (
    "quarter",
    "CASE WHEN qtr <= 4 THEN CAST(CAST(qtr AS INTEGER) AS VARCHAR) ELSE 'OT' END",
    "CASE WHEN qtr <= 4 THEN CAST(qtr AS INTEGER) ELSE 5 END",
    "qtr IS NOT NULL",
)
SHOTGUN_DIM = (
    "shotgun",
    "CASE WHEN shotgun = 1 THEN 'shotgun' ELSE 'under_center' END",
    "CASE WHEN shotgun = 1 THEN 1 ELSE 2 END",
    "TRUE",
)


def game_script_dim(sign: int = 1) -> tuple[str, str, str, str]:
    """Leading/tied/trailing from the entity's perspective. score_differential
    is stored from the posteam's point of view, so a defense (defteam) passes
    sign=-1 to flip it."""
    sd = "score_differential" if sign == 1 else "(-1 * score_differential)"
    return (
        "game_script",
        f"CASE WHEN {sd} > 0 THEN 'leading' WHEN {sd} = 0 THEN 'tied' ELSE 'trailing' END",
        f"CASE WHEN {sd} > 0 THEN 1 WHEN {sd} = 0 THEN 2 ELSE 3 END",
        "score_differential IS NOT NULL",
    )


# ── Name-less lead dims (3-tuples): caller prepends the dim name ──────────────

DEPTH = ("pass_length", "CASE pass_length WHEN 'short' THEN 1 WHEN 'deep' THEN 2 END", "pass_length IS NOT NULL")
PASS_DIR = ("pass_location", "CASE pass_location WHEN 'left' THEN 1 WHEN 'middle' THEN 2 WHEN 'right' THEN 3 END", "pass_location IS NOT NULL")
RUN_DIR = ("run_location", "CASE run_location WHEN 'left' THEN 1 WHEN 'middle' THEN 2 WHEN 'right' THEN 3 END", "run_location IS NOT NULL")


# ── Feature detection of optional plays columns ──────────────────────────────

def plays_columns(conn) -> set[str]:
    try:
        return {r[0] for r in conn.execute("DESCRIBE plays").fetchall()}
    except Exception:
        return set()


def success_col(available: set[str]) -> str:
    """SELECT-list fragment aliasing a `success` column (0/1). Falls back to
    epa>0 on old seasons that predate the modeled success field."""
    return "success" if "success" in available else "CASE WHEN epa > 0 THEN 1 ELSE 0 END AS success"


def two_pt_filter(available: set[str]) -> str:
    return "AND COALESCE(two_point_attempt, 0) = 0" if "two_point_attempt" in available else ""


# ── UNION assembly ───────────────────────────────────────────────────────────

def union_blocks(dims, metric_select: str, key_col: str) -> str:
    """One SELECT per dimension, UNION ALL'd. Each block groups the `b` CTE by
    the entity key and the dimension value, projecting `metric_select`."""
    blocks = []
    for dim, value_expr, sort_expr, extra in dims:
        blocks.append(f"""
        SELECT
            {key_col},
            '{dim}'      AS split_dim,
            {value_expr} AS split_value,
            {sort_expr}  AS sort_order,
            {metric_select}
        FROM b
        WHERE {extra}
        GROUP BY {key_col}, {value_expr}, {sort_expr}""")
    return "\n        UNION ALL\n".join(blocks)
