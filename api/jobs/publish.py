"""Upload or verify an immutable native release; never select or deploy it."""
import argparse
import json
from pathlib import Path

from publication.gcs import GCloudStore
from publication.releases import publish, verify


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
    args = parser.parse_args(argv)
    store = GCloudStore()
    if args.command == 'upload':
        result = publish(args.release, args.captures, args.destination, store)
    else:
        result = verify(args.destination, store, marker_generation=args.manifest_generation,
                        marker_sha256=args.manifest_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
