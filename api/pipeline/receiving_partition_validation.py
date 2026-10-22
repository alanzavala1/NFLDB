"""Pure conservation checks for receiving views with incomplete play context.

References come from official calculate_stats calls on the whole, classified and
excluded play sets. This validates those exports; it does not calculate credits,
infer missing context, qualify players or authorize publication.
"""
from collections.abc import Collection, Mapping

import numpy as np
import pandas as pd

from pipeline.snapshots import CandidateError
from services.receiving_coverage import targets_unavailable, yac_unavailable


COUNT_FIELDS = ("targets", "receptions", "receiving_yards", "receiving_tds",
                "receiving_yards_after_catch", "receiving_first_downs", "receiving_air_yards")
_NONNEGATIVE = ("targets", "receptions", "receiving_tds", "receiving_first_downs")
_KEYS = ["game_id", "play_id"]


def _fail(reason: str) -> None:
    raise CandidateError(f"receiving partition: {reason}")


def _counts(frame: pd.DataFrame, season: int, *, bucketed: bool = False) -> pd.DataFrame:
    required = {"player_id", "season", "season_type", *COUNT_FIELDS}
    if bucketed:
        required.add("split_value")
    if required - set(frame.columns):
        _fail("missing official count columns")
    if (frame[["season", "season_type"]].isna().any().any()
            or not frame.season.eq(season).all() or not frame.season_type.eq("REG").all()):
        _fail("unexpected official count scope")
    if not frame.player_id.dropna().map(
        lambda value: isinstance(value, str) and bool(value) and value == value.strip()
    ).all():
        _fail("invalid official player identity")
    keys = ["player_id", "split_value"] if bucketed else ["player_id"]
    if frame.duplicated(keys).any():
        _fail("duplicate official player/bucket rows")
    try:
        result = frame.copy()
        result[list(COUNT_FIELDS)] = frame[list(COUNT_FIELDS)].apply(pd.to_numeric, errors="raise")
        numeric = result[list(COUNT_FIELDS)].to_numpy(dtype=float, na_value=np.nan)
    except (ValueError, TypeError) as error:
        _fail(f"invalid official counts: {error}")
    limits = np.iinfo(np.int32)
    if (not np.isfinite(numeric).all() or not (numeric == np.trunc(numeric)).all()
            or (numeric < limits.min).any() or (numeric > limits.max).any()):
        _fail("official counts must be finite integers within SQL storage range")
    if result[list(_NONNEGATIVE)].lt(0).any().any():
        _fail("negative target/catch/TD/first-down counts")
    if result.receiving_first_downs.gt(result.receptions).any():
        _fail("first downs exceed receptions")
    result[list(COUNT_FIELDS)] = result[list(COUNT_FIELDS)].astype("int64")
    # Empty string cannot be an identified player. Retain upstream's unidentified
    # group for conservation instead of silently dropping it during groupby.
    result["player_id"] = result.player_id.fillna("")
    return result


