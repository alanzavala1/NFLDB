"""App-wide constants and configuration."""
import os
from datetime import datetime

from data_errors import is_missing_data_error

FIRST_SEASON = 1999


def _calendar_season_guess() -> int:
    """Best guess at the current season when the schedule can't be read.

    The NFL opens the Thursday after Labor Day, so a season is never under way
    before ~Sept 4 and always is by mid-month. The old rule (month >= 9) claimed
    the new season on Sept 1 — up to ten days before a single game was played,
    and well before nflverse publishes anything for it.
    """
    now = datetime.now()
    if now.month > 9 or (now.month == 9 and now.day >= 15):
        return now.year
    return now.year - 1


def _latest_scheduled_season() -> int | None:
    """Newest scheduled season, or None for an empty/missing schedule feed.

    `database` is imported lazily so this module stays importable without a
    database — tests seed their own connection, and tooling imports config
    without ever serving a request.
    """
    if os.environ.get("NFL_TEST_MODE"):
        return None
    try:
        from database import query_to_dict
        rows = query_to_dict("SELECT MAX(season) AS season FROM schedules")
        if rows and rows[0]["season"] is not None:
            return int(rows[0]["season"])
    except Exception as _data_error:
        if not is_missing_data_error(_data_error):
            raise
        pass
    return None


# Data first: a season is current once the schedule covers it, not once the
# calendar says so. Schedules are published months ahead, so this flips as soon
# as the new season is ingested — and never claims a season we hold no data for.
CURRENT_SEASON = _latest_scheduled_season() or _calendar_season_guess()


# Compatibility exports; static football definitions do not open a database.
from team_definitions import TEAM_NAMES, RELOCATIONS, MODERN_TEAM_ALIASES, era_team_case, DIVISIONS
