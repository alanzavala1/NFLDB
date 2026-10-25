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
                        help='Reuse captured plays/weekly inputs; does not enable new receiving splits')
    args = parser.parse_args(argv)
    options = {} if args.core_inputs is None else {'core_inputs': args.core_inputs}
    prepare_candidate(args.source, args.candidate, args.seasons, **options)


if __name__ == '__main__':
    main()
