"""Read-time policy for known gaps in the current nflverse target source.

2003–08 feeds lack complete target credits / incomplete-pass receiver identity.
Positive stored counts do not prove coverage. Fail closed for those seasons,
including postseason, rather than inventing zeroes or trusting legacy counts.
Outside this known gap this policy leaves the existing source values unchanged;
that is not a certification of every other season or of receiving EPA/ratings.
Raw stored data and independently usable catches/yards/TDs are never changed.
"""
from collections.abc import Iterable


UNAVAILABLE_TARGET_SEASONS = frozenset(range(2003, 2009))


def targets_unavailable(seasons: Iterable[int]) -> bool:
    return any(season in UNAVAILABLE_TARGET_SEASONS for season in seasons)


def mask_target_fields(row: dict, season: int, *, split: bool = False) -> dict:
    """Return a serving copy; never mutate database/cached builder rows."""
    if not targets_unavailable([season]):
        return row
    fields = ("att", "epa", "success_pct") if split else (
        "targets", "rz_targets", "third_targets", "target_share", "air_yards_share",
    )
    return {key: None if key in fields else value for key, value in row.items()}
