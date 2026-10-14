"""Weekly team injury reports for HTTP and assistant consumers."""
from config import CURRENT_SEASON
from sql_helpers import safe_query


def get_team_injuries(team: str, season: int | None = None, week: int | None = None) -> list[dict]:
    """Most recent injury report for the team. If `week` is omitted, returns
    the latest week we have data for in the given season."""
    if season is None:
        season = CURRENT_SEASON
    params: list = [team, season]
    week_clause = ""
    if week is not None:
        week_clause = " AND week = ?"
        params.append(week)
    rows = safe_query(f"""
        WITH latest AS (
            SELECT MAX(week) AS w FROM injuries
            WHERE team = ? AND season = ?{week_clause}
        )
        SELECT
            season, week, team,
            report_primary_injury, report_secondary_injury, report_status,
            practice_primary_injury, practice_status,
            full_name, position, gsis_id
        FROM injuries, latest
        WHERE team = ? AND season = ? AND week = latest.w
        ORDER BY
            CASE report_status
                WHEN 'Out'           THEN 0
                WHEN 'Doubtful'      THEN 1
                WHEN 'Questionable'  THEN 2
                WHEN 'Probable'      THEN 3
                ELSE 4
            END,
            full_name
    """, params + [team, season])
    return rows
