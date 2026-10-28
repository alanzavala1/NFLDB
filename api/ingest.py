"""Offline season refresh orchestration, invoked by candidate preparation.

Source loading, storage and statistics have focused owners in pipeline/.
"""

from database import get_connection
from pipeline.analytics import prepare_analytics
from pipeline.loading import load_and_store_raw, load_advanced_stats, load_supplemental_data
from pipeline.player_stats import build_player_game_stats
from pipeline.receiving_build import has_official_receiving
from pipeline.receiving_inputs import verify_stored_ftn
from pipeline.source_results import SourceOutcome


def run_ingest(seasons: list[int], log=print, *, core_inputs=None, passing_inputs=None, rebuild_all_analytics=False) -> list[SourceOutcome]:
    """Load source feeds, build player stats, then prepare analytics for the batch."""
    conn = get_connection()
    from pipeline.passing_build import has_official_passing
    if (passing_inputs is None and has_official_passing(conn)) or (passing_inputs is not None and core_inputs is None):
        raise RuntimeError("Native passing snapshot requires captured core and passing inputs before any source refresh")
    if core_inputs is None and has_official_receiving(conn):
        raise RuntimeError("Official receiving snapshot requires captured offline inputs before any source refresh")
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

    if rebuild_all_analytics:
        analytics_seasons.update(row[0] for row in conn.execute(
            "SELECT DISTINCT season FROM plays WHERE season_type='REG'").fetchall())
        log(f"\nFull analytics rebuild: {sorted(analytics_seasons)}")
    advanced_seasons = sorted(analytics_seasons) if rebuild_all_analytics else seasons
    log(f"\nLoading advanced stats for {advanced_seasons}...")
    outcomes.extend(load_advanced_stats(conn, advanced_seasons, log=log))

    log(f"\nLoading supplemental vendor data for {seasons}...")
    outcomes.extend(load_supplemental_data(conn, seasons, log=log))

    if rebuild_all_analytics and core_inputs is not None:
        verify_stored_ftn(conn, core_inputs, sorted(analytics_seasons))
    analytics_options = {} if core_inputs is None else {"receiving_inputs": core_inputs}
    if passing_inputs is not None:
        analytics_options["passing_inputs"] = passing_inputs
    prepare_analytics(sorted(analytics_seasons), log=log, **analytics_options)
    return outcomes


if __name__ == '__main__':
    raise SystemExit('Use python -m jobs.prepare --source SOURCE --candidate NEW_DATABASE --seasons YEAR for offline preparation.')
