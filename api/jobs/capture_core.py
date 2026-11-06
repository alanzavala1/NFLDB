"""Capture one fresh native season with verified upstream RDS provenance."""
import argparse
from pathlib import Path

from pipeline.core_capture import capture_core


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rscript', type=Path, required=True)
    parser.add_argument('--r-library', type=Path, required=True)
    args = parser.parse_args(argv)
    capture_core(args.output, args.season, rscript=args.rscript, library=args.r_library)


if __name__ == '__main__':
    main()
