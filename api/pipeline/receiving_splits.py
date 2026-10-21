"""Offline boundary from official nflfastR exports to player_splits rows.

Receiving Down/quarter preview. No R execution, downloads, database writes or new
qualification rules. Callers supply the players admitted by the existing build.
Unsupported metrics are NULL; this output must not replace complete live rows.
"""
from collections.abc import Collection
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.source_results import SourceError
from pipeline.receiving_dimensions import DIMENSIONS
from pipeline.receiving_target_metrics import receiving_target_metrics
from services.receiving_coverage import targets_unavailable, yac_unavailable


EXPORT_CONTRACT = {
    "schema_version": 6,
    "season_type": "REG",
    "excludes_two_point_attempts": True,
    "summary_level": "season",
    "split_dimensions": list(DIMENSIONS),
}
VERSIONS = {"nflfastR": "6.0.0", "nflreadr": "1.5.1"}
_PRODUCTION = {"targets": "att", "receptions": "cmp", "receiving_yards": "yards", "receiving_tds": "td"}
_COUNTS = {**_PRODUCTION, "receiving_yards_after_catch": "yac", "receiving_first_downs": "first_downs"}
_UNSUPPORTED = ("interceptions", "cpoe")
_TARGET_METRICS = ("epa", "success_pct", "air_yards")
_COLUMNS = ("player_id", "season", "category", "split_dim", "split_value", "sort_order",
            "att", "cmp", "yards", "td", "interceptions", "air_yards", "yac",
            "first_downs", "epa", "success_pct", "cpoe")


def _error(season: int, reason: str) -> SourceError:
    return SourceError("nflfastR_receiving_splits", season, reason)


