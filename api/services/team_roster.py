"""Season roster selection for team views."""
from database import query_to_dict


def get_team_roster(team: str, season: int) -> list[dict]:
    rows = query_to_dict(
        """
        SELECT
            player_id,
            player_name,
            position,
            jersey_number,
            headshot_url
        FROM rosters
        WHERE team = ? AND season = ?
        QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY season DESC) = 1
        ORDER BY position, player_name
        """,
        [team, season],
    )
    return rows
