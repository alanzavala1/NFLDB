"""Upload, select or download a native release; deployment is a separate operation."""
import argparse
import json
from pathlib import Path

from publication.gcs import GCloudStore
from publication.releases import publish, verify
from publication.selection import read_selection, select_release
from publication.downloads import download_selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    upload = commands.add_parser('upload')
    upload.add_argument('--release', type=Path, required=True)
    upload.add_argument('--captures', type=Path, required=True)
    upload.add_argument('--destination', required=True, help='New gs://bucket/prefix/release-id')
    check = commands.add_parser('verify')
    check.add_argument('--destination', required=True)
    check.add_argument('--manifest-generation')
    check.add_argument('--manifest-sha256')
    select = commands.add_parser('select')
    select.add_argument('--pointer', required=True)
    select.add_argument('--destination', required=True)
    select.add_argument('--expected-generation', required=True, help='Generation read at job start; 0 only for initial creation')
    select.add_argument('--manifest-generation', required=True)
    select.add_argument('--manifest-sha256', required=True)
    current = commands.add_parser('current')
    download = commands.add_parser('download')
    for command in (current, download):
        command.add_argument('--pointer', required=True)
        command.add_argument('--pointer-generation')
        command.add_argument('--pointer-sha256')
    download.add_argument('--output', type=Path, required=True)
    download.add_argument('--include-captures', action='store_true')
    args = parser.parse_args(argv)
    store = GCloudStore()
    if args.command == 'upload':
        result = publish(args.release, args.captures, args.destination, store)
    elif args.command == 'verify':
        result = verify(args.destination, store, marker_generation=args.manifest_generation,
                        marker_sha256=args.manifest_sha256)
    elif args.command == 'select':
        result = select_release(args.pointer, args.destination, store, expected_generation=args.expected_generation,
                                manifest_generation=args.manifest_generation, manifest_sha256=args.manifest_sha256)
    else:
        options = dict(pointer_generation=args.pointer_generation, pointer_sha256=args.pointer_sha256)
        result = (read_selection(args.pointer, store, **options) if args.command == 'current' else
                  download_selected(args.pointer, args.output, store, include_captures=args.include_captures, **options))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
