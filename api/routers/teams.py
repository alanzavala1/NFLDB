"""Team-level endpoints: profile, roster, and league-wide analytics."""
from fastapi import APIRouter, HTTPException, Query

import team_analytics_builder
import team_splits_builder
from config import CURRENT_SEASON
from schemas.analytics import TeamAnalyticsResponse, TeamSplit
from schemas.supplemental import DepthChartEntry, InjuryStatus
from schemas.teams import RosterPlayer, TeamProfile
from services.team_depth_chart import get_team_depth_chart as query_team_depth_chart
from services.team_injuries import get_team_injuries as query_team_injuries
from services.team_profile import get_team_profile as query_team_profile
from services.team_roster import get_team_roster as query_team_roster

router = APIRouter()


@router.get("/teams/{team}", response_model=TeamProfile)
def get_team(team: str, season: int = Query(default=CURRENT_SEASON)):
    profile = query_team_profile(team, season)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"No games found for {team} in {season}")
    return profile


@router.get("/teams/{team}/roster", response_model=list[RosterPlayer])
def get_team_roster(team: str, season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON
    rows = query_team_roster(team, season)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No roster found for {team} in {season}")
    return rows


@router.get("/teams/{team}/depth-chart", response_model=list[DepthChartEntry])
def get_team_depth_chart(team: str, season: int = Query(default=None), week: int | None = Query(default=None)):
    """The team's current depth chart. The vendor feed is a daily snapshot
    with no per-week history (see DEPTH_CHART_SEL), so `week` is accepted
    for API compatibility but ignored, and a request for a season other
    than the snapshot's returns [] rather than passing off today's chart
    as historical."""
    return query_team_depth_chart(team, season, week)


@router.get("/teams/{team}/splits", response_model=list[TeamSplit])
def get_team_splits(team: str, season: int = Query(default=None)):
    """Team offense/defense rate profile conditioned on each situational
    dimension. Reads the offline-prepared table without rebuilding."""
    if season is None:
        season = CURRENT_SEASON
    return team_splits_builder.read(team, season)


@router.get("/teams/{team}/injuries", response_model=list[InjuryStatus])
def get_team_injuries(team: str, season: int = Query(default=None), week: int | None = Query(default=None)):
    """Most recent injury report for the team. If `week` is omitted, returns
    the latest week we have data for in the given season."""
    return query_team_injuries(team, season, week)


@router.get("/team-analytics", response_model=TeamAnalyticsResponse)
def get_team_analytics(season: int = Query(default=None)):
    """Read precomputed team analytics from the materialized table.

    The heavy aggregation (150-line CTE over plays + schedules) used to run
    on every request. It now runs once during ingest and writes to the
    `team_season_analytics` table; this endpoint is a simple keyed SELECT.

    Missing rows stay unavailable until the next offline preparation.
    """
    if season is None:
        season = CURRENT_SEASON
    league = team_analytics_builder.read(season)
    return {"season": season, "league": league}
