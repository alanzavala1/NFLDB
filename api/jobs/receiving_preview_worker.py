"""Internal preview worker; invoke through jobs.receiving_preview."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import duckdb

from pipeline.receiving_preview import file_sha256
from pipeline.receiving_dimensions import DIMENSIONS
from pipeline.receiving_splits import VERSIONS
from pipeline.receiving_exports import load_receiving_season
from pipeline.snapshots import CandidateError


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
    # Legacy config may query schedules during import. Qualification uses fresh
    # bound plays in memory, so disable that unrelated lookup in this worker.
    os.environ["NFL_TEST_MODE"] = "1"
    report = {"format_version": 4, "status": "preview_only", "run_id": run_id,
              "source": str(source.resolve()), "source_sha256": baseline,
              "export_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "export_directory": str(exports.resolve()), "runtime": runtime,
              "qualification": "existing rules applied to bound fresh PBP context",
              "qualifications": {}, "whole_references": {}, "seasons": {}}
    with duckdb.connect(str(candidate)) as conn:
        conn.execute("BEGIN")
        try:
            for dimension in DIMENSIONS:
                conn.execute(f"CREATE TABLE receiving_{dimension}_preview AS SELECT * FROM player_splits WHERE FALSE")
            for season in seasons:
                prepared = load_receiving_season(exports, manifest, season, require_qualified=True)
                report["qualifications"][str(season)] = prepared.qualification
                report["whole_references"][str(season)] = prepared.whole
                report["seasons"][str(season)] = prepared.dimensions
                for dimension, rows in prepared.rows.items():
                    conn.register("preview_rows", rows)
                    conn.execute(f"INSERT INTO receiving_{dimension}_preview BY NAME SELECT * FROM preview_rows")
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
