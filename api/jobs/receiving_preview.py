"""Run official R and build receiving counts in a separate, non-publishable DB.

The source must be closed. Existing candidate/export paths are never replaced.
This does not run ingestion or the full snapshot validation/publication gate.
"""
import argparse
import json
from pathlib import Path

from pipeline.receiving_preview import prepare_receiving_preview


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-library", type=Path, required=True)
    parser.add_argument("--seasons", type=int, nargs="+", required=True)
    args = parser.parse_args(argv)
    report = prepare_receiving_preview(args.source, args.candidate, args.exports, args.seasons,
                                       rscript=args.rscript, library=args.r_library)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
