"""Offline season refresh — the only place that ingests.

Runs in GitHub Actions on a schedule, against the database pulled from GCS.
Never inside the container serving traffic: ingest is a heavy single-writer job
that once held `write_lock` against every reader and crash-looped the service
(see the Phase 0 commit).

Two subcommands, because the split is what keeps a frequent schedule cheap:

  check   compares nflverse's published stamps against ours and reports
          whether there is anything to do. Reads a few bytes.
  ingest  pulls the season in and rewrites the stamps. Only runs when `check`
          says something moved.

One stamp per upstream asset, not one for the season. nflverse publishes
play-by-play, snap counts, charting and the vendor stat feeds independently, so
a single play-by-play watermark can report "nothing to do" while half of what
the ingest consumes has in fact moved — see WATCHED_ASSETS for what that cost.

The watermarks deliberately live in their own small GCS object rather than
inside the database. Putting them in the database would mean downloading 477 MB
on every run just to discover there was nothing to do — and most runs have
nothing to do, since nflverse republishes a season only as its games are
charted.

Vendor stamps acknowledge successfully observed versions: loaded rows or an
explicit empty outcome. Failed/missing downloads keep their previous stamp and
stored data, so an optional outage is not recorded as an up-to-date source.

Exit status is always 0 on a clean run: "no new data" is a normal outcome, not
a failure.
"""
from __future__ import annotations

import json
import os
import sys
import argparse
from pathlib import Path
from functools import cache

import httpx
import pandas as pd

from pipeline.vendor_sources import WATCHED_VENDOR_SOURCES
from pipeline.context_sources import SCHEDULE_CSV

RELEASE_API = "https://api.github.com/repos/nflverse/nflverse-data/releases/tags/{tag}"

# Recorded when a season is ingested before its play-by-play exists, so a
# schedules-only load isn't repeated every run while we wait for kickoff.
SCHEDULES_ONLY = "schedules-only"

# The upstream assets worth watching, as (watermark key, release tag, asset).
#
# Watching only play-by-play was a bug with a visible symptom. nflverse
# publishes each of these on its own schedule, and snap counts lag plays: on
# 2026-09-11 the SF@LA game page rendered an O-line unit grade floating over an
# empty field, because player placement comes entirely from `snap_counts` while
# the grade comes from `plays`. It healed only because nflverse happened to
# republish play-by-play afterwards, which is coincidence, not a guarantee.
# With every consumed asset watched, a late snap-counts publication moves a
# watermark of its own and the next run picks it up.
#
# `{season}` is filled in per run. The PFR and NGS files are not season-scoped —
# one file carries every year — so their stamp moves when nflverse republishes
# any season. That can occasionally trigger a refresh our season didn't need.
# A wasted rebuild is much cheaper than a game page that contradicts itself, and
# whole-file is the only granularity the upstream offers.
#
# Deliberately NOT watched: injuries, depth charts, draft picks, combine and the
# ID map. They are reference data on their own cadence — depth charts change
# most days — and being a day behind on them contradicts nothing. Watching them
# would pull the 477MB database down nightly to fold in a practice-squad move.
WATCHED_ASSETS = (
    ("pbp",           "pbp",           "play_by_play_{season}.parquet"),
    # Official weekly stats — the table counting stats reconcile to. It was
    # missing from this list, and unwatched is how it sat two seasons stale
    # without anything noticing.
    ("weekly",        "stats_player",  "stats_player_week_{season}.parquet"),
    *((key, WATCHED_VENDOR_SOURCES[key].release, WATCHED_VENDOR_SOURCES[key].asset)
      for key in ('snaps', 'ftn', 'pfr_pass', 'pfr_rush', 'pfr_rec', 'pfr_def',
                  'ngs_passing', 'ngs_rushing', 'ngs_receiving')),
)


def _log(msg: str) -> None:
    print(msg, flush=True)


def upstream_latest_season() -> int:
    """The newest season the NFL has scheduled, per the nflverse schedule feed.

    Deliberately not `config.CURRENT_SEASON`, which reports the newest season
    already in our database. Asking the database what to fetch next can never
    discover a new season — it would answer with the one it already has. The
    schedule feed is published months ahead, so it is the thing that knows a
    new season exists at all.
    """
    games = pd.read_csv(SCHEDULE_CSV, usecols=["season"])
    return int(games["season"].max())


