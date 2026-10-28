"""Build, verify or atomically select an immutable local native release."""
import argparse
import json
from pathlib import Path

from pipeline.releases import create_release, verify_release
from pipeline.release_pointer import select_release


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build', help='Run full native validation and create a new release bundle')
    build.add_argument('--database', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--core-inputs', type=Path, required=True)
    build.add_argument('--passing-inputs', type=Path, required=True)
    build.add_argument('--watermarks', type=Path, help='Previously acknowledged stamps; no implicit upstream acknowledgment')
    verify = commands.add_parser('verify')
    verify.add_argument('--release', type=Path, required=True)
    select = commands.add_parser('select-local', help='Select a complete local bundle; does not deploy or upload')
    select.add_argument('--release', type=Path, required=True)
    select.add_argument('--pointer', type=Path, required=True)
    select.add_argument('--expected-pointer-sha256', help='Required for replacing an existing selection')
    args = parser.parse_args(argv)
    if args.command == 'build':
        marks = None if args.watermarks is None else json.loads(args.watermarks.read_bytes())
        result = create_release(args.database, args.output, core_inputs=args.core_inputs,
                                passing_inputs=args.passing_inputs, watermarks=marks)
    elif args.command == 'verify':
        result = verify_release(args.release)
    else:
        result = select_release(args.release, args.pointer, expected=args.expected_pointer_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
