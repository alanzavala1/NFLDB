"""Coordinate source validation and storage; football calculations live separately."""
from typing import TYPE_CHECKING

from config import FIRST_SEASON
from pipeline.awards import load_player_awards
from pipeline.context_sources import fetch_schedules, fetch_rosters
from pipeline.source_results import SourceError, SourceOutcome, RawLoad
from pipeline.sources import PLAYS_KEEP_COLUMNS, fetch_play_by_play, fetch_weekly_stats
from pipeline.vendor_sources import ADVANCED_SOURCES, SUPPLEMENTAL_SOURCES, fetch_vendor
from pipeline.storage import (
    upsert_by_season, replace_table, weekly_schema_is_legacy, store_weekly_stats,
)

if TYPE_CHECKING:
    from pipeline.receiving_core_inputs import ReceivingCoreInputs
    from pipeline.receiving_core_collection import ReceivingCoreCollection


def _weekly_scope(conn, seasons: list[int]) -> tuple[bool, list[int]]:
    legacy = weekly_schema_is_legacy(conn)
    if not legacy:
        return False, list(seasons)
    # Replacing an old schema drops its whole table. An older-season refresh
    # must not discard newer weekly seasons already stored there.
    latest_stored = conn.execute('SELECT MAX(season) FROM weekly_player_stats').fetchone()[0]
    latest = max(max(seasons), latest_stored if latest_stored is not None else max(seasons))
    return True, list(range(FIRST_SEASON, int(latest) + 1))


def load_and_store_raw(conn, seasons: list[int], log=print, *,
                       core_inputs: "ReceivingCoreInputs | ReceivingCoreCollection | None" = None):
    log(f"Loading play-by-play for {seasons}...")
    weekly_feed = None
    if core_inputs is None:
        feed = fetch_play_by_play(seasons, log=log)
    else:
        # A legacy weekly migration refreshes all history. Require those same
        # captures up front rather than silently downloading a different revision
        # or discovering missing years after replacing plays/schedules.
        _, wanted = _weekly_scope(conn, seasons)
        feed, weekly_feed = core_inputs.load_feeds(seasons, wanted)
        log(f"  reusing captured inputs: {core_inputs.revision()}")
    plays = feed.data

    log("Loading schedules...")
    schedule_feed = fetch_schedules(seasons)
    schedules = schedule_feed.data
    # A 404 is only a legitimate schedules-only state while games remain
    # unplayed. Do not call a completed season unpublished after an asset vanishes.
    for season in feed.not_found_seasons:
        completed = schedules[
            schedules['season'].eq(season)
            & schedules['away_score'].notna() & schedules['home_score'].notna()
        ]
        if not completed.empty:
            raise SourceError('plays', season, 'asset not found for a season with completed games')

    log('Loading rosters...')
    roster_feed = fetch_rosters(seasons)
    required_rosters = sorted(set(feed.loaded_seasons) - set(roster_feed.loaded_seasons))
    if required_rosters:
        raise SourceError('rosters', required_rosters[0], 'roster data is required when plays are available')

    if plays is None:
        log(f"  no play-by-play assets for unplayed seasons {seasons} — continuing")
    else:
        log(f"  keeping {len(plays.columns)}/{len(PLAYS_KEEP_COLUMNS)} pbp columns")
        options = {} if core_inputs is None else {"evolve_schema": True}
        upsert_by_season(conn, "plays", plays, feed.loaded_seasons, log=log, **options)

    upsert_by_season(conn, "schedules", schedules, seasons, log=log)

    if roster_feed.data is not None:
        upsert_by_season(conn, "rosters", roster_feed.data, roster_feed.loaded_seasons, log=log)

    log(f"Loading weekly player stats...")
    outcomes = feed.outcomes('plays') + schedule_feed.outcomes('schedules') + roster_feed.outcomes('rosters')
    weekly_options = {} if weekly_feed is None else {"captured_feed": weekly_feed}
    outcomes.extend(load_weekly_player_stats(conn, seasons, log=log, required_seasons=feed.loaded_seasons,
                                              **weekly_options))
    if core_inputs is not None:
        # Store provenance alongside the existing source outcomes; the ordinary
        # candidate worker already persists these in snapshot_preparation.
        outcomes = [SourceOutcome(item.source, item.season, item.status, item.rows,
                                  core_inputs.revision() if item.source in ('plays', 'weekly_player_stats')
                                  else item.detail) for item in outcomes]

    return RawLoad(plays, outcomes)


