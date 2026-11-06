"""Combine fresh core/passing seasons with unchanged captured history."""
import argparse
from pathlib import Path

from pipeline.refresh_inputs import replace_input_seasons


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('core-inputs', 'passing-inputs', 'fresh-core', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--fresh-passing', type=Path, nargs='+', required=True)
    args = parser.parse_args(argv)
    replace_input_seasons(args.core_inputs, args.passing_inputs, args.fresh_core, args.fresh_passing, args.output)


if __name__ == '__main__':
    main()
