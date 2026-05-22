"""Materialized player comparables.

Same pattern as team_analytics_builder: do the expensive work once during
ingest, store the result, serve from keyed SELECTs.

For comparables the expensive work is:
  1. Gather career totals for every player with >= 16 regular-season games
  2. Classify into position groups (QB / RB / WRTE)
  3. Build per-position feature vectors (per-game / per-attempt rates)
  4. Z-score normalize within each position group
  5. All-pairs cosine similarity within each position group
  6. For each player, keep the top _TOP_N neighbors

The math runs in numpy so 1500-player groups finish in <100ms. The
result lives in two tables:

  player_career_summary  (player_id, pos_group, display columns)
  player_comparables     (player_id, rank, comparable_id, similarity)

The endpoint becomes a single JOIN keyed by player_id.
"""
import numpy as np

from database import get_connection, query_to_dict


# Number of pre-computed neighbors per player. Endpoint LIMITs to <=20.
_TOP_N = 20


# ── Tables ───────────────────────────────────────────────────────────────────

_SUMMARY_DDL = """
CREATE TABLE IF NOT EXISTS player_career_summary (
    player_id    VARCHAR NOT NULL PRIMARY KEY,
    player_name  VARCHAR,
    position     VARCHAR,
    team         VARCHAR,
    headshot_url VARCHAR,
    pos_group    VARCHAR NOT NULL,
    games        INTEGER NOT NULL,
    first_season INTEGER NOT NULL,
    last_season  INTEGER NOT NULL,
    pass_yards   DOUBLE, pass_tds DOUBLE, ints DOUBLE,
    att          DOUBLE, cmp      DOUBLE,
    rush_yards   DOUBLE, rush_tds DOUBLE, carries  DOUBLE,
    rec_yards    DOUBLE, rec_tds  DOUBLE, targets  DOUBLE
)
"""

_COMPARABLES_DDL = """
CREATE TABLE IF NOT EXISTS player_comparables (
    player_id     VARCHAR NOT NULL,
    rank          INTEGER NOT NULL,
    comparable_id VARCHAR NOT NULL,
    similarity    DOUBLE  NOT NULL,
    PRIMARY KEY (player_id, rank)
)
"""


def ensure_tables() -> None:
    conn = get_connection()
    conn.execute(_SUMMARY_DDL)
    conn.execute(_COMPARABLES_DDL)


# ── Career totals query ──────────────────────────────────────────────────────

_CAREER_SQL = """
WITH recent_roster AS (
    SELECT player_id, position, team, headshot_url
    FROM rosters
    QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY season DESC) = 1
),
career AS (
    SELECT
        pgs.player_id,
        MAX(pgs.player_name)          AS player_name,
        COUNT(DISTINCT pgs.game_id)   AS games,
        MIN(pgs.season)               AS first_season,
        MAX(pgs.season)               AS last_season,
        SUM(pgs.attempts)             AS att,
        SUM(pgs.completions)          AS cmp,
        SUM(pgs.pass_yards)           AS pass_yards,
        SUM(pgs.pass_tds)             AS pass_tds,
        SUM(pgs.interceptions_thrown) AS ints,
        SUM(pgs.pass_epa)             AS pass_epa,
        SUM(pgs.carries)              AS carries,
        SUM(pgs.rush_yards)           AS rush_yards,
        SUM(pgs.rush_tds)             AS rush_tds,
        SUM(pgs.rush_epa)             AS rush_epa,
        SUM(pgs.targets)              AS targets,
        SUM(pgs.receptions)           AS rec,
        SUM(pgs.rec_yards)            AS rec_yards,
        SUM(pgs.rec_tds)              AS rec_tds,
        SUM(pgs.rec_epa)              AS rec_epa,
        SUM(pgs.air_yards)            AS air_yards,
        SUM(pgs.yac)                  AS yac
    FROM player_game_stats pgs
    JOIN schedules s ON pgs.game_id = s.game_id AND s.game_type = 'REG'
    GROUP BY pgs.player_id
    HAVING COUNT(DISTINCT pgs.game_id) >= 16
)
SELECT c.*, r.position, r.team, r.headshot_url
FROM career c
LEFT JOIN recent_roster r ON r.player_id = c.player_id
"""


# ── Classification + feature math (pure functions, unit-tested) ──────────────

def comp_pos_group(pos: str | None, att: int, carries: int, tgts: int) -> str:
    """Classify a career as QB / RB / WRTE / OTHER.

    Explicit position wins; otherwise fall back to usage signals so trick-play
    QBs or hybrid backs land in the right pool.
    """
    if pos == "QB":               return "QB"
    if pos in ("RB", "FB"):       return "RB"
    if pos in ("WR", "TE"):       return "WRTE"
    if att > carries and att > tgts and att >= 50: return "QB"
    if carries >= tgts and carries >= 50:          return "RB"
    if tgts >= 30:                                 return "WRTE"
    return "OTHER"


