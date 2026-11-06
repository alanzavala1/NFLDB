"""Pack or restore captured native inputs without downloading or recalculating."""
import argparse
import json
from pathlib import Path

from pipeline.capture_archive import pack_captures, restore_captures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    pack = commands.add_parser('pack')
    pack.add_argument('--core-inputs', type=Path, required=True)
    pack.add_argument('--passing-inputs', type=Path, required=True)
    pack.add_argument('--output', type=Path, required=True)
    restore = commands.add_parser('restore')
    restore.add_argument('--archive', type=Path, required=True)
    restore.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'pack':
        record = pack_captures(args.core_inputs, args.passing_inputs, args.output)
        result = {'archive': str(args.output), 'files': len(record['files']), 'revisions': record['revisions']}
    else:
        result = {key: str(value) for key, value in restore_captures(args.archive, args.output).items()}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