def adapt_receiving_splits(frame: pd.DataFrame, *, context: pd.DataFrame, season: int,
                           qualified_players: Collection[str], dimension: str = "down") -> pd.DataFrame:
    """Validate all source rows, then map admitted players' observed counts.

    Observed target records are not a completeness claim. Do not infer admission
    from them: historical target gaps would discard usable receiving production.
    A lateral can have yards/TD without a target/catch; negative yards/YAC are valid.
    """
    if dimension not in DIMENSIONS:
        raise _error(season, "unsupported split dimension")
    buckets = DIMENSIONS[dimension]
    if not isinstance(qualified_players, Collection) or isinstance(qualified_players, (str, bytes)) or any(
        not isinstance(player, str) or not player.strip() for player in qualified_players
    ):
        raise _error(season, "qualified_players must contain nonempty player IDs")
    required = {"player_id", "season", "season_type", "split_value", "receiving_epa", "receiving_air_yards", *_COUNTS}
    if missing := required - set(frame.columns):
        raise _error(season, f"export is missing columns {sorted(missing)}")
    source = frame.copy()
    if source.empty:
        raise _error(season, "receiving export is empty")
    if source[["season", "season_type"]].isna().any().any() or not source.season.eq(season).all() or not source.season_type.eq("REG").all():
        raise _error(season, "export contains unexpected season or season_type")
    source["split_value"] = source.split_value.astype("string")
    if not source.split_value.isin(buckets).all():
        raise _error(season, f"export contains invalid {dimension} values")
    identified = source.player_id.notna()
    if not source.loc[identified, "player_id"].map(
        lambda player: isinstance(player, str) and bool(player) and player == player.strip()
    ).all():
        raise _error(season, "export contains invalid player IDs")
    if source.loc[identified].duplicated(["player_id", "season", "split_value"]).any():
        raise _error(season, "export contains duplicate player/bucket rows")
    try:
        values = source[list(_COUNTS)].apply(pd.to_numeric, errors="raise")
        numeric = values.to_numpy(dtype=float, na_value=np.nan)
    except (TypeError, ValueError) as error:
        raise _error(season, "export counts must be numeric") from error
    if not np.isfinite(numeric).all() or not (numeric == np.trunc(numeric)).all():
        raise _error(season, "export counts must be finite integers")
    limits = np.iinfo(np.int32)
    if ((numeric < limits.min) | (numeric > limits.max)).any():
        raise _error(season, "export counts exceed player_splits integer storage")
    if values[["targets", "receptions", "receiving_tds", "receiving_first_downs"]].lt(0).any().any():
        raise _error(season, "export has negative target/catch/TD/first-down counts")
    if values.receiving_first_downs.gt(values.receptions).any():
        raise _error(season, "receiving first downs exceed receptions")
    source[list(_COUNTS)] = values
    source[list(_TARGET_METRICS)] = receiving_target_metrics(source, context, season, dimension=dimension)
    # The all-position calculator also emits zero receiving lines. Test activity
    # before target masking so unknown historical targets cannot become fake 0s.
    activity_fields = [*_PRODUCTION, "receiving_first_downs"]
    if not yac_unavailable([season]):
        activity_fields.append("receiving_yards_after_catch")
    active = values[activity_fields].ne(0).any(axis=1)
    source = source.loc[identified & active & source.player_id.isin(qualified_players)]
    result = source[["player_id", "season", "split_value", *_COUNTS, *_TARGET_METRICS]].rename(columns=_COUNTS).copy()
    result["category"] = "receiving"
    result["split_dim"] = dimension
    result["sort_order"] = result.split_value.map({value: index for index, value in enumerate(buckets, 1)}).astype("Int64")
    for column in ("season", *_COUNTS.values()):
        result[column] = result[column].astype("Int64")
    if targets_unavailable([season]):
        result["att"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    if yac_unavailable([season]):
        result["yac"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    for column in _UNSUPPORTED:
        dtype = "Float64" if column == "cpoe" else "Int64"
        result[column] = pd.Series(pd.NA, index=result.index, dtype=dtype)
    return result[list(_COLUMNS)].sort_values(["player_id", "sort_order"]).reset_index(drop=True)


def load_receiving_split_export(directory: Path, *, season: int,
                               qualified_players: Collection[str],
                               manifest: dict | None = None, dimension: str = "down") -> pd.DataFrame:
    """Read a completed, versioned R trial export; fail closed on scope drift.

    Read verified bytes rather than reopening files after their hash check.
    Digests detect changed files; they are not publisher authentication or a
    substitute for candidate reconciliation.
    """
    if dimension not in DIMENSIONS:
        raise _error(season, "unsupported split dimension")
    try:
        if manifest is None:
            manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise _error(season, "completion marker must be an object")
        contract = manifest.get("receiving_export")
        if (contract != EXPORT_CONTRACT
                or type(contract.get("schema_version")) is not int
                or type(contract.get("excludes_two_point_attempts")) is not bool):
            raise _error(season, "unsupported export scope or schema version")
        if any(manifest.get(package) != version for package, version in VERSIONS.items()):
            raise _error(season, "unsupported calculator package versions")
        seasons = manifest.get("seasons")
        if not isinstance(seasons, list) or season not in seasons:
            raise _error(season, "requested season is absent from completion marker")
        frame = read_export_csv(directory, manifest, f"{dimension}-{season}.csv", season=season)
        context = read_export_csv(directory, manifest, f"context-{season}.csv", season=season)
    except (OSError, ValueError) as error:
        raise _error(season, f"cannot read completed export: {error}") from error
    return adapt_receiving_splits(frame, context=context, season=season,
                                  qualified_players=qualified_players, dimension=dimension)


def read_export_csv(directory: Path, manifest: dict, name: str, *, season: int) -> pd.DataFrame:
    """Parse only the exact CSV bytes whose SHA256 matches the completion record."""
    if Path(name).name != name:
        raise _error(season, "export name must be a plain filename")
    hashes = manifest.get("files")
    expected = hashes.get(name) if isinstance(hashes, dict) else None
    if not isinstance(expected, str) or len(expected) != 64:
        raise _error(season, f"missing SHA256 for {name}")
    data = (directory / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise _error(season, f"SHA256 mismatch for {name}")
    return pd.read_csv(io.BytesIO(data), dtype={"player_id": "string", "split_value": "string"})
