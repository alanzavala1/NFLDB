"""Supported preview partitions and the existing player_splits bucket labels."""
import numpy as np
import pandas as pd

from pipeline.source_results import SourceError


DIMENSIONS = {"down": ("1", "2", "3", "4"), "quarter": ("1", "2", "3", "4", "OT")}


def context_split_values(context: pd.DataFrame, dimension: str, season: int) -> pd.Series:
    """Use play context, never player credit identity, to assign each bucket.

    All periods above four share OT, as in splits_core. Missing down does not
    discard an otherwise usable quarter play. Missing period remains unknown.
    """
    if dimension not in DIMENSIONS:
        raise SourceError("nflfastR_receiving_splits", season, "unsupported split dimension")
    field = "down" if dimension == "down" else "qtr"
    if field not in context:
        raise SourceError("nflfastR_receiving_splits", season, f"missing context {field}")
    try:
        values = pd.to_numeric(context[field], errors="raise")
        observed = values.dropna().to_numpy(dtype=float)
    except (TypeError, ValueError) as error:
        raise SourceError("nflfastR_receiving_splits", season, f"invalid context {field}") from error
    if (not np.isfinite(observed).all() or not (observed == np.trunc(observed)).all()
            or (observed < 1).any() or (observed > np.iinfo(np.int32).max).any()
            or (dimension == "down" and (observed > 4).any())):
        raise SourceError("nflfastR_receiving_splits", season, f"invalid context {field}")
    result = values.astype("Int64").astype("string")
    if dimension == "quarter":
        result = result.mask(values.gt(4).fillna(False), "OT")
    return result
