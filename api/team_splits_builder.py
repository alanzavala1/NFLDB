"""Materialized team splits: a team's offense (and defense) rate profile,
conditioned on one situational dimension.

Same long-format / materialize / self-heal pattern as player splits, built on
the shared splits_core scaffolding. `side` ('offense' | 'defense') replaces the
player table's `category`; metrics are team rate stats (EPA/play, success%,
pass rate, yards/play, explosive%) over scrimmage plays.
"""
import duckdb

import splits_core as core
from database import get_connection, query_to_dict


_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS team_splits (
    team        VARCHAR NOT NULL,
    season      INTEGER NOT NULL,
    side        VARCHAR NOT NULL,   -- 'offense' | 'defense'
    split_dim   VARCHAR NOT NULL,
    split_value VARCHAR NOT NULL,
    sort_order  INTEGER,
    plays         INTEGER,
    epa_play      DOUBLE,
    success_pct   DOUBLE,
    pass_rate     DOUBLE,
    yards_play    DOUBLE,
    explosive_pct DOUBLE,
    pass_epa      DOUBLE,
    rush_epa      DOUBLE,
    PRIMARY KEY (team, season, side, split_dim, split_value)
)
"""

_COLUMNS = ("team", "season", "side", "split_dim", "split_value", "sort_order",
            "plays", "epa_play", "success_pct", "pass_rate", "yards_play",
            "explosive_pct", "pass_epa", "rush_epa")

# Field position from the offense's yardline_100 (distance to opponent goal).
# Ordered own → opp → red zone so the table reads as a drive progressing.
_FIELD_ZONE_DIM = (
    "field_zone",
    "CASE WHEN yardline_100 <= 20 THEN 'red_zone' WHEN yardline_100 <= 50 THEN 'opp_territory' ELSE 'own_territory' END",
    "CASE WHEN yardline_100 <= 20 THEN 3 WHEN yardline_100 <= 50 THEN 2 ELSE 1 END",
    "yardline_100 IS NOT NULL",
)

_METRICS = """
    COUNT(*)                                                              AS plays,
    ROUND(AVG(epa), 4)                                                    AS epa_play,
    ROUND(100.0 * AVG(success), 1)                                        AS success_pct,
    ROUND(100.0 * AVG(CASE WHEN pass_attempt = 1 OR sack = 1 THEN 1 ELSE 0 END), 1) AS pass_rate,
    ROUND(AVG(yards_gained), 2)                                           AS yards_play,
    ROUND(100.0 * AVG(CASE WHEN (pass_attempt = 1 AND yards_gained >= 20)
                             OR (rush_attempt = 1 AND yards_gained >= 10) THEN 1 ELSE 0 END), 1) AS explosive_pct,
    ROUND(AVG(epa) FILTER (WHERE pass_attempt = 1 OR sack = 1), 4)        AS pass_epa,
    ROUND(AVG(epa) FILTER (WHERE rush_attempt = 1), 4)                    AS rush_epa"""


def ensure_table(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_TABLE_DDL)


def _side_dims(side: str) -> list[tuple[str, str, str, str]]:
    # Defense flips game script: when posteam (the opposing offense) leads,
    # this team's defense is trailing.
    sign = 1 if side == "offense" else -1
    return [core.DOWN_DIM, core.QUARTER_DIM, core.game_script_dim(sign), _FIELD_ZONE_DIM]


def _side_sql(side: str, season: int, available: set[str]) -> str:
    s = int(season)
    team_col = "posteam" if side == "offense" else "defteam"
    kneel = "AND COALESCE(qb_kneel, 0) = 0" if "qb_kneel" in available else ""
    spike = "AND COALESCE(qb_spike, 0) = 0" if "qb_spike" in available else ""

    base = f"""
        {team_col} AS team,
        down, qtr, score_differential, yardline_100,
        epa, pass_attempt, rush_attempt, sack, yards_gained, {core.success_col(available)}
        FROM plays
        WHERE {team_col} IS NOT NULL
          AND season = {s} AND season_type = 'REG'
          AND play_type IN ('pass', 'run')
          {core.two_pt_filter(available)} {kneel} {spike}"""

    union = core.union_blocks(_side_dims(side), _METRICS, "team")
    return f"""
    WITH b AS (SELECT {base})
    {union}
    """


def materialize(season: int) -> int:
    """Compute offense + defense splits for every team in one season."""
    conn = get_connection()
    ensure_table(conn)
    s = int(season)
    available = core.plays_columns(conn)

    conn.execute("DELETE FROM team_splits WHERE season = ?", [s])
    cols = ", ".join(_COLUMNS)
    for side in ("offense", "defense"):
        sql = _side_sql(side, s, available)
        try:
            conn.execute(f"""
                INSERT INTO team_splits ({cols})
                SELECT team, {s} AS season, '{side}' AS side,
                       split_dim, split_value, sort_order,
                       plays, epa_play, success_pct, pass_rate, yards_play,
                       explosive_pct, pass_epa, rush_epa
                FROM ({sql})
            """)
        except Exception as e:
            print(f"team_splits[{side}] materialize failed for season {s}: {e}")

    return conn.execute(
        "SELECT COUNT(*) FROM team_splits WHERE season = ?", [s]
    ).fetchone()[0]


def read(team: str, season: int) -> list[dict]:
    try:
        return query_to_dict("""
            SELECT side, split_dim, split_value, sort_order,
                   plays, epa_play, success_pct, pass_rate, yards_play,
                   explosive_pct, pass_epa, rush_epa
            FROM team_splits
            WHERE team = ? AND season = ?
            ORDER BY side, split_dim, sort_order
        """, [team, int(season)])
    except Exception:
        return []


def read_or_materialize(team: str, season: int) -> list[dict]:
    rows = read(team, season)
    if rows:
        return rows
    if materialize(season) > 0:
        return read(team, season)
    return []
