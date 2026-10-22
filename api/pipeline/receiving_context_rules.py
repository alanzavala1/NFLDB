"""Definitions and classifiers for contextual receiving previews, without I/O."""
import numpy as np
import pandas as pd

from pipeline.source_results import SourceError
from team_definitions import DIVISIONS, MODERN_TEAM_ALIASES, RELOCATIONS, TEAM_NAMES


DIVISION_ORDER = ("AFC East", "AFC North", "AFC South", "AFC West",
                  "NFC East", "NFC North", "NFC South", "NFC West")
# Preserve the legacy exact-grass definition, including its hybrid aliases.
# Unknown labels remain unknown rather than silently becoming artificial turf.
SURFACES = {"grass": "grass", **{name: "turf" for name in (
    "astroplay", "astroturf", "fieldturf", "sportturf", "dessograss",
    "a_turf", "matrixturf",
)}}
ROOFS = {"dome": "dome", "closed": "dome", "outdoors": "outdoors", "open": "outdoors"}
EXTRA_DIMENSIONS = {
    "game_state": ("competitive", "garbage"), "roof": ("dome", "outdoors"),
    "surface": ("grass", "turf"), "opponent": tuple(TEAM_NAMES), "opp_division": DIVISION_ORDER,
    "target_depth": ("short", "deep"), "target_direction": ("left", "middle", "right"),
    "pressure": ("clean", "pressured"), "play_action": ("play_action", "no_pa"),
    "blitz": ("standard_rush", "blitz"),
}
EXTRA_FIELDS = {"game_state": "wp", "roof": "roof", "surface": "surface", "opponent": "defteam",
                "opp_division": "defteam", "target_depth": "pass_length", "target_direction": "pass_location",
                "pressure": "qb_hit", "play_action": "is_play_action", "blitz": "n_pass_rushers"}
POLICIES = {
    "pressure": "Recorded QB hit versus no QB hit; not all pressure. Unavailable before 2006.",
    "opp_division": "Current franchise divisions, including pre-2002 seasons; not historical alignment.",
    "surface": "Legacy exact grass versus reviewed non-grass labels; includes hybrids in turf. Unknown aliases excluded.",
    "target_depth": "Original pass depth shared by all credited recipients; not a lateral recipient's route.",
    "target_direction": "Original pass direction shared by all credited recipients; not a lateral recipient's route.",
    "blitz": "FTN pass rushers 1-4 versus 5-11; not n_blitzers. Missing/out-of-range values excluded.",
    "play_action": "FTN recorded play action; false is distinct from uncharted. FTN starts in 2022.",
}


def extra_context_values(context: pd.DataFrame, dimension: str, season: int) -> pd.Series:
    field = EXTRA_FIELDS[dimension]
    def fail(reason):
        raise SourceError("nflfastR_receiving_splits", season, reason)
    if field not in context:
        fail(f"missing context {field}")
    values = context[field]
    result = pd.Series(pd.NA, index=context.index, dtype="string")
    if dimension in ("roof", "surface", "target_depth", "target_direction", "opponent", "opp_division"):
        values = values.astype("string")
        if dimension in ("roof", "surface"):
            return values.map(ROOFS if dimension == "roof" else SURFACES).astype("string")
        if dimension in ("target_depth", "target_direction"):
            invalid = values.notna() & values.ne("") & ~values.isin(EXTRA_DIMENSIONS[dimension])
            if invalid.any():
                fail(f"invalid context {field}")
            return values.where(values.isin(EXTRA_DIMENSIONS[dimension]))
        known = values.notna() & values.ne("")
        if not values[known].isin(TEAM_NAMES).all():
            fail("invalid context defteam")
        modern = values.replace(MODERN_TEAM_ALIASES)
        if dimension == "opp_division":
            return modern.map(DIVISIONS).astype("string")
        for current, era, last in RELOCATIONS:
            if season <= last:
                modern = modern.replace({current: era})
        return modern.where(known)
    try:
        values = pd.to_numeric(values, errors="raise")
        observed = values.dropna().to_numpy(dtype=float)
    except (TypeError, ValueError):
        fail(f"invalid context {field}")
    if not np.isfinite(observed).all():
        fail(f"invalid context {field}")
    if dimension in ("play_action", "blitz") and season < 2022:
        return result
    if dimension == "game_state":
        if (observed < 0).any() or (observed > 1).any():
            fail("invalid context wp")
        result.loc[values.notna()] = "garbage"
        result.loc[values.between(0.05, 0.95).fillna(False)] = "competitive"
    elif dimension == "blitz":
        if not (observed == np.trunc(observed)).all():
            fail("invalid context n_pass_rushers")
        result.loc[values.between(1, 4).fillna(False)] = "standard_rush"
        result.loc[values.between(5, 11).fillna(False)] = "blitz"
    else:
        if not values.dropna().isin([0, 1]).all():
            fail(f"invalid context {field}")
        if dimension == "pressure" and season < 2006:
            return result
        labels = {0: "clean", 1: "pressured"} if dimension == "pressure" else {1: "play_action", 0: "no_pa"}
        result = values.map(labels).astype("string")
    return result


def export_definitions(dimensions: dict) -> dict:
    """Catalog consumed by R; classifications are independently checked in Python."""
    return {"dimensions": {key: list(values) for key, values in dimensions.items()},
            "roofs": ROOFS, "surfaces": SURFACES, "divisions": DIVISIONS,
            "modern_aliases": MODERN_TEAM_ALIASES, "relocations": [list(row) for row in RELOCATIONS],
            "policies": POLICIES, "pressure_first_season": 2006, "ftn_first_season": 2022}
