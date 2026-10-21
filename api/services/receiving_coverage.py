"""Known receiving-source gaps used by serving masks and offline preparation.

2003–08 feeds lack complete target credits / incomplete-pass receiver identity.
Positive stored counts do not prove coverage. Fail closed for those seasons,
including postseason, rather than inventing zeroes or trusting legacy counts.
Outside this known gap this policy leaves the existing source values unchanged;
that is not a certification of every other season or of receiving EPA/ratings.
Raw stored data and independently usable catches/yards/TDs are never changed.
The YAC helper is currently used only by the isolated preview, not serving.
"""
from collections.abc import Iterable


UNAVAILABLE_TARGET_SEASONS = frozenset(range(2003, 2009))
FIRST_YAC_SEASON = 2006


def targets_unavailable(seasons: Iterable[int]) -> bool:
    return any(season in UNAVAILABLE_TARGET_SEASONS for season in seasons)


def yac_unavailable(seasons: Iterable[int]) -> bool:
    """Preview policy: pre-2006 YAC lacks supported source records.

    Separate from target coverage: 2006–08 has YAC despite missing targets.
    Later seasons still require reconciliation, not just this date check.
    This helper does not change the existing serving mask below.
    """
    return any(season < FIRST_YAC_SEASON for season in seasons)


def mask_target_fields(row: dict, season: int, *, split: bool = False) -> dict:
    """Return a serving copy; never mutate database/cached builder rows."""
    if not targets_unavailable([season]):
        return row
    fields = ("att", "epa", "success_pct") if split else (
        "targets", "rz_targets", "third_targets", "target_share", "air_yards_share",
    )
    return {key: None if key in fields else value for key, value in row.items()}
