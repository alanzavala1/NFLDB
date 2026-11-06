"""Target-role air yards and rates for the isolated receiving preview."""
import numpy as np
import pandas as pd

from pipeline.source_results import SourceError
from pipeline.receiving_dimensions import context_split_values
from services.receiving_coverage import air_yards_unavailable, targets_unavailable


def receiving_target_metrics(source: pd.DataFrame, context: pd.DataFrame, season: int,
                             *, dimension: str | None = "down") -> pd.DataFrame:
    """Require complete matching target populations before exposing each field.

    Success is EPA > 0, calculated here because calculate_stats has no success
    output. Missing EPA is not a failed play. Official receiving EPA must also
    match the target-play numerator before it can be divided by target credits.
    Air yards has independent completeness checks, without requiring EPA.
    """
    def fail(reason):
        raise SourceError("nflfastR_receiving_target_metrics", season, reason)

    flags = ["complete_pass", "incomplete_pass", "interception"]
    required = {"game_id", "play_id", "season", "season_type", "two_point_attempt",
                "receiver_player_id", "epa", "air_yards", *flags}
    if required - set(context.columns):
        fail("missing target context columns")
    plays = context.copy()
    if (plays[["season", "season_type"]].isna().any().any()
            or not plays.season.eq(season).all() or not plays.season_type.eq("REG").all()
            or plays.two_point_attempt.eq(1).any()):
        fail("unexpected target context scope")
    if plays[["game_id", "play_id"]].isna().any().any() or plays.duplicated(["game_id", "play_id"]).any():
        fail("missing or duplicate play identity")
    # None is the internal whole-population calculation, independent of every
    # situational classifier. It is not an additional public export dimension.
    plays["split_value"] = "all" if dimension is None else context_split_values(plays, dimension, season)
    for flag in [*flags, "two_point_attempt"]:
        if not plays[flag].dropna().isin([0, 1]).all():
            fail("invalid context attempt flags")
    if not plays.receiver_player_id.dropna().map(
        lambda value: isinstance(value, str) and bool(value) and value == value.strip()
    ).astype(bool).all():
        fail("invalid context receiver identity")
    try:
        plays["epa"] = pd.to_numeric(plays.epa, errors="raise")
        official = pd.to_numeric(source.receiving_epa, errors="raise")
    except (ValueError, TypeError) as error:
        fail(f"EPA must be numeric: {error}")
    if np.isinf(plays.epa.to_numpy(dtype=float, na_value=np.nan)).any() or np.isinf(official.to_numpy(dtype=float, na_value=np.nan)).any():
        fail("EPA must be finite or missing")
    # Upstream sums missing air-yard inputs as zero. Inspect coverage ourselves
    # before accepting that aggregate, without making EPA depend on air yards.
    for frame, column, missing_allowed in ((plays, "air_yards", True),
                                           (source, "receiving_air_yards", False)):
        try:
            air = pd.to_numeric(frame[column], errors="raise")
            numeric = air.to_numpy(dtype=float, na_value=np.nan)
        except (ValueError, TypeError) as error:
            fail(f"air yards must be numeric: {error}")
        valid = numeric[~np.isnan(numeric)] if missing_allowed else numeric
        if (not np.isfinite(valid).all() or not (valid == np.trunc(valid)).all()
                or (valid < np.iinfo(np.int32).min).any() or (valid > np.iinfo(np.int32).max).any()):
            fail("air yards must be finite integers within SQL storage range")
        if missing_allowed:
            plays["air_yards"] = air
        else:
            official_air = air
    plays = plays.loc[plays[flags].eq(1).any(axis=1) & plays.receiver_player_id.notna() & plays.split_value.notna()].copy()
    plays["positive_epa"] = plays.epa.gt(0).astype(int)
    grouped = plays.groupby(["receiver_player_id", "split_value"]).agg(
        target_plays=("play_id", "size"), epa_plays=("epa", "count"),
        epa_total=("epa", "sum"), successful=("positive_epa", "sum"),
        air_plays=("air_yards", "count"), air_total=("air_yards", "sum"),
    ).rename_axis(index=["player_id", "split_value"])
    aligned = source[["player_id", "split_value"]].join(grouped, on=["player_id", "split_value"])
    complete = (source.targets.gt(0) & aligned.target_plays.eq(source.targets)
                & aligned.epa_plays.eq(aligned.target_plays))
    if targets_unavailable([season]):
        complete[:] = False
    same_epa = np.isclose(official.to_numpy(dtype=float, na_value=np.nan),
                          aligned.epa_total.to_numpy(dtype=float, na_value=np.nan), rtol=1e-9, atol=1e-7)
    result = pd.DataFrame(index=source.index)
    result["epa"] = (official / source.targets.replace(0, np.nan)).where(complete & same_epa).round(4).astype("Float64")
    result["success_pct"] = (100 * aligned.successful / source.targets.replace(0, np.nan)).where(complete).round(1).astype("Float64")
    # An observed zero-target lateral-only bucket has zero target air yards,
    # although it has no target-based rates. Never replace missing per-play air
    # yards with zero when one or more targets do exist.
    matching_targets = aligned.target_plays.fillna(0).eq(source.targets)
    complete_air = (matching_targets & aligned.air_plays.fillna(0).eq(source.targets)
                    & official_air.eq(aligned.air_total.fillna(0)))
    if air_yards_unavailable([season]):
        complete_air[:] = False
    result["air_yards"] = official_air.where(complete_air).astype("Int64")
    return result
