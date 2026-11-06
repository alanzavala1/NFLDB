"""Supported preview partitions and the existing player_splits bucket labels."""
import numpy as np
import pandas as pd

from pipeline.source_results import SourceError
from pipeline.receiving_context_rules import EXTRA_DIMENSIONS, extra_context_values


DIMENSIONS = {"down": ("1", "2", "3", "4"), "quarter": ("1", "2", "3", "4", "OT"),
              "home_away": ("home", "away"), "shotgun": ("shotgun", "under_center"),
              "field_zone": ("own_territory", "opp_territory", "red_zone"),
              "game_script": ("leading", "tied", "trailing"),
              "no_huddle": ("huddle", "no_huddle"), **EXTRA_DIMENSIONS}


def context_split_values(context: pd.DataFrame, dimension: str, season: int) -> pd.Series:
    """Use play context, never player credit identity, to assign each bucket.

    All periods above four share OT, as in splits_core. Missing down does not
    discard an otherwise usable quarter play. Missing period remains unknown.
    """
    if dimension not in DIMENSIONS:
        raise SourceError("nflfastR_receiving_splits", season, "unsupported split dimension")
    if dimension in EXTRA_DIMENSIONS:
        return extra_context_values(context, dimension, season)
    field = {"down": "down", "quarter": "qtr", "home_away": "posteam_type",
             "shotgun": "shotgun", "field_zone": "yardline_100",
             "game_script": "score_differential", "no_huddle": "no_huddle"}[dimension]
    if field not in context:
        raise SourceError("nflfastR_receiving_splits", season, f"missing context {field}")
    if dimension == "home_away":
        # Designated game side, not stadium geography or a season's latest team.
        # Unknown values must never silently fall through to the away bucket.
        values = context[field].astype("string")
        if not values.dropna().isin(DIMENSIONS[dimension]).all():
            raise SourceError("nflfastR_receiving_splits", season, f"invalid context {field}")
        return values
    try:
        values = pd.to_numeric(context[field], errors="raise")
        observed = values.dropna().to_numpy(dtype=float)
    except (TypeError, ValueError) as error:
        raise SourceError("nflfastR_receiving_splits", season, f"invalid context {field}") from error
    if dimension == "game_script":
        limits = np.iinfo(np.int32)
        if (not np.isfinite(observed).all() or not (observed == np.trunc(observed)).all()
                or (observed < limits.min).any() or (observed > limits.max).any()):
            raise SourceError("nflfastR_receiving_splits", season, "invalid context score_differential")
        # Offense's score minus defense's score before the play, including the
        # original score state when a completion/lateral changes the lead.
        result = pd.Series(pd.NA, index=values.index, dtype="string")
        for condition, label in ((values.gt(0), "leading"), (values.eq(0), "tied"),
                                 (values.lt(0), "trailing")):
            result.loc[condition.fillna(False)] = label
        return result
    if dimension == "field_zone":
        if not np.isfinite(observed).all() or (observed < 0).any() or (observed > 100).any():
            raise SourceError("nflfastR_receiving_splits", season, "invalid context yardline_100")
        # Distance to the opponent's goal line, using the pre-play ball spot.
        result = pd.Series(pd.NA, index=values.index, dtype="string")
        result.loc[values.notna()] = "own_territory"
        result.loc[values.le(50).fillna(False)] = "opp_territory"
        result.loc[values.le(20).fillna(False)] = "red_zone"
        return result
    if dimension in ("shotgun", "no_huddle"):
        if not values.dropna().isin([0, 1]).all():
            raise SourceError("nflfastR_receiving_splits", season, f"invalid context {field}")
        labels = {1: "shotgun", 0: "under_center"} if dimension == "shotgun" else {0: "huddle", 1: "no_huddle"}
        return values.map(labels).astype("string")
    if (not np.isfinite(observed).all() or not (observed == np.trunc(observed)).all()
            or (observed < 1).any() or (observed > np.iinfo(np.int32).max).any()
            or (dimension == "down" and (observed > 4).any())):
        raise SourceError("nflfastR_receiving_splits", season, f"invalid context {field}")
    result = values.astype("Int64").astype("string")
    if dimension == "quarter":
        result = result.mask(values.gt(4).fillna(False), "OT")
    return result
