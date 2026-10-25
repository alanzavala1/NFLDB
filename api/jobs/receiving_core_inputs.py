"""Convert a completed receiving run's captured inputs; no downloads or DB writes.

This prepares the input boundary for main-build integration. It does not build
analytics, replace player_splits or authorize a snapshot for publication.
"""
import argparse
from pathlib import Path

from pipeline.receiving_core_inputs import export_core_inputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-library", type=Path, required=True)
    args = parser.parse_args()
    inputs = export_core_inputs(args.exports, args.output, rscript=args.rscript, library=args.r_library)
    print(f"Captured inputs ready: {inputs.directory}; {inputs.revision()}")


if __name__ == "__main__":
    main()
