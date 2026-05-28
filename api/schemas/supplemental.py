"""Response schemas for the supplemental vendor data layered onto
player and team views: injuries, depth charts, draft, combine."""
from pydantic import BaseModel


class DraftInfo(BaseModel):
    """One row per drafted player from `draft_picks`. Career achievement
    fields (`probowls`, `allpro`, `car_av`) come pre-aggregated from PFR."""
    season: int
    round: int
    pick: int
    team: str
    college: str | None
    age: int | None
    probowls: int | None
    allpro: int | None
    car_av: float | None    # career approximate value (PFR)
    games: int | None


class CombineData(BaseModel):
    """One row per combine participant. Heights are recorded as '6-2' strings
    by the source; we leave them as strings for display rather than coercing."""
    draft_year: int | None
    draft_round: int | None
    draft_ovr: int | None
    school: str | None
    pos: str | None
    ht: str | None       # e.g. "6-2"
    wt: float | None
    forty: float | None
    bench: float | None
    vertical: float | None
    broad_jump: float | None
    cone: float | None
    shuttle: float | None


class InjuryStatus(BaseModel):
    """A weekly injury report entry. We surface the most recent one for a
    player on the player view; a list for team/game views."""
    season: int
    week: int
    team: str
    report_primary_injury: str | None
    report_secondary_injury: str | None
    report_status: str | None       # "Out", "Questionable", "Probable", etc.
    practice_primary_injury: str | None
    practice_status: str | None     # "Did Not Participate", "Limited", "Full", etc.
    full_name: str | None
    position: str | None
    gsis_id: str | None             # exposed for team-wide views


class DepthChartEntry(BaseModel):
    """A weekly depth-chart slot. depth_team is "1"/"2"/"3", where "1" is
    the starter at that depth_position."""
    season: int
    week: int
    team: str
    formation: str | None           # "Offense" / "Defense" / "Special Teams"
    depth_position: str | None      # e.g. "QB", "RB1", "LT", "WR2", "LB1"
    depth_team: str | None          # "1" = starter, "2" = backup, ...
    gsis_id: str | None
    full_name: str | None
    position: str | None            # roster position (QB, WR, etc.)
    jersey_number: str | None
