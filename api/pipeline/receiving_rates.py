"""Target-role rates for the isolated receiving preview, not lateral allocation."""
import numpy as np
import pandas as pd

from pipeline.source_results import SourceError
from services.receiving_coverage import targets_unavailable


def receiving_rates(source: pd.DataFrame, context: pd.DataFrame, season: int) -> pd.DataFrame:
    """Require complete matching target/EPA populations before exposing a rate.

    Success is EPA > 0, calculated here because calculate_stats has no success
    output. Missing EPA is not a failed play. Official receiving EPA must also
    match the target-play numerator before it can be divided by target credits.
    """
    def fail(reason):
        raise SourceError("nflfastR_receiving_rates", season, reason)

    flags = ["complete_pass", "incomplete_pass", "interception"]
    required = {"game_id", "play_id", "season", "season_type", "two_point_attempt",
                "down", "receiver_player_id", "epa", *flags}
    if required - set(context.columns):
        fail("missing target context columns")
    plays = context.copy()
    if (plays[["season", "season_type"]].isna().any().any()
            or not plays.season.eq(season).all() or not plays.season_type.eq("REG").all()
            or plays.two_point_attempt.eq(1).any()):
        fail("unexpected target context scope")
    if plays[["game_id", "play_id"]].isna().any().any() or plays.duplicated(["game_id", "play_id"]).any():
        fail("missing or duplicate play identity")
    if not plays.down.dropna().isin([1, 2, 3, 4]).all():
        fail("invalid context down")
    for flag in [*flags, "two_point_attempt"]:
        if not plays[flag].dropna().isin([0, 1]).all():
            fail("invalid context attempt flags")
    if not plays.receiver_player_id.dropna().map(
        lambda value: isinstance(value, str) and bool(value) and value == value.strip()
    ).all():
        fail("invalid context receiver identity")
    try:
        plays["epa"] = pd.to_numeric(plays.epa, errors="raise")
        official = pd.to_numeric(source.receiving_epa, errors="raise")
    except (ValueError, TypeError) as error:
        fail(f"EPA must be numeric: {error}")
    if np.isinf(plays.epa.to_numpy(dtype=float, na_value=np.nan)).any() or np.isinf(official.to_numpy(dtype=float, na_value=np.nan)).any():
        fail("EPA must be finite or missing")
    plays = plays.loc[plays[flags].eq(1).any(axis=1) & plays.receiver_player_id.notna() & plays.down.notna()].copy()
    plays["split_value"] = plays.down.astype(int).astype(str)
    plays["positive_epa"] = plays.epa.gt(0).astype(int)
    grouped = plays.groupby(["receiver_player_id", "split_value"]).agg(
        target_plays=("play_id", "size"), epa_plays=("epa", "count"),
        epa_total=("epa", "sum"), successful=("positive_epa", "sum"),
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
    return result
