"""Response schema for /team-analytics: per-team season metrics with ranks."""
from pydantic import BaseModel


class TeamAnalyticsRow(BaseModel):
    """One row per team. Rank columns are 1-based with 1 = best (for that team).

    Higher-is-better metrics use DESC ranks; lower-is-better metrics use ASC,
    so rank=1 always means "best in the league" regardless of metric direction.

    Most rate metrics can legitimately be NULL (e.g. PROE is NULL for seasons
    before nflfastR added pass_oe; rz_td_pct is NULL for teams that never
    reached the red zone), so all of them are required-but-nullable.
    """
    team: str
    games: int
    wins: int
    losses: int
    ties: int
    pf_total: int
    pa_total: int

    # Scoring
    ppg: float | None
    papg: float | None
    pt_diff_per_game: float | None
    pts_per_drive: float | None
    pts_per_drive_allowed: float | None

    # Drives / red zone / turnovers
    total_drives: int | None
    total_drives_allowed: int | None
    rz_td_pct: float | None
    rz_td_pct_allowed: float | None
    off_turnovers_total: int
    def_takeaways_total: int
    turnover_diff_per_game: float | None

    # Offense
    off_plays_count: int | None
    off_epa_play: float | None
    off_pass_epa: float | None
    off_rush_epa: float | None
    off_success_pct: float | None
    off_explosive_pct: float | None
    proe: float | None
    third_down_pct: float | None

    # Defense
    def_epa_play: float | None
    def_pass_epa: float | None
    def_rush_epa: float | None
    def_success_pct: float | None
    def_explosive_pct: float | None
    def_sack_pct: float | None
    third_down_stop_pct: float | None

    # Ranks — 1 = best for the team's direction
    ppg_rank: int | None
    pts_per_drive_rank: int | None
    off_epa_play_rank: int | None
    off_pass_epa_rank: int | None
    off_rush_epa_rank: int | None
    off_success_rank: int | None
    off_explosive_rank: int | None
    third_down_rank: int | None
    rz_td_rank: int | None
    proe_rank: int | None
    papg_rank: int | None
    pts_per_drive_allowed_rank: int | None
    def_epa_play_rank: int | None
    def_pass_epa_rank: int | None
    def_rush_epa_rank: int | None
    def_success_rank: int | None
    def_explosive_rank: int | None
    third_down_stop_rank: int | None
    rz_td_allowed_rank: int | None
    def_sack_rank: int | None
    pt_diff_rank: int | None
    to_diff_rank: int | None


class TeamAnalyticsResponse(BaseModel):
    """/team-analytics?season=… returns the season plus per-team rows."""
    season: int
    league: list[TeamAnalyticsRow]
