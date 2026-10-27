"""Known receiving-source gaps used by serving masks and offline preparation.

2003–08 feeds lack complete target credits / incomplete-pass receiver identity.
Positive stored counts do not prove coverage. Fail closed for those seasons,
including postseason, rather than inventing zeroes or trusting legacy counts.
Outside the historical boundaries below, existing source values are unchanged;
that is not a certification of every other season or of receiving EPA/ratings.
Raw stored data and independently usable catches/yards/TDs are never changed.
The same historical boundaries govern prepared splits and legacy summaries.
On player_game_stats, air_yards and yac are receiving fields, even for a QB.
"""
from collections.abc import Iterable


UNAVAILABLE_TARGET_SEASONS = frozenset(range(2003, 2009))
FIRST_YAC_SEASON = 2006
FIRST_AIR_YARDS_SEASON = 2006


def targets_unavailable(seasons: Iterable[int]) -> bool:
    return any(season in UNAVAILABLE_TARGET_SEASONS for season in seasons)


def yac_unavailable(seasons: Iterable[int]) -> bool:
    """Prepared receiving policy: pre-2006 YAC lacks supported source records.

    Separate from target coverage: 2006–08 has YAC despite missing targets.
    Later seasons still require reconciliation, not just this date check.
    """
    return any(season < FIRST_YAC_SEASON for season in seasons)


def air_yards_unavailable(seasons: Iterable[int]) -> bool:
    """Prepared receiving requires air records and complete target attribution.

    Pre-2006 air records are unsupported; 2003–08 targets are incomplete.
    Later seasons still require per-bucket coverage and reconciliation.
    """
    return any(season < FIRST_AIR_YARDS_SEASON or season in UNAVAILABLE_TARGET_SEASONS
               for season in seasons)


def mask_receiving_fields(row: dict, season: int, *, split: bool = False) -> dict:
    """Return a serving copy; never mutate database/cached builder rows."""
    fields = set()
    if targets_unavailable([season]):
        fields.update(("att", "epa", "success_pct") if split else (
            "targets", "rz_targets", "third_targets", "target_share",
        ))
    if yac_unavailable([season]):
        fields.add("yac")
    if air_yards_unavailable([season]):
        fields.update(("air_yards", "air_yards_share"))
    return {key: None if key in fields else value for key, value in row.items()}
