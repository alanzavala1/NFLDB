"""Build a candidate without modifying or publishing the source database.

Run from api/ with its locked environment. The source must be closed and have
no pending WAL. Existing candidates are never overwritten. This first checkpoint
checks preparation and core row coverage; it does not certify a release.
"""
import argparse
from pathlib import Path

from pipeline.snapshots import prepare_candidate


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Existing, closed database')
    parser.add_argument('--candidate', type=Path, required=True, help='New working database path')
    parser.add_argument('--seasons', type=int, nargs='+', required=True)
    args = parser.parse_args(argv)
    prepare_candidate(args.source, args.candidate, args.seasons)


if __name__ == '__main__':
    main()
