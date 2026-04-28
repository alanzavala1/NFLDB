import threading
import duckdb
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "nfl.duckdb")

_conn = None
_lock = threading.Lock()


def get_connection() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = duckdb.connect(DB_PATH)
    return _conn


def query_to_dict(sql: str, params: list = None) -> list[dict]:
    with _lock:
        conn = get_connection()
        rel = conn.execute(sql, params or [])
        columns = [desc[0] for desc in rel.description]
        return [dict(zip(columns, row)) for row in rel.fetchall()]
