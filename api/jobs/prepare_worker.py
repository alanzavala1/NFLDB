"""Internal subprocess for candidate preparation; use jobs.prepare to invoke it."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path


def prepare(seasons: list[int]) -> None:
    # Never allow an internal worker invocation to fall back to the serving DB.
    path = os.environ.get('NFL_DB_PATH')
    if not path or not Path(path).is_absolute() or not Path(path).is_file():
        raise RuntimeError('Worker requires NFL_DB_PATH pointing to an existing candidate')

    import database
    if Path(database.DB_PATH).resolve() != Path(path).resolve():
        raise RuntimeError('Database was imported before the candidate path was configured')
    try:
        from ingest import run_ingest
        with database.write_lock:
            outcomes = run_ingest(seasons, log=lambda message: print(message, flush=True))
            conn = database.get_connection()
            conn.execute('''CREATE OR REPLACE TABLE snapshot_preparation (
                format_version INTEGER, requested_seasons JSON,
                source_outcomes JSON, prepared_at TIMESTAMPTZ
            )''')
            conn.execute(
                'INSERT INTO snapshot_preparation VALUES (1, ?, ?, current_timestamp)',
                [json.dumps(seasons), json.dumps([asdict(o) for o in outcomes])],
            )
            conn.execute('CHECKPOINT')
    finally:
        database.close_connection()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seasons', type=int, nargs='+', required=True)
    prepare(parser.parse_args().seasons)


if __name__ == '__main__':
    main()