@cache
def _release_assets(tag: str) -> dict[str, str]:
    """`{asset name: updated_at}` for one nflverse release, fetched once per run.

    Several watched assets share a release, so the cache turns ten lookups into
    five requests. `GITHUB_TOKEN` is used when the workflow provides it —
    unauthenticated calls are rate-limited per IP, and Actions runners share
    theirs with everyone else on the same host.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.get(RELEASE_API.format(tag=tag), headers=headers, timeout=30, follow_redirects=True)
    r.raise_for_status()
    assets = {a["name"]: a.get("updated_at") for a in r.json().get("assets", []) if a.get("name")}
    return assets


def remote_watermarks(season: int) -> dict[str, str | None]:
    """Upstream `updated_at` for every watched asset, keyed by watermark name.

    A value of None means the asset isn't published yet or is outside its
    declared coverage. For play-by-play that
    is the normal state of a season before its first games are charted, not an
    error; for the rest it simply means there is nothing of theirs to be stale
    against.
    """
    return _watched_watermarks(season, WATCHED_ASSETS)


def _watched_watermarks(season, assets):
    out: dict[str, str | None] = {}
    for key, tag, name in assets:
        spec = WATCHED_VENDOR_SOURCES.get(key)
        if spec and season < spec.first_season:
            out[key] = None
            continue
        out[key] = _release_assets(tag).get(name.format(season=season))
    return out


def native_remote_watermarks(season):
    from pipeline.upstream_assets import observe_core_assets, asset_version
    out = _watched_watermarks(season, WATCHED_ASSETS[2:])
    out.update({key: asset_version(asset) for key, asset in observe_core_assets(season).items()})
    return out


def cmd_native_check(watermarks_path):
    season = _resolve_season()
    _release_assets.cache_clear()
    moved = _moved(read_watermarks(watermarks_path), season, native_remote_watermarks(season))
    changed = bool(moved) or os.environ.get('REFRESH_FORCE') == '1'
    _log(f'Native season {season}: ' + (', '.join(moved) if moved else 'all watched assets unchanged'))
    _emit(changed='true' if changed else 'false', season=season)
    return 0


def read_watermarks(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        # Absent or unreadable is the first-run case, not an error.
        return {}


def write_watermarks(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _emit(**outputs) -> None:
    """Report to the workflow and to whoever reads the log."""
    for k, v in outputs.items():
        _log(f"  {k}={v}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            for k, v in outputs.items():
                fh.write(f"{k}={v}\n")


def _resolve_season() -> int:
    override = os.environ.get("REFRESH_SEASON")
    return int(override) if override else upstream_latest_season()


def _moved(marks: dict, season: int, remote: dict) -> list[str]:
    """Which watched assets differ from what we last ingested.

    An asset still unpublished upstream never counts as moved: a season with no
    NGS yet is not a reason to rebuild, and recording None for it would make the
    first real publication indistinguishable from no change.
    """
    return [
        key for key, stamp in remote.items()
        if stamp is not None and marks.get(f"{key}:{season}") != stamp
    ]


def cmd_check(watermarks_path: str) -> int:
    season = _resolve_season()
    force = os.environ.get("REFRESH_FORCE") == "1"
    marks = read_watermarks(watermarks_path)
    remote = remote_watermarks(season)
    local_pbp = marks.get(f"pbp:{season}")

    _log(f"Season {season}" + (" (forced)" if force else ""))
    for key, _, _ in WATCHED_ASSETS:
        ours, theirs = marks.get(f"{key}:{season}"), remote[key]
        if theirs is None:
            state = "not published yet"
        elif ours == theirs:
            state = "up to date"
        else:
            state = f"MOVED   ours={ours or 'never'} upstream={theirs}"
        _log(f"  {key:<13} {state}")

    if force:
        reason = "forced"
        changed = True
    elif remote["pbp"] is None:
        # No plays upstream. Worth one pass to pick up schedules and rosters,
        # which are published months ahead — but only once. Nothing else here
        # can matter while the season has not been played.
        changed = local_pbp != SCHEDULES_ONLY
        reason = "schedules not yet loaded" if changed else "no plays upstream, schedules already loaded"
    else:
        moved = _moved(marks, season, remote)
        changed = bool(moved)
        if moved:
            reason = "republished upstream: " + ", ".join(moved)
        else:
            reason = "every watched asset unchanged since last ingest"

    _log(f"\n{'CHANGED' if changed else 'NO CHANGE'}: {reason}")
    _emit(changed="true" if changed else "false", season=season)
    return 0


def cmd_ingest(watermarks_path: str) -> int:
    if os.environ.get('NFL_DB_READ_ONLY') != '0':
        raise RuntimeError('Offline ingest requires NFL_DB_READ_ONLY=0; use jobs.prepare for isolated candidates')
    # Imported here, not at module scope: `check` must not need a database.
    from database import get_connection, write_lock
    from ingest import run_ingest

    season = _resolve_season()
    # Read the stamps BEFORE ingesting. Anything nflverse publishes while the
    # rebuild is running belongs to the next run, and recording it now would
    # mark data we never actually pulled as ingested.
    remote = remote_watermarks(season)

    _log(f"Ingesting season {season}...")
    get_connection()
    # Hold the write lock for the whole run, matching the app's single-writer
    # contract. Nothing else is running here, but it keeps the invariant true
    # wherever run_ingest is called from.
    with write_lock:
        outcomes = run_ingest([season], log=_log)

    marks = read_watermarks(watermarks_path)
    if remote["pbp"] is None and any(
        o.source == 'schedules' and o.season == season and o.status == 'loaded' for o in outcomes
    ) and not any(o.source == 'plays' and o.status == 'loaded' for o in outcomes):
        # Schedules and rosters only — there is nothing else to have ingested,
        # so leave the other keys alone rather than claiming them.
        marks[f"pbp:{season}"] = SCHEDULES_ONLY
    else:
        for key, stamp in remote.items():
            if stamp is not None:
                spec = WATCHED_VENDOR_SOURCES.get(key)
                source = spec.name if spec else {'pbp': 'plays', 'weekly': 'weekly_player_stats'}[key]
                if not any(
                    o.source == source and o.season == season
                    and (o.status == 'loaded' or (spec and o.status == 'empty')) for o in outcomes
                ):
                    # Optional failures retain stored data and their old stamp.
                    # A successfully read empty asset acknowledges this version
                    # without claiming rows were loaded; its outcome says empty.
                    continue
                marks[f"{key}:{season}"] = stamp

    write_watermarks(watermarks_path, marks)
    _log("\nIngested {}; watermarks now:".format(season))
    for key, _, _ in WATCHED_ASSETS:
        _log(f"  {key:<13} {marks.get(f'{key}:{season}') or '(unpublished)'}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == 'prepare':
        parser = argparse.ArgumentParser(description='Prepare a native release without editing the published database or watermarks')
        parser.add_argument('watermarks', type=Path)
        for name in ('source', 'candidate', 'release', 'core-inputs', 'passing-inputs'):
            parser.add_argument('--'+name, type=Path, required=True)
        parser.add_argument('--seasons', type=int, nargs='+', required=True)
        args = parser.parse_args(argv[2:])
        from pipeline.refresh_release import prepare_refresh_release
        def observe(year):
            _release_assets.cache_clear()  # Re-read remote versions after the build.
            return native_remote_watermarks(year)
        prepare_refresh_release(args.source, args.candidate, args.release, args.seasons,
            core_inputs=args.core_inputs, passing_inputs=args.passing_inputs,
            previous_watermarks=read_watermarks(str(args.watermarks)), observe=observe, log=_log)
        return 0
    if len(argv) < 2 or argv[1] not in ("check", "native-check", "ingest"):
        print(__doc__)
        print("usage: python -m jobs.refresh {check|native-check|ingest|prepare} [watermarks.json]; prepare --help for native releases")
        return 2
    path = argv[2] if len(argv) > 2 else "watermarks.json"
    if argv[1] == 'native-check':
        return cmd_native_check(path)
    return cmd_check(path) if argv[1] == "check" else cmd_ingest(path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
