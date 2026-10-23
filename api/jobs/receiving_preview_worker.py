"""Internal preview worker; invoke through jobs.receiving_preview."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import duckdb

from pipeline.receiving_preview import file_sha256
from pipeline.receiving_dimensions import DIMENSIONS
from pipeline.receiving_splits import VERSIONS, read_export_csv, validate_export_manifest
from pipeline.receiving_preview_validation import load_receiving_preview_partition, validate_whole_receiving
from pipeline.snapshots import CandidateError
from pipeline.receiving_inputs import verify_receiving_inputs
from pipeline.receiving_qualification import qualify_receiving_context


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
                validate_export_manifest(manifest, season)
                weekly = read_export_csv(exports, manifest, f"weekly-{season}.csv", season=season)
                overall = read_export_csv(exports, manifest, f"overall-{season}.csv", season=season)
                context = read_export_csv(exports, manifest, f"context-{season}.csv", season=season)
                ftn_outcome = verify_receiving_inputs(exports, manifest, context, season)
                qualified, qualification = qualify_receiving_context(context, season, manifest["files"][f"context-{season}.csv"])
                if not qualified:
                    raise CandidateError(f"receiving[{season}]: no qualified players for preview")
                report["qualifications"][str(season)] = qualification
                whole_check = validate_whole_receiving(overall, weekly, season, qualified)
                whole_check["source_revisions"] = {name: manifest["files"][name] for name in
                                                  (f"overall-{season}.csv", f"weekly-{season}.csv")}
                report["whole_references"][str(season)] = whole_check
                report["seasons"][str(season)] = {}
                for dimension in DIMENSIONS:
                    rows, partition_report = load_receiving_preview_partition(
                        exports, manifest, context=context, overall=overall, season=season,
                        dimension=dimension, qualified=qualified,
                    )
                    report["seasons"][str(season)][dimension] = partition_report
                    if dimension in ("play_action", "blitz"):
                        partition_report["coverage"]["charting_source"] = ftn_outcome
                        if ftn_outcome["status"] != "loaded":
                            partition_report["coverage"]["reason"] = f"FTN {ftn_outcome['status']}: {ftn_outcome.get('detail', '')}".rstrip(": ")
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
