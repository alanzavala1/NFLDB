"""Convert captured inputs or group converted runs; no downloads or DB writes.

This prepares the input boundary for main-build integration. It does not build
analytics, replace player_splits or authorize a snapshot for publication.
"""
import argparse
from pathlib import Path

from pipeline.receiving_core_inputs import export_core_inputs
from pipeline.receiving_core_collection import assemble_core_inputs


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--exports", type=Path, help="Completed receiving run to convert")
    source.add_argument("--bundles", type=Path, nargs="+", help="Converted runs to index together")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rscript", type=Path)
    parser.add_argument("--r-library", type=Path)
    args = parser.parse_args(argv)
    if args.exports is not None:
        if args.rscript is None or args.r_library is None:
            parser.error("--exports requires --rscript and --r-library")
        inputs = export_core_inputs(args.exports, args.output, rscript=args.rscript, library=args.r_library)
    else:
        if args.rscript is not None or args.r_library is not None:
            parser.error("--bundles only reads captured files; omit R runtime options")
        inputs = assemble_core_inputs(args.bundles, args.output)
    print(f"Captured inputs ready: {inputs.directory}; {inputs.revision()}")


if __name__ == "__main__":
    main()
