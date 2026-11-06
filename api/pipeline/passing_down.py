"""Passing count validation and admission shared by every offline split view."""
import hashlib

import duckdb
import numpy as np
import pandas as pd

from pipeline.source_results import SourceError
from splits_core import PLAYER_COLUMNS
from pipeline.passing_dimensions import DIMENSIONS, context_split_values


COUNTS = ("attempts", "completions", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered")
MAPPING = dict(zip(COUNTS[:5], ("att", "cmp", "yards", "td", "interceptions")))
UNVERIFIED = ("air_yards", "yac", "first_downs", "epa", "success_pct", "cpoe")
CONTEXT = ("game_id", "play_id", "season", "season_type", "down", "passer_player_id",
           "pass_attempt", "sack", "two_point_attempt")


def _require(condition, season, message):
    if not condition:
        raise SourceError("passing_down_preview", season, message)


def _counts(frame, season, *, down=False, dimension="down"):
    columns = ["player_id", "season", "season_type", *COUNTS, *(["split_value"] if down else [])]
    _require(not set(columns) - set(frame), season, "count export missing columns")
    result = frame[columns].copy()
    _require(result.season.eq(season).all() and result.season_type.eq("REG").all(), season, "unexpected count scope")
    identified = result.player_id.notna()
    _require(result.loc[identified, "player_id"].map(
        lambda player: isinstance(player, str) and bool(player) and player == player.strip()).astype(bool).all(), season, "invalid player identity")
    if down:
        result["split_value"] = result.split_value.astype("string")
        _require(result.split_value.isin(DIMENSIONS[dimension]).all(), season, f"invalid {dimension} bucket")
    _require(not result.duplicated(["player_id", *(["split_value"] if down else [])]).any(), season, "duplicate count keys")
    try:
        values = result[list(COUNTS)].apply(pd.to_numeric, errors="raise")
        numbers = values.to_numpy(dtype=float, na_value=np.nan)
        _require(not any(result[c].map(lambda v: isinstance(v, (bool, np.bool_))).astype(bool).any() for c in COUNTS)
                 and np.isfinite(numbers).all() and (numbers == np.trunc(numbers)).all()
                 and (np.abs(numbers) <= 2147483647).all(), season, "counts must be finite integers")
        _require(values[[c for c in COUNTS if c != "passing_yards"]].ge(0).all().all(), season, "negative count")
        _require((values.completions + values.passing_interceptions <= values.attempts).all()
                 and (values.passing_tds <= values.completions).all(), season, "impossible passing counts")
        result[list(COUNTS)] = values.astype("int64")
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError("passing_down_preview", season, "counts must be numeric integers") from error
    return result.loc[identified].copy()


def _totals(frame):
    return frame.groupby("player_id")[list(COUNTS)].sum()


def _equal(left, right, season, label):
    a, b = left.align(right, fill_value=0)
    _require(a.eq(b).all().all(), season, f"{label} counts differ")


def _qualify(context, season):
    _require(not set(CONTEXT) - set(context), season, "context missing required fields")
    _require(not context.empty and context.season.eq(season).all() and context.season_type.eq("REG").all()
             and context.two_point_attempt.fillna(0).eq(0).all(), season, "unexpected context scope")
    _require(not context[["game_id", "play_id"]].isna().any().any()
             and not context.duplicated(["game_id", "play_id"]).any(), season, "invalid or duplicate play keys")
    _require(context.game_id.map(lambda v: isinstance(v, str) and bool(v.strip())).all(), season, "invalid game identity")
    try:
        keys = pd.to_numeric(context.play_id, errors="raise").to_numpy(dtype=float)
        down = pd.to_numeric(context.down.dropna(), errors="raise").to_numpy(dtype=float)
        _require(np.isfinite(keys).all() and (keys >= 0).all() and (keys == np.trunc(keys)).all()
                 and np.isfinite(down).all() and (down == np.trunc(down)).all(), season, "invalid numeric play context")
    except (TypeError, ValueError) as error:
        raise SourceError("passing_down_preview", season, "invalid numeric play context") from error
    for field in ("pass_attempt", "sack", "two_point_attempt"):
        _require(context[field].dropna().isin([0, 1]).all(), season, "invalid dropback flags")
    _require(context.passer_player_id.dropna().map(
        lambda player: isinstance(player, str) and bool(player) and player == player.strip()).astype(bool).all(), season, "invalid passer identity")
    from splits_builder import qualification_ctes
    sql = qualification_ctes("passing", season, set(context), minimal=True)
    with duckdb.connect(":memory:") as conn:
        conn.register("plays", context)
        admitted = conn.execute(sql + """ SELECT player_id,COUNT(*) AS qualifying_plays
            FROM base JOIN qualified USING(player_id) GROUP BY player_id ORDER BY player_id""").fetchall()
    return dict(admitted), hashlib.sha256(sql.encode()).hexdigest()


def adapt_passing_down(*, context, whole, classified, excluded, down, weekly, season):
    """Validate every supplied player's six counts before applying existing admission.

    Sack-only buckets remain represented. Unchecked efficiency fields stay NULL;
    sacks remain in the raw/count evidence because player_splits has no sack column.
    No database connection outside isolated in-memory qualification is opened.
    """
    return adapt_passing_partition(context=context, whole=whole, classified=classified,
                                  excluded=excluded, down=down, weekly=weekly, season=season)


def adapt_passing_partition(*, context, whole, classified, excluded, down, weekly, season, dimension="down"):
    """Shared count admission and conservation for any verified passing view."""
    _require(type(season) is int and season >= 1999, season, "invalid season")
    _require(dimension in DIMENSIONS, season, "unsupported passing dimension")
    qualified, sql_sha = _qualify(context, season)
    labels = context_split_values(context, dimension, season)
    frames = {name: _counts(value, season, down=name == "down", dimension=dimension) for name, value in (
        ("whole", whole), ("classified", classified), ("excluded", excluded), ("down", down), ("weekly", weekly))}
    totals = {name: _totals(value) for name, value in frames.items()}
    _equal(totals["whole"], totals["weekly"], season, "whole versus weekly")
    _equal(totals["down"], totals["classified"], season, "Down versus classified")
    _equal(totals["classified"].add(totals["excluded"], fill_value=0), totals["whole"], season, "classified plus excluded versus whole")
    for bucket in DIMENSIONS[dimension]:
        _require(labels.eq(bucket).any() or not frames["down"].loc[
            frames["down"].split_value.eq(bucket), list(COUNTS)].ne(0).any().any(),
            season, "production in a bucket with no member plays")
    for active, name in ((labels.notna().any(), "classified"), (labels.isna().any(), "excluded")):
        _require(active or not frames[name][list(COUNTS)].ne(0).any().any(),
                 season, "production in an empty play population")
    for label in ("whole", "classified", "excluded", "down"):
        frame = frames[label]
        frames[label] = frame.loc[frame[list(COUNTS)].ne(0).any(axis=1)]
    observed = set(frames["whole"].player_id)
    _require(not set(qualified) - observed, season, "qualifying passer missing from whole counts")
    selected = frames["down"].loc[frames["down"].player_id.isin(qualified)].copy()
    output = selected.rename(columns=MAPPING)
    output["category"], output["split_dim"] = "passing", dimension
    output["sort_order"] = output.split_value.map({value: index for index, value in enumerate(DIMENSIONS[dimension], 1)}).astype("Int64")
    if dimension == "opponent":
        output["sort_order"] = pd.Series(pd.NA, index=output.index, dtype="Int64")
    for field in UNVERIFIED:
        output[field] = None
    output = output[list(PLAYER_COLUMNS)].sort_values(["player_id", "sort_order"]).reset_index(drop=True)
    outside = frames["excluded"].loc[frames["excluded"].player_id.isin(qualified)]
    report = {"status": "preview_only", "publication_ready": False, "season": season,
              "scope": "supplied REG nonconversion games; passing counts only",
              "rows": len(output), "qualified_players": len(qualified), "qualifying_plays": qualified,
              "qualification_sql_sha256": sql_sha, "count_checks": "whole/weekly, Down/classified, classified+excluded/whole: exact for all players",
              "context": {"plays": len(context), "classified": int(labels.notna().sum()),
                          "excluded": int(labels.isna().sum())},
              "qualified_excluded_counts": {field: int(outside[field].sum()) for field in COUNTS},
              "unavailable_metrics": {field: "Not validated by this passing count preview" for field in UNVERIFIED},
              "sacks": "Verified in exports and comparisons; no canonical player_splits sack column"}
    return output, report
