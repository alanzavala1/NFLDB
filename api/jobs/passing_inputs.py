"""Index validated native passing exports for an offline analytics build."""
import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--core-inputs", type=Path, required=True)
    args = parser.parse_args()
    os.environ["NFL_TEST_MODE"] = "1"
    from pipeline.passing_inputs import assemble_passing_inputs
    from pipeline.receiving_core_collection import open_core_inputs
    assemble_passing_inputs(args.exports, args.output, open_core_inputs(args.core_inputs))


if __name__ == "__main__":
    main()
