"""Team-level endpoints: profile, roster, and league-wide analytics."""
from fastapi import APIRouter, HTTPException, Query

import team_analytics_builder
from config import CURRENT_SEASON
from database import query_to_dict
from routers.schedule import attach_records
from schemas.analytics import TeamAnalyticsResponse
from schemas.teams import RosterPlayer, TeamProfile

router = APIRouter()


_LEADER_COLS = """
        COUNT(DISTINCT pgs.game_id)   AS games_played,
        SUM(pgs.attempts)             AS attempts,
        SUM(pgs.completions)          AS completions,
        SUM(pgs.pass_yards)           AS pass_yards,
        SUM(pgs.pass_tds)             AS pass_tds,
        SUM(pgs.interceptions_thrown) AS interceptions_thrown,
        SUM(pgs.sacks_taken)          AS sacks_taken,
        SUM(pgs.pass_epa)             AS pass_epa,
        SUM(pgs.carries)              AS carries,
        SUM(pgs.rush_yards)           AS rush_yards,
        SUM(pgs.rush_tds)             AS rush_tds,
        SUM(pgs.rush_epa)             AS rush_epa,
        SUM(pgs.targets)              AS targets,
        SUM(pgs.receptions)           AS receptions,
        SUM(pgs.rec_yards)            AS rec_yards,
        SUM(pgs.rec_tds)              AS rec_tds,
        SUM(pgs.air_yards)            AS air_yards,
        SUM(pgs.yac)                  AS yac,
        SUM(pgs.rec_epa)              AS rec_epa,
        SUM(pgs.solo_tackles)         AS solo_tackles,
        SUM(pgs.assist_tackles)       AS assist_tackles,
        SUM(pgs.sacks)                AS sacks,
        SUM(pgs.tackles_for_loss)     AS tackles_for_loss,
        SUM(pgs.qb_hits)              AS qb_hits,
        SUM(pgs.def_interceptions)    AS def_interceptions,
        SUM(pgs.pass_breakups)        AS pass_breakups,
        SUM(pgs.forced_fumbles)       AS forced_fumbles,
        SUM(pgs.fumble_recoveries)    AS fumble_recoveries
"""


@router.get("/teams/{team}", response_model=TeamProfile)
def get_team(team: str, season: int = Query(2025)):
    games = query_to_dict(
        """
        SELECT
            game_id, season, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            stadium, roof, surface, temp, wind
        FROM schedules
        WHERE season = ? AND (away_team = ? OR home_team = ?)
        ORDER BY week
        """,
        [season, team, team],
    )
    if not games:
        raise HTTPException(status_code=404, detail=f"No games found for {team} in {season}")

    attach_records(games)

    leaders = query_to_dict(
        f"""
        SELECT
            pgs.player_id,
            pgs.player_name,
            r.position,
            r.headshot_url,
            r.jersey_number,
            {_LEADER_COLS}
        FROM player_game_stats pgs
        LEFT JOIN rosters r ON pgs.player_id = r.player_id AND r.season = pgs.season
        JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type = 'REG'
        WHERE pgs.season = ? AND pgs.team = ?
        GROUP BY pgs.player_id, pgs.player_name, r.position, r.headshot_url, r.jersey_number
        """,
        [season, team],
    )

    playoff_leaders = query_to_dict(
        f"""
        SELECT
            pgs.player_id,
            pgs.player_name,
            r.position,
            r.headshot_url,
            r.jersey_number,
            {_LEADER_COLS}
        FROM player_game_stats pgs
        LEFT JOIN rosters r ON pgs.player_id = r.player_id AND r.season = pgs.season
        JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type != 'REG'
        WHERE pgs.season = ? AND pgs.team = ?
        GROUP BY pgs.player_id, pgs.player_name, r.position, r.headshot_url, r.jersey_number
        """,
        [season, team],
    )

    return {"team": team, "season": season, "games": games, "leaders": leaders, "playoff_leaders": playoff_leaders}


@router.get("/teams/{team}/roster", response_model=list[RosterPlayer])
def get_team_roster(team: str, season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON
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
    if not rows:
        raise HTTPException(status_code=404, detail=f"No roster found for {team} in {season}")
    return rows


@router.get("/team-analytics", response_model=TeamAnalyticsResponse)
def get_team_analytics(season: int = Query(default=None)):
    """Read precomputed team analytics from the materialized table.

    The heavy aggregation (150-line CTE over plays + schedules) used to run
    on every request. It now runs once during ingest and writes to the
    `team_season_analytics` table; this endpoint is a simple keyed SELECT.

    If the row is missing (fresh DB, never-ingested season), the builder
    lazily materializes on first hit so the system self-heals.
    """
    if season is None:
        season = CURRENT_SEASON
    league = team_analytics_builder.read_or_materialize(season)
    return {"season": season, "league": league}
