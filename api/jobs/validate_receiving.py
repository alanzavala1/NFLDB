"""Validate all receiving seasons read-only against captured inputs; never publish.

This scoped command does not replace jobs.validate or the complete release gate.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--core-inputs", type=Path, required=True,
                        help="Bound captured bundle/collection covering all loaded regular seasons")
    args = parser.parse_args(argv)
    path = args.database.resolve()
    if not path.is_file() or Path(f"{path}.wal").exists():
        raise RuntimeError("Validation requires an existing database with no pending WAL")
    os.environ.update(NFL_DB_PATH=str(path), NFL_DB_READ_ONLY="1", NFL_TEST_MODE="1")
    import database
    if Path(database.DB_PATH).resolve() != path or database._conn is not None:
        raise RuntimeError("Run receiving validation in a fresh process configured for the candidate")
    try:
        from pipeline.receiving_core_collection import open_core_inputs
        from pipeline.receiving_validation import validate_receiving
        from pipeline.receiving_api_checks import check_receiving_api
        conn = database.get_connection()
        report = validate_receiving(conn, open_core_inputs(args.core_inputs), log=lambda message: print(message, file=sys.stderr))
        report["api_requests"] = asyncio.run(check_receiving_api(conn, report["played_seasons"]))
        print(json.dumps(report, sort_keys=True, allow_nan=False))
    finally:
        database.close_connection()


if __name__ == "__main__":
    main()
