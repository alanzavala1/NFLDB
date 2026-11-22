"""Exercise the packaged analytics dependencies against a synthetic fixture."""
import argparse
import base64
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import tempfile

import duckdb
import pyarrow
import sqlglot
import wren_core
from wren import WrenEngine
from wren.config import WrenConfig
from wren.model.error import WrenError


HERE = Path(__file__).resolve().parent
QUERY = """SELECT player_id,
    CAST(SUM(targets) AS BIGINT) AS targets,
    CAST(SUM(receptions) AS BIGINT) AS receptions,
    CAST(SUM(receiving_yards) AS BIGINT) AS receiving_yards,
    100.0 * SUM(receptions) / NULLIF(SUM(targets), 0) AS catch_rate_pct
    FROM receiving_games GROUP BY player_id ORDER BY player_id"""


def fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fixture_manifest():
    columns = [("game_id", "VARCHAR"), ("player_id", "VARCHAR"),
               ("targets", "INTEGER"), ("receptions", "INTEGER"),
               ("receiving_yards", "INTEGER")]
    manifest = {
        "catalog": "wren", "schema": "public",
        "models": [{
            "name": "receiving_games", "dialect": "duckdb",
            "refSql": "SELECT * FROM fixture.main.receiving_game_source",
            "columns": [{"name": name, "type": kind} for name, kind in columns],
        }],
        "relationships": [], "views": [], "metrics": [],
    }
    return base64.b64encode(json.dumps(manifest).encode()).decode()


def check(case):
    # Both the fixture writer and read-only query handles must close before
    # TemporaryDirectory removes the files, including on Windows.
    with tempfile.TemporaryDirectory(prefix="nfldb-runtime-") as temporary:
        directory = Path(temporary)
        database = directory / "fixture.duckdb"
        with duckdb.connect(str(database)) as connection:
            connection.execute((HERE / "fixtures/receiving.sql").read_text(encoding="utf-8"))
        before = fingerprint(database)
        with WrenEngine(
            fixture_manifest(), "duckdb",
            {"url": directory.as_posix(), "format": "duckdb"},
            fallback=False, config=WrenConfig(strict_mode=True),
        ) as engine:
            sql = QUERY if case == "aggregate" else "SELECT missing_field FROM receiving_games"
            rows = engine.query(sql, limit=10, read_only=True).to_pylist()
        if fingerprint(database) != before or Path(str(database) + ".wal").exists():
            raise RuntimeError("Fixture changed during a read-only query")

    modules = {"duckdb": duckdb, "pyarrow": pyarrow,
               "sqlglot": sqlglot, "wren_core": wren_core}
    return {
        "status": "ok", "frozen": bool(getattr(sys, "frozen", False)),
        "platform": sys.platform, "architecture": platform.machine(),
        "python": platform.python_version(), "fixture_unchanged": True,
        "dependencies": {name: str(Path(module.__file__).resolve())
                         for name, module in modules.items()},
        "versions": {name: version(name) for name in ("duckdb", "wrenai", "wren-core-py")},
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("aggregate", "invalid-query"), default="aggregate")
    args = parser.parse_args()
    try:
        report = check(args.case)
    except WrenError as error:
        print(json.dumps({"status": "error", "code": error.error_code.name}))
        return 2
    print(json.dumps(report, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
