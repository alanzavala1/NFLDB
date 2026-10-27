"""Export and verify a passing Down preview; never writes a database."""
import argparse
import json
import os
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-inputs", type=Path, required=True)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-library", type=Path, required=True)
    args = parser.parse_args(argv)
    os.environ["NFL_TEST_MODE"] = "1"
    from pipeline.passing_preview import prepare_passing_preview
    result = prepare_passing_preview(args.core_inputs, args.exports, args.season,
                                     rscript=args.rscript, library=args.r_library)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