def comp_feature_vec(r: dict, pg: str) -> list[float]:
    """Per-position feature vector — efficiency stats normalized to per-attempt
    or per-game so volume doesn't dominate the similarity."""
    g   = max(r["games"],   1)
    att = max(r["att"],     1)
    car = max(r["carries"], 1)
    tgt = max(r["targets"], 1)
    rec = max(r["rec"],     1)
    if pg == "QB":
        return [
            r["cmp"]        / att,
            r["pass_yards"] / att,
            r["pass_tds"]   / att,
            r["ints"]       / att,
            r["pass_epa"]   / att,
            r["rush_yards"] / g,
            r["rush_tds"]   / g,
        ]
    elif pg == "RB":
        return [
            r["rush_yards"] / car,
            r["rush_tds"]   / car,
            r["rush_yards"] / g,
            r["rush_epa"]   / car,
            r["rec_yards"]  / g,
            r["rec"]        / g,
            r["targets"]    / g,
        ]
    else:  # WRTE
        return [
            r["rec"]        / tgt,
            r["rec_yards"]  / rec,
            r["rec_tds"]    / rec,
            r["rec_yards"]  / g,
            r["rec_epa"]    / tgt,
            r["air_yards"]  / tgt,
            r["yac"]        / rec,
        ]


def zscore_normalize(vecs: list[list[float]]) -> list[list[float]]:
    """Pure-Python implementation kept for unit tests; the builder itself
    uses numpy for the big matrix."""
    import math
    if not vecs:
        return vecs
    n_feat = len(vecs[0])
    out = [list(v) for v in vecs]
    for j in range(n_feat):
        vals = [v[j] for v in vecs]
        mu = sum(vals) / len(vals)
        std = math.sqrt(sum((x - mu) ** 2 for x in vals) / len(vals))
        for i in range(len(out)):
            out[i][j] = (out[i][j] - mu) / std if std > 0 else 0.0
    return out


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0 if either is zero."""
    import math
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Build (numpy-vectorized) ─────────────────────────────────────────────────

# Position-group filters: minimum volume to be eligible as a peer
_MIN_ATT  = {"QB": 200, "RB": 0,   "WRTE": 0}
_MIN_CAR  = {"QB": 0,   "RB": 100, "WRTE": 0}
_MIN_TGT  = {"QB": 0,   "RB": 0,   "WRTE": 50}


def _filter_pool(rows: list[dict], pg: str) -> list[dict]:
    """Apply per-position minimum-volume filters."""
    return [r for r in rows
            if r["att"]     >= _MIN_ATT[pg]
            and r["carries"] >= _MIN_CAR[pg]
            and r["targets"] >= _MIN_TGT[pg]]


def _compute_neighbors(pool: list[dict], pg: str, top_n: int) -> list[tuple]:
    """Build (player_id, rank, comparable_id, similarity) tuples for a group.

    Vectorized: O(N^2) cosines done as a single matrix multiply.
    For N=2000 and 7 features this is a sub-second operation.
    """
    if len(pool) < 2:
        return []

    # Build feature matrix V (N x K)
    V = np.array([comp_feature_vec(r, pg) for r in pool], dtype=np.float64)

    # Z-score normalize each feature column
    mu  = V.mean(axis=0)
    std = V.std(axis=0)
    std[std == 0] = 1.0   # avoid div-by-zero for constant features
    Z = (V - mu) / std

    # Cosine similarity = (Z @ Z.T) / (||Z_i|| ||Z_j||)
    norms = np.linalg.norm(Z, axis=1)
    norms[norms == 0] = 1.0
    Zn = Z / norms[:, None]
    S = Zn @ Zn.T                       # N x N cosine matrix
    S = np.clip(S, 0.0, 1.0)            # clip negatives to 0 (match old behavior)
    np.fill_diagonal(S, -1.0)           # exclude self

    # For each player, find top-N
    ids = [r["player_id"] for r in pool]
    out: list[tuple] = []
    for i, pid in enumerate(ids):
        # argsort descending; take first top_n that are >= 0
        order = np.argsort(-S[i])
        rank = 0
        for j in order:
            if S[i, j] < 0:
                break
            rank += 1
            out.append((pid, rank, ids[j], float(S[i, j])))
            if rank >= top_n:
                break
    return out


def materialize() -> tuple[int, int]:
    """Rebuild player_career_summary and player_comparables from scratch.

    Returns (summary_rows, comparable_rows). Safe to re-run.
    """
    ensure_tables()
    conn = get_connection()

    try:
        rows = query_to_dict(_CAREER_SQL)
    except Exception as e:
        print(f"comparables materialize: career query failed: {e}")
        return (0, 0)

    if not rows:
        return (0, 0)

    # Classify and split into pools
    pools: dict[str, list[dict]] = {"QB": [], "RB": [], "WRTE": []}
    for r in rows:
        pg = comp_pos_group(r.get("position"), r["att"], r["carries"], r["targets"])
        if pg in pools:
            r["pos_group"] = pg
            pools[pg].append(r)

    # Apply per-position min-volume filters; only filtered rows are stored
    qualified: list[dict] = []
    all_neighbors: list[tuple] = []
    for pg in ("QB", "RB", "WRTE"):
        pool = _filter_pool(pools[pg], pg)
        qualified.extend(pool)
        all_neighbors.extend(_compute_neighbors(pool, pg, _TOP_N))

    # Replace tables atomically (DELETE + INSERT inside a single transaction).
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM player_career_summary")
        conn.execute("DELETE FROM player_comparables")

        for r in qualified:
            conn.execute(
                """INSERT INTO player_career_summary VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?)""",
                [r["player_id"], r["player_name"], r.get("position"), r.get("team"),
                 r.get("headshot_url"), r["pos_group"],
                 int(r["games"]), int(r["first_season"]), int(r["last_season"]),
                 float(r["pass_yards"] or 0), float(r["pass_tds"] or 0), float(r["ints"] or 0),
                 float(r["att"] or 0), float(r["cmp"] or 0),
                 float(r["rush_yards"] or 0), float(r["rush_tds"] or 0), float(r["carries"] or 0),
                 float(r["rec_yards"] or 0), float(r["rec_tds"] or 0), float(r["targets"] or 0)],
            )

        for pid, rank, cid, sim in all_neighbors:
            conn.execute(
                "INSERT INTO player_comparables VALUES (?, ?, ?, ?)",
                [pid, rank, cid, sim],
            )

        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"comparables materialize: write failed: {e}")
        return (0, 0)

    return (len(qualified), len(all_neighbors))


# ── Read API ─────────────────────────────────────────────────────────────────

_READ_SQL = """
SELECT
    c.similarity,
    f.player_id, f.player_name, f.position, f.team, f.headshot_url,
    f.games, f.first_season, f.last_season,
    f.pass_yards, f.pass_tds, f.rush_yards, f.rush_tds,
    f.carries, f.rec_yards, f.rec_tds, f.targets,
    f.att, f.cmp, f.ints
