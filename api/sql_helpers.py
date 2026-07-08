"""Shared SQL fragments and query helpers."""
import logging

from database import query_to_dict

logger = logging.getLogger(__name__)

# All numeric stat columns on player_game_stats (excluding identity/team fields).
# Single source of truth used in SQL selects and Python aggregations.
STAT_COLS = (
    "attempts", "completions", "pass_yards", "pass_tds",
    "interceptions_thrown", "sacks_taken", "pass_epa",
    "targets", "receptions", "rec_yards", "rec_tds",
    "air_yards", "yac", "rec_epa",
    "carries", "rush_yards", "rush_tds", "rush_epa",
    "solo_tackles", "assist_tackles", "tackles_for_loss",
    "sacks", "qb_hits", "def_interceptions",
    "pass_breakups", "forced_fumbles", "fumble_recoveries",
    "fg_att", "fg_made", "xp_att", "xp_made",
    "punts", "punt_yards",
    "punt_returns", "punt_return_yards", "punt_return_tds",
)

# Prefixed for use inside CTEs where pgs alias is in scope.
PGS_STAT_SEL = ", ".join(f"pgs.{c}" for c in STAT_COLS)

# De-duped roster: one row per player+season. For players who changed teams
# mid-season (weekly roster snapshots), pick the latest week's row — i.e. the
# team they finished the season on — with `team` as a final tiebreak so the
# winner is deterministic (the old `ORDER BY season DESC` was a no-op: season
# is a partition key, so the row was arbitrary).
ROSTER_CTE = """\
    roster AS (
        SELECT player_id, season, team, position, jersey_number, headshot_url
        FROM rosters
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY player_id, season
            ORDER BY week DESC NULLS LAST, team
        ) = 1
    )"""


# depth_charts is the new nflverse feed (ESPN-sourced): dt-stamped daily
# snapshots with pos_grp/pos_abb/pos_rank — no season/week/formation columns.
# This projection adapts it to the DepthChartEntry response shape the frontend
# already consumes: season derived from the snapshot date (NFL-season rule),
# pos_grp variants ('3WR 1TE', 'Base 4-3 D', ...) folded into the
# Offense/Defense/Special Teams labels the UI groups by, pos_rank as the
# "1" = starter string. The feed has no week or jersey number.
DEPTH_CHART_SEL = """
        CASE WHEN month(CAST(dt AS TIMESTAMP)) >= 9
             THEN year(CAST(dt AS TIMESTAMP))
             ELSE year(CAST(dt AS TIMESTAMP)) - 1 END AS season,
        CAST(NULL AS INTEGER)     AS week,
        team,
        CASE WHEN pos_grp = 'Special Teams' THEN 'Special Teams'
             WHEN pos_grp LIKE 'Base%'      THEN 'Defense'
             ELSE 'Offense' END   AS formation,
        pos_abb                   AS depth_position,
        CAST(pos_rank AS VARCHAR) AS depth_team,
        gsis_id,
        player_name               AS full_name,
        pos_abb                   AS position,
        CAST(NULL AS VARCHAR)     AS jersey_number"""


def team_sql(away: str, home: str) -> tuple[str, str]:
    """Team-correction CASE and ROW_NUMBER rank for a known game.

    Roster team is authoritative; pgs.team is only used if roster doesn't match the game.
    `away` and `home` are SQL expressions (e.g. literal "?" placeholders or column refs).
    """
    correction = f"""\
CASE
                    WHEN r.team IN ({away}, {home})                             THEN r.team
                    WHEN pgs.team IN ({away}, {home})                           THEN pgs.team
                    ELSE COALESCE(r.team, pgs.team)
                END"""
    rank = f"""\
CASE
                        WHEN r.team = pgs.team AND pgs.team IN ({away}, {home}) THEN 0
                        WHEN r.team IN ({away}, {home})                         THEN 1
                        WHEN pgs.team IN ({away}, {home})                       THEN 2
                        ELSE 3
                    END"""
    return correction, rank


def safe_query(sql: str, params: list = None) -> list[dict]:
    """Wrapper around query_to_dict that returns [] on any failure (missing table, etc)."""
    try:
        return query_to_dict(sql, params or [])
    except Exception:
        logger.warning("safe_query failed, returning []", exc_info=True)
        return []
