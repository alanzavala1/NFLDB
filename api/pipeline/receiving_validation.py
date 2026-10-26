"""Read-only receiving validation against revision-bound official exports.

This is deliberately a scoped check. Success does not certify other analytics,
source freshness, operating-system support or publication readiness.
"""
import json

import duckdb
import pandas as pd

from pipeline.receiving_build import PREPARATION_TABLE, REFERENCE_TABLE, TOTALS_TABLE, _DDL, prepare_receiving, receiving_records
from pipeline.reconciliation import receiving_total_checks
from pipeline.snapshots import CandidateError
from pipeline.source_results import SourceError
from pipeline.validation import SnapshotValidationError


_TABLES = (PREPARATION_TABLE, REFERENCE_TABLE, TOTALS_TABLE)


def _require(condition, message):
    if not condition:
        raise SnapshotValidationError(message)


def _schema(conn):
    import splits_builder
    with duckdb.connect(":memory:") as expected:
        expected.execute(_DDL)
        expected.execute(splits_builder._TABLE_DDL)
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        for table in ("plays", "weekly_player_stats", "player_game_stats", "schedules"):
            _require(table in tables, f"receiving: missing source table {table}")
        for table in (*_TABLES, "player_splits"):
            _require(table in tables, f"receiving: missing prepared table {table}")
            actual = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}
            for _, name, kind, _, _, _ in expected.execute(f"PRAGMA table_info('{table}')").fetchall():
                _require(actual.get(name) == kind, f"{table}.{name}: expected {kind}, got {actual.get(name)}")


def _record(conn, table, season):
    values = conn.execute(f"SELECT record FROM {table} WHERE season=?", [season]).fetchall()
    _require(len(values) == 1 and values[0][0] is not None, f"{table}[{season}]: expected one nonnull record")
    value = json.loads(values[0][0])
    _require(isinstance(value, dict), f"{table}[{season}]: record must be an object")
    return value


def _json(value):
    # Comparing canonical JSON also distinguishes false/0 and numeric strings.
    # Never allow NaN/Infinity to disappear inside a metadata comparison.
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _rows(frame, columns):
    keys = ["player_id", "season", "category", "split_dim", "split_value"]
    frame = frame[list(columns)].sort_values(keys).reset_index(drop=True).astype(object)
    return frame.where(frame.notna(), None).to_dict(orient="records")


def validate_receiving(conn, inputs, *, log=lambda message: None):
    """Replay every loaded REG season without changing the candidate or inputs.

    Shared acceptance code verifies exact captured plays/weekly data, admission,
    dependency/definition/input hashes, independent weekly/whole counts, exact
    classified membership and excluded credits, historical masks and target-role
    rate/air populations. Compare every stored row AND metadata record with that
    replay, so a self-consistent corruption cannot pass by conserving its own sum.
    No R, network, builder writes or validation stamp is involved.
    """
    import splits_builder
    try:
        _schema(conn)
        seasons = [row[0] for row in conn.execute(
            "SELECT DISTINCT season FROM plays WHERE season_type='REG' ORDER BY season").fetchall()]
        _require(bool(seasons) and all(type(year) is int and year >= 1999 for year in seasons),
                 "receiving: no valid loaded regular seasons")
        for table in _TABLES:
            years = conn.execute(f"SELECT season FROM {table} ORDER BY season").fetchall()
            _require(years == [(year,) for year in seasons], f"{table}: records must cover every loaded REG season exactly once")
        extra = conn.execute("""SELECT DISTINCT season FROM player_splits WHERE category='receiving'
                                 AND (season IS NULL OR season NOT IN (SELECT DISTINCT season FROM plays WHERE season_type='REG'))""").fetchall()
        _require(not extra, "receiving: split rows outside loaded regular seasons")
        report = {}
        for season in seasons:
            prepared = prepare_receiving(conn, season, inputs)
            for table, expected in receiving_records(prepared).items():
                actual = _record(conn, table, season)
                _require(_json(actual) == _json(expected), f"{table}[{season}]: differs from bound source replay")
            actual = conn.execute("SELECT * FROM player_splits WHERE season=? AND category='receiving'", [season]).df()
            expected = pd.concat(list(prepared.exports.rows.values()), ignore_index=True)
            _require(_rows(actual, splits_builder._COLUMNS) == _rows(expected, splits_builder._COLUMNS),
                     f"player_splits[{season}, receiving]: differs from bound source replay")
            game_checks = receiving_total_checks(conn, season)
            for name, (mismatches, allowed) in game_checks.items():
                _require(mismatches <= allowed, f"{name}[{season}]: {mismatches} mismatches (allowed {allowed})")
            coverage = prepared.report["game_coverage"]
            report[season] = {"qualified_players": prepared.exports.qualification["players"],
                              "receiving_rows": len(actual), "views": len(prepared.exports.rows),
                              "player_game_checks": game_checks,
                              "missing_game_ids": coverage["missing_game_ids"],
                              "unconfirmed_game_ids": coverage["unconfirmed_game_ids"],
                              "partial_views": [key for key, value in prepared.exports.dimensions.items()
                                                if value["coverage"]["status"] == "partial"],
                              "unavailable_views": [key for key, value in prepared.exports.dimensions.items()
                                                    if value["coverage"]["status"] == "unavailable"]}
            log(f"Receiving[{season}]: {len(actual):,} rows and all coverage/whole records match bound inputs")
        return {"status": "passed", "scope": "source-bound receiving validation only", "publication_ready": False,
                "core_revision": inputs.revision(), "played_seasons": seasons, "seasons": report}
    except (CandidateError, SourceError, KeyError, TypeError, ValueError, duckdb.Error) as error:
        raise SnapshotValidationError(f"Receiving validation failed: {error}") from error
