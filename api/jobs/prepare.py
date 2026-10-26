"""Build a candidate without modifying or publishing the source database.

Run from api/ with its locked environment. The source must be closed and have
no pending WAL. Existing candidates are never overwritten. Preparation checks
core counts, analytics, statistical identities and representative HTTP reads.
Publishing and refresh watermark updates remain separate.
"""
import argparse
from pathlib import Path

from pipeline.snapshots import prepare_candidate


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Existing, closed database')
    parser.add_argument('--candidate', type=Path, required=True, help='New working database path')
    parser.add_argument('--seasons', type=int, nargs='+', required=True)
    parser.add_argument('--core-inputs', type=Path,
                        help='Use captured core inputs and official receiving exports (integration is not yet publishable)')
    parser.add_argument('--rebuild-all-analytics', action='store_true',
                        help='Refresh advanced inputs and rebuild analytics for every stored REG season')
    args = parser.parse_args(argv)
    options = {} if args.core_inputs is None else {'core_inputs': args.core_inputs}
    if args.rebuild_all_analytics:
        options['rebuild_all_analytics'] = True
    prepare_candidate(args.source, args.candidate, args.seasons, **options)


if __name__ == '__main__':
    main()
