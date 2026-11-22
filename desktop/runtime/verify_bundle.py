"""Test a relocated bundle without a development Python environment."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


EXPECTED = [
    {"player_id": "receiver-a", "targets": 10, "receptions": 2,
     "receiving_yards": 40, "catch_rate_pct": 20.0},
    {"player_id": "receiver-b", "targets": 4, "receptions": 3,
     "receiving_yards": 24, "catch_rate_pct": 75.0},
]


def verify(bundle, architecture=None):
    with tempfile.TemporaryDirectory(prefix="nfldb-relocation-") as temporary:
        scratch = Path(temporary)
        moved = scratch / "relocated runtime space Ω"
        shutil.copytree(bundle, moved)
        executable = moved / ("nfldb-runtime-check.exe" if os.name == "nt" else "nfldb-runtime-check")
        environment = {key: value for key, value in os.environ.items()
                       if key in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"}}
        environment.update(PATH="", PYTHONHOME=str(scratch / "no-python-home"),
                           PYTHONPATH=str(scratch / "no-python-path"),
                           WREN_HOME=str(scratch / "no-user-settings"))
        cases = []
        for case in ("aggregate", "invalid-query", "aggregate"):
            process = subprocess.run([str(executable), "--case", case], cwd=scratch,
                                     env=environment, capture_output=True, text=True,
                                     encoding="utf-8", timeout=60)
            try:
                result = json.loads(process.stdout)
            except (ValueError, UnicodeError) as error:
                raise RuntimeError(f"No JSON response: {process.stderr}") from error
            if case == "invalid-query":
                if process.returncode != 2 or result.get("status") != "error":
                    raise RuntimeError(f"Invalid query was not rejected: {result}")
                if result.get("code") != "GENERIC_USER_ERROR":
                    raise RuntimeError(f"Unexpected query failure: {result}")
            else:
                if process.returncode or result.get("status") != "ok" or not result.get("frozen"):
                    raise RuntimeError(f"Bundled query failed: {result}; {process.stderr}")
                if not result.get("fixture_unchanged"):
                    raise RuntimeError("Fixture was modified")
                actual_architecture = {"AMD64": "x86_64", "aarch64": "arm64"}.get(
                    result["architecture"], result["architecture"])
                if architecture and actual_architecture != architecture:
                    raise RuntimeError(f"Incorrect architecture: {actual_architecture}")
                for location in result["dependencies"].values():
                    if not Path(location).is_relative_to(moved):
                        raise RuntimeError(f"Dependency outside bundle: {location}")
                rows = result["rows"]
                if len(rows) != len(EXPECTED):
                    raise RuntimeError(f"Incorrect row count: {rows}")
                for actual, expected in zip(rows, EXPECTED):
                    if actual.keys() != expected.keys() or any(
                        not math.isclose(actual[key], value, abs_tol=1e-10)
                        if isinstance(value, float) else actual[key] != value
                        for key, value in expected.items()
                    ):
                        raise RuntimeError(f"Incorrect aggregate: {rows}")
            cases.append({"case": case, "exit_code": process.returncode, "status": result["status"]})
        return {"status": "passed", "platform": result["platform"],
                "architecture": result["architecture"], "versions": result["versions"],
                "cases": cases, "bundle_bytes": sum(p.stat().st_size for p in moved.rglob("*") if p.is_file())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--architecture", choices=("x86_64", "arm64"))
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle.resolve(), args.architecture)))


if __name__ == "__main__":
    main()
