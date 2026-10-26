"""Read-only validation of a specified prepared database; never repairs or publishes."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--core-inputs', type=Path,
                        help='Run complete official receiving integration checks against bound captures (publication remains blocked)')
    args = parser.parse_args(argv)
    path = args.database.resolve()
    if not path.is_file() or Path(f'{path}.wal').exists():
        raise RuntimeError('Validation requires an existing database with no pending WAL')
    os.environ['NFL_DB_PATH'] = str(path)
    os.environ['NFL_DB_READ_ONLY'] = '1'
    import database
    if Path(database.DB_PATH).resolve() != path or database._conn is not None:
        raise RuntimeError('Run validation in a fresh process configured for the candidate')
    try:
        from pipeline.validation import validate_snapshot
        from pipeline.api_checks import check_api
        conn = database.get_connection()
        options = {}
        if args.core_inputs is not None:
            from pipeline.receiving_core_collection import open_core_inputs
            options = {'receiving_inputs': open_core_inputs(args.core_inputs),
                       'log': lambda message: print(message, file=sys.stderr)}
        report = validate_snapshot(conn, **options)
        report['api_requests'] = asyncio.run(check_api(conn, report['played_seasons']))
        print(json.dumps(report, sort_keys=True))
    finally:
        database.close_connection()


if __name__ == '__main__':
    main()
