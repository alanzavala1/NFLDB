"""Season schedule listing and week grouping for HTTP and assistant consumers."""
from database import query_to_dict
from services.schedule_records import attach_records


def get_schedule(season: int) -> list[dict]:
    rows = query_to_dict(
        """
        SELECT
            game_id, season, game_type, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            away_qb_name, home_qb_name, spread_line, total_line,
            roof, surface, temp, wind, stadium, overtime, div_game,
            away_coach, home_coach
        FROM schedules
        WHERE season = ?
        ORDER BY week, gametime
        """,
        [season],
    )
    attach_records(rows)
    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row["week"], []).append(row)
    return [{"week": w, "games": games} for w, games in sorted(grouped.items())]
