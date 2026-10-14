"""Current team depth-chart snapshots for HTTP and assistant consumers."""
from sql_helpers import DEPTH_CHART_SEL, safe_query


def get_team_depth_chart(team: str, season: int | None = None, week: int | None = None) -> list[dict]:
    """The team's current depth chart. The vendor feed is a daily snapshot
    with no per-week history (see DEPTH_CHART_SEL), so `week` is accepted
    for API compatibility but ignored, and a request for a season other
    than the snapshot's returns [] rather than passing off today's chart
    as historical."""
    rows = safe_query(f"""
        SELECT {DEPTH_CHART_SEL}
        FROM depth_charts
        WHERE team = ? AND dt = (SELECT MAX(dt) FROM depth_charts)
        ORDER BY
            CASE WHEN pos_grp = 'Special Teams' THEN 2
                 WHEN pos_grp LIKE 'Base%'      THEN 1
                 ELSE 0 END,
            pos_slot, pos_rank
    """, [team])
    if rows and season is not None and rows[0]["season"] != season:
        return []
    return rows
