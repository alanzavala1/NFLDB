"""Plan native refreshes cheaply, then prepare a complete release in a new workspace."""
import argparse
import json
import os
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan')
    plan.add_argument('--pointer', required=True)
    plan.add_argument('--season', type=int)
    plan.add_argument('--force', action='store_true')
    plan.add_argument('--output', type=Path, required=True)
    prepare = commands.add_parser('prepare')
    for name in ('plan', 'download', 'workspace', 'rscript', 'r-library'):
        prepare.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(argv)
    os.environ.setdefault('NFL_TEST_MODE', '1')
    from automation.refresh_plan import plan_refresh, write_record
    if args.command == 'plan':
        if args.output.exists() or args.output.is_symlink():
            raise FileExistsError(args.output)
        from publication.gcs import GCloudStore
        result = plan_refresh(args.pointer, GCloudStore(), season=args.season, force=args.force)
        write_record(args.output, result)
    else:
        from automation.native_refresh import prepare_refresh
        result = prepare_refresh(args.plan, args.download, args.workspace,
                                 rscript=args.rscript, library=args.r_library)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
