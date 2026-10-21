"""Internal preview worker; invoke through jobs.receiving_preview."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pipeline.receiving_preview import file_sha256
from pipeline.receiving_splits import VERSIONS, load_receiving_down_export, read_export_csv
from pipeline.snapshots import CandidateError
from services.receiving_coverage import targets_unavailable


def _check_totals(rows: pd.DataFrame, weekly: pd.DataFrame, season: int,
                  qualified: list[str]) -> dict:
    counts = {"receptions": "cmp", "receiving_yards": "yards", "receiving_tds": "td"}
    required = {"player_id", "season", "season_type", "targets", *counts}
    if not required.issubset(weekly.columns) or weekly.empty:
        raise CandidateError(f"weekly[{season}]: missing receiving reference data")
    if weekly[["season", "season_type"]].isna().any().any() or not weekly.season.eq(season).all() or not weekly.season_type.eq("REG").all():
        raise CandidateError(f"weekly[{season}]: unexpected reference scope")
    values = weekly[["targets", *counts]].apply(pd.to_numeric, errors="raise")
    numeric = values.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(numeric).all() or not (numeric == np.trunc(numeric)).all():
        raise CandidateError(f"weekly[{season}]: invalid reference counts")
    if values[["targets", "receptions", "receiving_tds"]].lt(0).any().any():
        raise CandidateError(f"weekly[{season}]: negative reference counts")
    weekly = weekly.copy()
    weekly[values.columns] = values
    if set(rows.player_id) != set(qualified):
        raise CandidateError(f"receiving[{season}]: qualified player missing from preview")
    if targets_unavailable([season]):
        if rows.att.notna().any():
            raise CandidateError(f"receiving[{season}]: historical targets must be NULL")
    else:
        counts["targets"] = "att"
    for source, target in counts.items():
        expected = weekly[weekly.player_id.isin(qualified)].groupby("player_id")[source].sum()
        actual = rows.groupby("player_id")[target].sum()
        a, b = actual.align(expected, fill_value=0)
        if not a.eq(b).all():
            raise CandidateError(f"receiving[{season}]: {source} does not match weekly totals")
    return {"players": len(qualified), "rows": len(rows), "production_matches_weekly": True,
            "targets": "unavailable" if targets_unavailable([season]) else "matched_weekly"}


def prepare(source: Path, exports: Path, seasons: list[int], run_id: str, baseline: str) -> dict:
    configured = os.environ.get("NFL_DB_PATH")
    if not configured or not Path(configured).is_absolute() or not Path(configured).is_file():
        raise CandidateError("Preview worker requires an existing absolute NFL_DB_PATH")
    candidate = Path(configured).resolve()
    default = Path(__file__).resolve().parents[1] / "data/nfl.duckdb"
    if candidate == source.resolve() or candidate == default.resolve():
        raise CandidateError("Preview worker cannot write the source or serving database")
    if file_sha256(candidate) != baseline:
        raise CandidateError("Copied baseline changed before preview preparation")
    manifest_bytes = (exports / "run.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or manifest.get("run_id") != run_id or manifest.get("seasons") != seasons:
        raise CandidateError("R completion marker does not match this invocation")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or not runtime.get("R") or not isinstance(runtime.get("packages"), dict):
        raise CandidateError("R completion marker has no runtime package record")
    if any(runtime["packages"].get(name) != version for name, version in VERSIONS.items()):
        raise CandidateError("Runtime package versions differ from calculator contract")
    # Legacy config may query schedules during import. Preview qualification uses
    # our explicit connection, so disable that unrelated lookup in this worker.
    os.environ["NFL_TEST_MODE"] = "1"
    import splits_builder

    report = {"format_version": 1, "status": "preview_only", "run_id": run_id,
              "source": str(source.resolve()), "source_sha256": baseline,
              "export_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "export_directory": str(exports.resolve()), "runtime": runtime,
              "qualification": "existing stored PBP rules", "seasons": {}}
    with duckdb.connect(str(candidate)) as conn:
        available = {row[0] for row in conn.execute("DESCRIBE plays").fetchall()}
        conn.execute("BEGIN")
        try:
            conn.execute("CREATE TABLE receiving_down_preview AS SELECT * FROM player_splits WHERE FALSE")
            for season in seasons:
                sql = splits_builder.qualification_ctes("receiving", season, available) + " SELECT player_id FROM qualified"
                qualified = conn.execute(sql).df().player_id.tolist()
                if not qualified:
                    raise CandidateError(f"receiving[{season}]: no qualified players for preview")
                rows = load_receiving_down_export(exports, season=season, qualified_players=qualified, manifest=manifest)
                weekly = read_export_csv(exports, manifest, f"weekly-{season}.csv", season=season)
                report["seasons"][str(season)] = _check_totals(rows, weekly, season, qualified)
                conn.register("preview_rows", rows)
                conn.execute("INSERT INTO receiving_down_preview BY NAME SELECT * FROM preview_rows")
            conn.execute("CREATE TABLE receiving_preview_preparation (record JSON)")
            conn.execute("INSERT INTO receiving_preview_preparation VALUES (?)", [json.dumps(report)])
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("CHECKPOINT")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--seasons", type=int, nargs="+", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--baseline-sha256", required=True)
    args = parser.parse_args()
    prepare(args.source, args.exports, args.seasons, args.run_id, args.baseline_sha256)


if __name__ == "__main__":
    main()