def _totals(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.groupby("player_id")[list(COUNT_FIELDS)].sum()


def _equal(actual: pd.DataFrame, expected: pd.DataFrame, label: str) -> None:
    actual, expected = actual.align(expected, fill_value=0)
    if not actual.eq(expected).all().all():
        fields = actual.ne(expected).any()
        _fail(f"{label} differs for {', '.join(fields[fields].index)}")


def validate_receiving_partition(
    *, context: pd.DataFrame, membership: pd.DataFrame, bucket_stats: pd.DataFrame,
    classified: pd.DataFrame, excluded: pd.DataFrame, overall: pd.DataFrame,
    season: int, buckets: Collection[str], qualified_players: Collection[str],
    source_revisions: Mapping[str, str], missing_reason: str,
) -> dict:
    """Check exact membership and per-player count conservation before admission.

    ``context.split_value`` is the independently derived expected classification;
    ``membership`` is the calculator producer's exported game/play assignment.
    A missing label means excluded, never a default bucket. Counts are observed
    upstream counts, including historically incomplete targets; arithmetic alone
    does not certify their completeness. Rate/air coverage remains a separate gate.
    """
    if (not isinstance(buckets, Collection) or isinstance(buckets, (str, bytes)) or not buckets
            or any(not isinstance(value, str) or not value or value != value.strip() for value in buckets)
            or len(set(buckets)) != len(buckets)):
        _fail("provide distinct nonempty bucket labels")
    if (not isinstance(qualified_players, Collection) or isinstance(qualified_players, (str, bytes))
            or any(not isinstance(value, str) or not value or value != value.strip()
                   for value in qualified_players)):
        _fail("invalid qualified player identities")
    if (not isinstance(source_revisions, Mapping) or not source_revisions or any(
        not isinstance(name, str) or not name or not isinstance(digest, str)
        or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
        for name, digest in source_revisions.items()
    )):
        _fail("provide verified input SHA256 revisions")
    if not isinstance(missing_reason, str) or not missing_reason.strip():
        _fail("provide an explicit missing-context reason")
    required = {*_KEYS, "season", "season_type", "two_point_attempt", "split_value"}
    if required - set(context.columns) or {*_KEYS, "split_value"} - set(membership.columns):
        _fail("missing play membership columns")
    if (context.empty or context[["season", "season_type"]].isna().any().any()
            or not context.season.eq(season).all() or not context.season_type.eq("REG").all()
            or not context.two_point_attempt.dropna().isin([0, 1]).all()
            or context.two_point_attempt.eq(1).any()):
        _fail("unexpected play context scope")
    for frame in (context, membership):
        if frame[_KEYS].isna().any().any() or frame.duplicated(_KEYS).any():
            _fail("missing or duplicate game/play membership")
        if not frame.split_value.dropna().isin(buckets).all():
            _fail("invalid play bucket")
    joined = context[_KEYS + ["split_value"]].merge(
        membership[_KEYS + ["split_value"]], on=_KEYS, how="outer",
        validate="one_to_one", indicator=True, suffixes=("_expected", "_exported"),
    )
    expected, exported = joined.split_value_expected, joined.split_value_exported
    same = expected.eq(exported).fillna(False) | (expected.isna() & exported.isna())
    if not joined._merge.eq("both").all() or not same.all():
        _fail("exported membership differs from independently classified play IDs")

    raw = _counts(bucket_stats, season, bucketed=True)
    covered, omitted, full = (_counts(frame, season) for frame in (classified, excluded, overall))
    if raw.split_value.isna().any() or not raw.split_value.isin(buckets).all():
        _fail("invalid official bucket")
    for bucket in buckets:
        if not context.split_value.eq(bucket).any() and raw.loc[
            raw.split_value.eq(bucket), list(COUNT_FIELDS)
        ].ne(0).any().any():
            _fail("official production in a bucket with no member plays")
    included_plays = int(context.split_value.notna().sum())
    excluded_plays = len(context) - included_plays
    for plays, frame in ((included_plays, covered), (excluded_plays, omitted)):
        if plays == 0 and frame[list(COUNT_FIELDS)].ne(0).any().any():
            _fail("official production in an empty play population")
    _equal(_totals(raw), _totals(covered), "buckets versus classified reference")
    _equal(_totals(covered).add(_totals(omitted), fill_value=0), _totals(full),
           "classified plus excluded versus whole reference")

    # Admission is global. A player may have all receiving production on excluded
    # plays and legitimately have no row in this particular view.
    activity = ["targets", "receptions", "receiving_yards", "receiving_tds", "receiving_first_downs"]
    if not yac_unavailable([season]):
        activity.append("receiving_yards_after_catch")
    full_players = set(full.loc[full[activity].ne(0).any(axis=1), "player_id"])
    qualified = set(qualified_players)
    if not qualified.issubset(full_players):
        _fail("qualified player missing from whole receiving reference")
    covered_players = set(covered.loc[covered[activity].ne(0).any(axis=1), "player_id"])
    production = {}
    for name, frame in (("classified", covered), ("excluded", omitted), ("overall", full)):
        production[name] = {key: int(value) for key, value in
                            frame.loc[frame.player_id.isin(qualified), list(COUNT_FIELDS)].sum().items()}
    return {
        "status": "unavailable" if included_plays == 0 else "partial" if excluded_plays else "complete",
        "reason": missing_reason if excluded_plays else None,
        "source_revisions": dict(source_revisions),
        "plays": {"overall": len(context), "classified": included_plays, "excluded": excluded_plays},
        "qualified_players": len(qualified),
        "qualified_without_classified_production": sorted(qualified - covered_players),
        "qualified_production": production,
        "checks": {"exact_play_membership": True, "disjoint_buckets": True,
                   "buckets_match_classified": True, "classified_plus_excluded_matches_overall": True},
        "count_scope": "observed official counts; not a metric completeness certificate",
        "historical_masks": {"targets_unavailable": targets_unavailable([season]),
                             "yac_unavailable": yac_unavailable([season])},
    }
