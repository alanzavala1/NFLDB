"""DuckDB connection management.

One process holds a single DuckDB Connection that owns the file. Every caller
that needs to run a query takes a fresh cursor from that Connection via
`get_cursor()`. Cursors are independent execution contexts (DuckDB's MVCC
isolates them), so concurrent reads don't serialize on a Python lock.

Serving opens the snapshot read-only. Offline jobs explicitly opt into a
writable connection and hold `write_lock` while preparing a new candidate.
"""
import os
import threading

import duckdb

# Overridable so a local run can point at a rebuilt or experimental copy
# without touching the working database. Writes require NFL_DB_READ_ONLY=0 in
# an offline process; the serving app rejects that mode.
DB_PATH = os.environ.get(
    "NFL_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "nfl.duckdb")
)

# The single-writer guarantee. Reentrant so an ingest run (which holds the
# lock for its whole duration) can call the builders' materialize() functions,
# which also acquire it. Readers never take this lock.
write_lock = threading.RLock()

_conn: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """The process connection; ordinary read queries take independent cursors."""
    global _conn
    if _conn is None:
        read_only = os.environ.get('NFL_DB_READ_ONLY') != '0'
        if not read_only:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = duckdb.connect(DB_PATH, read_only=read_only)
        # In a container, DuckDB sizes its memory budget (80% of RAM) and
        # thread pool (one per core) from the HOST, not the cgroup limits —
        # on Cloud Run that meant queries happily allocated past the 1 GiB
        # container cap and the instance was OOM-killed mid-request (503s +
        # cold starts). The Dockerfile pins both; unset locally = defaults.
        mem = os.environ.get("DUCKDB_MEMORY_LIMIT")
        if mem:
            _conn.execute(f"SET memory_limit = '{mem}'")
        threads = os.environ.get("DUCKDB_THREADS")
        if threads:
            _conn.execute(f"SET threads = {int(threads)}")
    return _conn


def close_connection() -> None:
    """Release the process connection after an offline job has finished.

    The caller must own the process lifecycle; never close while serving queries.
    """
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        finally:
            _conn = None


# Large tables hit by per-request point lookups that lack a usable index
# (the materialized splits/comparables tables already have a PRIMARY KEY on
# their lookup key, so they're not listed). Small/fast tables are left
# unindexed on purpose — an index there is overhead with no payoff.
_INDEXES = [
    ("depth_charts", "gsis_id"),         # 1.4M rows — current-depth lookup per profile
    ("player_game_stats", "player_id"),  # 434k — game log + most aggregations
    ("snap_counts", "pfr_player_id"),    # 324k — snap totals per profile
]


def ensure_indexes(*, strict: bool = False) -> None:
    """Idempotent point-lookup indexes for the hot read paths. DuckDB persists
    indexes, so this only does real work the first time (or after a table that
    was rebuilt via CREATE TABLE AS, e.g. player_game_stats, dropped its index).
    Offline candidate finalization uses strict=True so failures stop the build.
    """
    conn = get_connection()
    try:
        tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    except Exception:
        if strict:
            raise
        return
    for table, col in _INDEXES:
        if table not in tables:
            continue
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_{col} ON {table}({col})")
        except Exception as e:
            if strict:
                raise
            print(f"index {table}.{col} skipped: {e}")


def get_cursor() -> duckdb.DuckDBPyConnection:
    """A fresh cursor for read queries. Cursors are cheap and isolated."""
    return get_connection().cursor()


def query_to_dict(sql: str, params: list = None) -> list[dict]:
    """Run a query on a fresh cursor and return rows as dicts.

    Used by all read endpoints. Each call gets its own cursor, so concurrent
    requests do not serialize.
    """
    with get_cursor() as cur:
        rel = cur.execute(sql, params or [])
        columns = [desc[0] for desc in rel.description]
        return [dict(zip(columns, row)) for row in rel.fetchall()]