FROM player_comparables c
JOIN player_career_summary f ON f.player_id = c.comparable_id
WHERE c.player_id = ?
ORDER BY c.rank
LIMIT ?
"""


def _rows_to_response(rows: list[dict]) -> list[dict]:
    """Convert raw rows to the PlayerComparable response shape."""
    out: list[dict] = []
    for r in rows:
        out.append({
            "player_id":    r["player_id"],
            "player_name":  r["player_name"],
            "position":     r.get("position"),
            "team":         r.get("team"),
            "headshot_url": r.get("headshot_url"),
            "similarity":   round(float(r["similarity"]) * 100, 1),
            "games":        int(r["games"]),
            "first_season": int(r["first_season"]),
            "last_season":  int(r["last_season"]),
            "pass_yards":   float(r["pass_yards"] or 0),
            "pass_tds":     float(r["pass_tds"] or 0),
            "rush_yards":   float(r["rush_yards"] or 0),
            "rush_tds":     float(r["rush_tds"] or 0),
            "carries":      float(r["carries"] or 0),
            "rec_yards":    float(r["rec_yards"] or 0),
            "rec_tds":      float(r["rec_tds"] or 0),
            "targets":      float(r["targets"] or 0),
            "att":          float(r["att"] or 0),
            "cmp":          float(r["cmp"] or 0),
            "ints":         float(r["ints"] or 0),
        })
    return out


def read(player_id: str, n: int = 8) -> list[dict]:
    """Read top-N comparables for a player. Returns [] if not materialized."""
    try:
        rows = query_to_dict(_READ_SQL, [player_id, n])
    except Exception:
        return []
    return _rows_to_response(rows)


def read_or_materialize(player_id: str, n: int = 8) -> list[dict]:
    """Read from the materialized table; rebuild on first hit if empty.

    Note: unlike team_analytics, the rebuild is global (all players at
    once), so the first cold request can take a few seconds. Subsequent
    requests are O(1) keyed lookups.
    """
    rows = read(player_id, n)
    if rows:
        return rows

    # Cold path: rebuild the whole thing. Only happens once per fresh DB.
    summary_n, _ = materialize()
    if summary_n == 0:
        return []
    return read(player_id, n)
