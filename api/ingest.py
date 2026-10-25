"""Season refresh orchestration and the legacy local CLI.

Source loading, storage and statistics have focused owners in pipeline/.
"""
import argparse

from database import get_connection
from pipeline.analytics import prepare_analytics
from pipeline.loading import load_and_store_raw, load_advanced_stats, load_supplemental_data
from pipeline.player_stats import build_player_game_stats
from pipeline.source_results import SourceOutcome


def run_ingest(seasons: list[int], log=print, *, core_inputs=None) -> list[SourceOutcome]:
    """Load source feeds, build player stats, then prepare analytics for the batch."""
    conn = get_connection()
    options = {} if core_inputs is None else {"core_inputs": core_inputs}
    raw = load_and_store_raw(conn, seasons, log=log, **options)
    plays = raw.plays
    outcomes = list(raw.outcomes)

    if plays is None:
        # Every derived table below is built from play-by-play. Stop here rather
        # than materializing empty stats over a season that hasn't been played.
        # Schedules and rosters are already stored; re-run once nflverse
        # publishes plays and this completes normally.
        log(f"\nNo play-by-play for {seasons} yet — schedules and rosters are "
            f"loaded; skipping derived stats until plays are published.")
        return outcomes

    # A multi-season request may include an unplayed season with no asset.
    # Restrict downstream replacements to seasons actually downloaded.
    seasons = sorted(int(season) for season in plays['season'].unique())

    # Requested play seasons are replaced first. A weekly schema migration can
    # also refresh historical official data, so rebuild those dependent stats
    # one season at a time instead of loading all historical plays into memory.
    build_player_game_stats(conn, plays, seasons, log=log)
    analytics_seasons = set(seasons)
    weekly_seasons = {o.season for o in outcomes
                      if o.source == 'weekly_player_stats' and o.status == 'loaded'}
    for season in sorted(weekly_seasons - analytics_seasons):
        historical = conn.execute('SELECT * FROM plays WHERE season = ?', [season]).df()
        if not historical.empty:
            log(f'Official weekly data changed for {season}; rebuilding dependent player stats')
            build_player_game_stats(conn, historical, [season], log=log)
            analytics_seasons.add(season)

    log(f"\nLoading advanced stats for {seasons}...")
    outcomes.extend(load_advanced_stats(conn, seasons, log=log))

    log(f"\nLoading supplemental vendor data for {seasons}...")
    outcomes.extend(load_supplemental_data(conn, seasons, log=log))

    prepare_analytics(sorted(analytics_seasons), log=log)
    return outcomes


def main():
    import json
    import os
    import urllib.request
    import urllib.error

    parser = argparse.ArgumentParser(description="Ingest NFL data into DuckDB.")
    parser.add_argument("--seasons", type=int, nargs="+", default=[2025],
                        help="Season year(s) to load, e.g. --seasons 2024 2025")
    parser.add_argument("--api", default="http://localhost:8000",
                        help="API base URL to route through when server is running")
    args = parser.parse_args()

    # If the API server is running, route through it to avoid the DB file lock.
    via_api = []
    # force=true is admin-gated server-side; send the token if configured.
    # Absent/invalid → server 403s → HTTPError (a URLError) → falls to direct ingest.
    admin_token = os.environ.get("ADMIN_TOKEN")
    headers = {"X-Admin-Token": admin_token} if admin_token else {}
    for season in args.seasons:
        try:
            req = urllib.request.Request(
                f"{args.api}/seasons/{season}/load?force=true", method="POST",
                headers=headers,
            )
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read())
            print(f"Season {season}: triggered via API (status: {data.get('status')})")
            via_api.append(season)
        except urllib.error.URLError:
            break  # API not running — fall through to direct ingest

    direct = [s for s in args.seasons if s not in via_api]
    if direct:
        run_ingest(direct)
    else:
        print("\nIngest running inside the API server. Poll GET /seasons for status.")


if __name__ == "__main__":
    main()
