"""Read-only exact passing row/metadata replay against captured inputs."""
import duckdb
import pandas as pd

from pipeline.passing_build import PREPARATION_TABLE, _DDL, prepare_passing
from pipeline.receiving_validation import _json, _record, _rows
from pipeline.snapshots import CandidateError
from pipeline.source_results import SourceError
from pipeline.validation import SnapshotValidationError


def validate_passing(conn, core_inputs, passing_inputs, *, log=lambda message: None):
    import splits_builder
    def require(condition, message):
        if not condition:
            raise SnapshotValidationError(message)
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        require(PREPARATION_TABLE in tables, "passing: missing preparation records")
        with duckdb.connect(":memory:") as expected:
            expected.execute(_DDL)
            actual = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info('{PREPARATION_TABLE}')").fetchall()}
            for _, name, kind, _, _, _ in expected.execute(f"PRAGMA table_info('{PREPARATION_TABLE}')").fetchall():
                require(actual.get(name) == kind, f"{PREPARATION_TABLE}.{name}: expected {kind}")
        seasons = [row[0] for row in conn.execute(
            "SELECT DISTINCT season FROM plays WHERE season_type='REG' ORDER BY season").fetchall()]
        require(bool(seasons), "passing: no loaded REG seasons")
        require(conn.execute(f"SELECT season FROM {PREPARATION_TABLE} ORDER BY season").fetchall()
                == [(year,) for year in seasons], "passing: preparation must cover every loaded REG season exactly once")
        require(not conn.execute("""SELECT 1 FROM player_splits WHERE category='passing' AND
            (season IS NULL OR season NOT IN (SELECT DISTINCT season FROM plays WHERE season_type='REG')) LIMIT 1""").fetchall(),
                "passing: rows outside loaded REG seasons")
        results = {}
        for season in seasons:
            prepared = prepare_passing(conn, season, core_inputs, passing_inputs)
            require(_json(_record(conn, PREPARATION_TABLE, season)) == _json(prepared.report),
                    f"passing[{season}]: preparation differs from bound source replay")
            actual = conn.execute("SELECT * FROM player_splits WHERE category='passing' AND season=?", [season]).df()
            expected = pd.concat(list(prepared.rows.values()), ignore_index=True)
            require(_rows(actual, splits_builder._COLUMNS) == _rows(expected, splits_builder._COLUMNS),
                    f"passing[{season}]: rows differ from bound source replay")
            results[season] = {"rows": len(actual), "views": len(prepared.rows),
                               "qualified_players": prepared.report["admission"]["qualified_players"]}
            log(f"Passing[{season}]: {len(actual):,} rows and coverage records match bound inputs")
        return {"status": "passed", "publication_ready": False, "played_seasons": seasons,
                "core_revision": core_inputs.revision(), "passing_revision": passing_inputs.revision(), "seasons": results}
    except (CandidateError, SourceError, KeyError, TypeError, ValueError, duckdb.Error) as error:
        raise SnapshotValidationError(f"Passing validation failed: {error}") from error
