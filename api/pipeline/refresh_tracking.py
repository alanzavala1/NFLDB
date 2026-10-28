"""Acknowledgment means this run observed a stable, successfully consumed asset."""
from pipeline.vendor_sources import WATCHED_VENDOR_SOURCES
from pipeline.upstream_assets import CORE_ASSETS


def acknowledged_watermarks(previous, season, before, after, outcomes, *, captured_core=False, core_versions=None):
    result = dict(previous)
    for key, stamp in before.items():
        if not stamp or stamp != after.get(key):
            continue  # Changed during preparation, missing, or never observed.
        if key in CORE_ASSETS:
            if not core_versions or core_versions.get(key) != stamp:
                continue
            sources = ('plays', 'weekly_player_stats') if key == 'playstats' else (
                'plays' if key == 'pbp_rds' else 'weekly_player_stats',)
            if all(any(item.source == source and item.season == season and item.status == 'loaded'
                       for item in outcomes) for source in sources):
                result[f'{key}:{season}'] = stamp
            continue
        spec = WATCHED_VENDOR_SOURCES.get(key)
        if not spec and key not in ('pbp', 'weekly'):
            continue
        if captured_core and key in ('pbp', 'weekly'):
            continue  # Reusing a capture does not acknowledge today's upstream version.
        source = spec.name if spec else {'pbp': 'plays', 'weekly': 'weekly_player_stats'}[key]
        if any(item.source == source and item.season == season
               and (item.status == 'loaded' or (spec and item.status == 'empty')) for item in outcomes):
            result[f'{key}:{season}'] = stamp
    return result
