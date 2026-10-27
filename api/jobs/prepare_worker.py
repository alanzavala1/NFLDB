"""Internal subprocess for candidate preparation; use jobs.prepare to invoke it."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path


def prepare(seasons: list[int], *, core_inputs: Path | None = None, passing_inputs: Path | None = None,
            rebuild_all_analytics=False) -> None:
    # Never allow an internal worker invocation to fall back to the serving DB.
    path = os.environ.get('NFL_DB_PATH')
    if not path or not Path(path).is_absolute() or not Path(path).is_file():
        raise RuntimeError('Worker requires NFL_DB_PATH pointing to an existing candidate')

    import database
    if Path(database.DB_PATH).resolve() != Path(path).resolve():
        raise RuntimeError('Database was imported before the candidate path was configured')
    try:
        from ingest import run_ingest
        options = {}
        if core_inputs is not None:
            from pipeline.receiving_core_collection import open_core_inputs
            options['core_inputs'] = open_core_inputs(core_inputs)
        if passing_inputs is not None:
            if core_inputs is None:
                raise ValueError('Passing exports require captured core inputs')
            from pipeline.passing_inputs import PassingInputs
            options['passing_inputs'] = PassingInputs(passing_inputs)
        if rebuild_all_analytics:
            options['rebuild_all_analytics'] = True
        with database.write_lock:
            outcomes = run_ingest(seasons, log=lambda message: print(message, flush=True), **options)
            conn = database.get_connection()
            # A schedules-only refresh skips supplemental loading/analytics.
            # These local serving prerequisites must still be prepared offline.
            if not any(o.source == 'plays' and o.status == 'loaded' for o in outcomes):
                from pipeline.awards import load_player_awards
                load_player_awards(conn)
            database.ensure_indexes(strict=True)
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
    parser.add_argument('--core-inputs', type=Path)
    parser.add_argument('--passing-inputs', type=Path)
    parser.add_argument('--rebuild-all-analytics', action='store_true')
    args = parser.parse_args()
    prepare(args.seasons, core_inputs=args.core_inputs, passing_inputs=args.passing_inputs,
            rebuild_all_analytics=args.rebuild_all_analytics)


if __name__ == '__main__':
    main()
