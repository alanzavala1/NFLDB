"""Shared player/team matching for HTTP search and assistant entity lookup."""
import re

from config import TEAM_NAMES
from sql_helpers import safe_query

# Keep aliases few and unambiguous: a wrong entity is worse than no result.
_SEARCH_ALIASES = {
    "cmc": "christian mccaffrey",
    "niner": "san francisco 49ers",
    "niners": "san francisco 49ers",
    "jags": "jacksonville jaguars",
    "bucs": "tampa bay buccaneers",
    "pats": "new england patriots",
    "fins": "miami dolphins",
    "vikes": "minnesota vikings",
    "bolts": "los angeles chargers",
}


def _normalize_search(value: str) -> str:
    """Case/punctuation-insensitive form used by both aliases and DB matching."""
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def search(q: str) -> list[dict]:
    q = q.strip()
    if not q:
        return []

    ql = _normalize_search(q)
    if not ql:
        return []
    ql = _SEARCH_ALIASES.get(ql, ql)

    # Normalized substring matching handles punctuation and spacing.
    teams = []
    seen_team_names = set()
    for abbrev, name in TEAM_NAMES.items():
        if ql not in _normalize_search(abbrev) and ql not in _normalize_search(name):
            continue
        if name in seen_team_names:
            continue
        seen_team_names.add(name)
        teams.append(
            {"type": "team", "id": abbrev, "name": name, "position": None,
             "team": abbrev, "headshot_url": None}
        )
        if len(teams) == 3:
            break

    parts = ql.split()
    compact = ql.replace(" ", "")
    initial_last = len(parts) == 2 and len(parts[0]) == 1
    initial = parts[0] if initial_last else ""
    last = parts[1] if initial_last else ""

    # Initials and punctuation-free spellings supplement normalized name search.
    players = safe_query(
        """
        WITH normalized AS (
            SELECT
                player_id,
                player_name,
                position,
                team,
                headshot_url,
                season,
                TRIM(REGEXP_REPLACE(LOWER(player_name), '[^a-z0-9]+', ' ', 'g')) AS normalized_name,
                REGEXP_REPLACE(LOWER(player_name), '[^a-z0-9]+', '', 'g') AS compact_name
            FROM rosters
            QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY season DESC) = 1
        )
        SELECT
            player_id AS id,
            player_name AS name,
            position,
            team,
            headshot_url,
            CASE
                WHEN normalized_name = ? THEN 0
                WHEN normalized_name LIKE ? || '%' THEN 1
                WHEN ? AND LEFT(normalized_name, 1) = ?
                         AND REGEXP_EXTRACT(normalized_name, '([a-z0-9]+)$', 1) = ? THEN 2
                WHEN normalized_name LIKE '%' || ? || '%' THEN 3
                ELSE 4
            END AS rank
        FROM normalized
        WHERE normalized_name LIKE '%' || ? || '%'
           OR compact_name LIKE '%' || ? || '%'
           OR (? AND LEFT(normalized_name, 1) = ?
                    AND REGEXP_EXTRACT(normalized_name, '([a-z0-9]+)$', 1) = ?)
        ORDER BY rank, season DESC, player_name
        LIMIT 8
        """,
        [ql, ql, initial_last, initial, last,
         ql, ql, compact, initial_last, initial, last],
    )

    player_results = [
        {"type": "player", "id": p["id"], "name": p["name"],
         "position": p["position"], "team": p["team"], "headshot_url": p["headshot_url"]}
        for p in players
    ]

    return (teams + player_results)[:10]