def load_weekly_player_stats(
    conn, seasons: list[int], log=print, *, required_seasons: list[int] | None = None,
    captured_feed=None,
) -> list[SourceOutcome]:
    """Official weekly player stats, the source of truth counting stats reconcile to.

    On the legacy schema this rebuilds every season rather than the requested
    ones. `_upsert_by_season` inserts only columns common to the table and the
    frame — right for season-to-season drift, wrong for a feed migration, where
    it would keep the old 53-column table, drop all 102 new columns, and leave
    the renamed ones NULL. Rebuilding means fetching the full history, because
    dropping the table would otherwise discard the seasons not being ingested.
    """
    legacy, wanted = _weekly_scope(conn, seasons)
    if legacy:
        log(f"  legacy weekly schema (pre-stats_player rename) — rebuilding "
            f"{len(wanted)} seasons from the new feed")

    if captured_feed is not None:
        if set(captured_feed.loaded_seasons) != set(wanted) or captured_feed.not_found_seasons:
            raise SourceError('weekly_player_stats', None, 'captured inputs do not cover the weekly refresh')
        feed = captured_feed
    else:
        feed = fetch_weekly_stats(wanted, log=log)
    required_missing = sorted(set(required_seasons or []) - set(feed.loaded_seasons))
    if required_missing:
        raise SourceError('weekly_player_stats', required_missing[0],
                          'official stats are required when play-by-play is available')
    if legacy and feed.not_found_seasons:
        raise SourceError('weekly_player_stats', feed.not_found_seasons[0],
                          'legacy schema rebuild is incomplete; keeping the stored table')

    weekly = feed.data
    if weekly is None:
        log(f"  no official weekly assets for {seasons}; leaving stored data unchanged")
        return feed.outcomes('weekly_player_stats')

    # nflverse ships ~21 rows per season with no player_id and no player_name —
    # a SEA week 1 2026 row with every stat zero is one. They carry nothing, and
    # downstream they are poison: player_game_stats is keyed on player_id and
    # inherits the NULL, then /leaders returns 500 because LeagueLeader.player_id
    # is a required string. That is how it surfaced, on the current season, the
    # first time a season's stats were rebuilt from this feed.
    #
    # Dropped here rather than filtered in each reader, because the stored table
    # is the shared surface: splits, ratings and the offensive build all read it.
    orphans = int(weekly["player_id"].isna().sum())
    if orphans:
        weekly = weekly[weekly["player_id"].notna()]
        log(f"  dropped {orphans} rows with no player_id")

    for season in required_seasons or []:
        if not weekly['season'].eq(season).any():
            raise SourceError('weekly_player_stats', season, 'asset has no identified players for a played season')

    store_weekly_stats(conn, weekly, sorted(feed.loaded_seasons), legacy=legacy, log=log)
    feed.data = weekly
    return feed.outcomes('weekly_player_stats')


def load_advanced_stats(conn, seasons: list[int], log=print) -> list[SourceOutcome]:
    """Store validated vendor frames; missing/failed years keep their old rows."""
    outcomes = []
    for spec in ADVANCED_SOURCES:
        feed = fetch_vendor(spec, seasons, log=log)
        if feed.data is not None:
            upsert_by_season(conn, spec.name, feed.data, feed.loaded_seasons, log=log)
        outcomes.extend(feed.outcomes)
    return outcomes


def load_supplemental_data(conn, seasons: list[int], log=print) -> list[SourceOutcome]:
    """Store optional reference/snapshot feeds, then prepare the static awards seed."""
    outcomes = []
    for spec in SUPPLEMENTAL_SOURCES:
        feed = fetch_vendor(spec, seasons, log=log)
        if feed.data is not None:
            if spec.scope in ('reference', 'snapshot'):
                replace_table(conn, spec.name, feed.data, log=log)
            else:
                upsert_by_season(conn, spec.name, feed.data, feed.loaded_seasons, log=log)
        outcomes.extend(feed.outcomes)
    # This is local preparation, not an optional network feed. A seed/write
    # failure must stop the pipeline rather than claim successful preparation.
    log('  Player awards (seed)...')
    load_player_awards(conn, log=log)
    return outcomes
