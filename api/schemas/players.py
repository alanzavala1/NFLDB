"""Response schema for /players/{id}: the deeply nested player profile.

Convention: every field is required-but-possibly-null. The SQL helpers
always SELECT every column; values are simply NULL for stats that don't
apply (a passer has no receiving NGS, an offensive player has no
defensive snaps). This keeps the generated TypeScript to `T | null`
instead of `T | null | undefined`, which is much cleaner to consume.
"""
from typing import Literal

from pydantic import BaseModel

from schemas.supplemental import CombineData, DepthChartEntry, DraftInfo, InjuryStatus


class PlayerGame(BaseModel):
    """One row in the player's game log."""
    game_id: str
    season: int
    week: int
    team: str
    opponent: str
    location: Literal["home", "away"]
    gameday: str | None
    away_score: int | None
    home_score: int | None
    result: Literal["W", "L", "T"] | None
    game_type: str

    position: str | None
    jersey_number: int | None
    headshot_url: str | None

    # STAT_COLS — always populated (snap-first helper uses COALESCE(..., 0))
    attempts: float
    completions: float
    pass_yards: float
    pass_tds: float
    interceptions_thrown: float
    sacks_taken: float
    pass_epa: float

    targets: float
    receptions: float
    rec_yards: float
    rec_tds: float
    air_yards: float
    yac: float
    rec_epa: float

    carries: float
    rush_yards: float
    rush_tds: float
    rush_epa: float

    solo_tackles: float
    assist_tackles: float
    tackles_for_loss: float
    sacks: float
    qb_hits: float
    def_interceptions: float
    pass_breakups: float
    forced_fumbles: float
    fumble_recoveries: float

    fg_att: float
    fg_made: float
    xp_att: float
    xp_made: float
    punts: float
    punt_yards: float

    punt_returns: float
    punt_return_yards: float
    punt_return_tds: float


class NgsStats(BaseModel):
    """Next Gen Stats per season. Fields populated depend on role.

    NOTE: unlike most of our models, these sub-views are genuinely sparse —
    a QB row only has passing fields, a WR row only has receiving fields.
    The helper builds the dict from non-null SELECT results, so absent
    fields mean "doesn't apply." Defaults are kept so each instance can
    carry any subset.
    """
    # Passing
    avg_time_to_throw: float | None = None
    adot: float | None = None
    avg_completed_air_yards: float | None = None
    cpoe: float | None = None
    aggressiveness: float | None = None
    expected_cmp_pct: float | None = None
    ngs_passer_rating: float | None = None
    # Rushing
    rush_yoe: float | None = None
    rush_yoe_per_att: float | None = None
    rush_efficiency: float | None = None
    avg_time_to_los: float | None = None
    pct_vs_8_defenders: float | None = None
    # Receiving
    avg_separation: float | None = None
    avg_cushion: float | None = None
    avg_target_depth: float | None = None
    avg_yac: float | None = None
    avg_yac_above_exp: float | None = None
    catch_pct: float | None = None
    air_yards_share: float | None = None


class SnapTotals(BaseModel):
    """Per-season snap counts. snap_counts SQL always returns every column,
    just NULL where the player has no snaps of that type."""
    season: int
    offense_snaps: int | None
    defense_snaps: int | None
    st_snaps: int | None
    avg_offense_pct: float | None
    avg_defense_pct: float | None
    avg_st_pct: float | None


class SituationalStats(BaseModel):
    """Per-season situational splits — sparse by design. See NgsStats note."""
    # Longest plays
    lng_pass: int | None = None
    lng_rush: int | None = None
    lng_rec:  int | None = None
    # Red zone
    rz_pass_att: int | None = None
    rz_cmp:      int | None = None
    rz_pass_tds: int | None = None
    rz_targets:  int | None = None
    rz_rec_tds:  int | None = None
    rz_carries:  int | None = None
    rz_rush_tds: int | None = None
    # Third down
    third_pass_att: int | None = None
    third_pass_fd:  int | None = None
    third_targets:  int | None = None
    third_rec_fd:   int | None = None
    third_carries:  int | None = None
    third_rush_fd:  int | None = None
    # First downs generated
    fd_pass: int | None = None
    fd_rec:  int | None = None
    fd_rush: int | None = None


class PlayerWpa(BaseModel):
    """Per-season WPA attribution. Sparse by role (passer/rusher/receiver)."""
    pass_wpa: float | None = None
    rec_wpa:  float | None = None
    rush_wpa: float | None = None


class PlayerAdvStats(BaseModel):
    """Per-season advanced stats — sparse by player role."""
    fumbles_lost:    int | None = None
    target_share:    float | None = None
    air_yards_share: float | None = None
    stuff_rate:      float | None = None
    stuffed:         int | None = None
    carries_total:   int | None = None


class PlayerProfile(BaseModel):
    """Full /players/{id} payload."""
    player_id: str
    player_name: str
    position: str | None
    team: str | None
    jersey_number: int | None
    headshot_url: str | None
    height: int | None
    weight: int | None
    age: int | None
    college: str | None
    years_exp: int | None
    entry_year: int | None
    rookie_year: int | None
    draft_club: str | None
    draft_number: int | None

    games_played: int
    season_totals: dict[str, float]
    games: list[PlayerGame]

    ngs:         dict[int, NgsStats]
    snap_totals: dict[int, SnapTotals]
    situational: dict[int, SituationalStats]
    wpa:         dict[int, PlayerWpa]
    adv_stats:   dict[int, PlayerAdvStats]

    # Supplemental vendor data — all null if not yet ingested or not applicable
    draft:          DraftInfo        | None
    combine:        CombineData      | None
    current_injury: InjuryStatus     | None  # most-recent-week injury, if from the same season as their last game
    depth:          DepthChartEntry  | None  # most-recent-week depth chart slot, ditto
