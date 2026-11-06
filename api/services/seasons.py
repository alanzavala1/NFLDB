"""Published season coverage; optional feeds are checked independently."""
from sql_helpers import safe_query


def get_season_coverage() -> tuple[set[int], set[int]]:
    played = {row['season'] for row in safe_query('SELECT DISTINCT season FROM plays')}
    scheduled = {row['season'] for row in safe_query('SELECT DISTINCT season FROM schedules')}
    return played, scheduled
