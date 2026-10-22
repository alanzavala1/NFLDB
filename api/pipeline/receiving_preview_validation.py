"""Verified export loading and reference checks for the offline receiving worker."""
from pathlib import Path

import pandas as pd

from pipeline.receiving_dimensions import DIMENSIONS, context_split_values
from pipeline.receiving_partition_validation import validate_official_counts, validate_receiving_partition
from pipeline.receiving_splits import adapt_receiving_splits, read_export_csv, validate_export_manifest
from pipeline.snapshots import CandidateError
from services.receiving_coverage import air_yards_unavailable, targets_unavailable, yac_unavailable
from pipeline.receiving_context_rules import POLICIES


_BASE_COUNTS = {"receptions": "cmp", "receiving_yards": "yards", "receiving_tds": "td",
                "receiving_first_downs": "first_downs"}


def _supported_counts(season: int) -> dict:
    fields = dict(_BASE_COUNTS)
    if not targets_unavailable([season]):
        fields["targets"] = "att"
    if not yac_unavailable([season]):
        fields["receiving_yards_after_catch"] = "yac"
    return fields


def _match(actual: pd.Series, expected: pd.Series, label: str) -> None:
    actual, expected = actual.align(expected, fill_value=0)
    if not actual.eq(expected).all():
        raise CandidateError(f"receiving: {label} does not match reference counts")


def validate_whole_receiving(overall: pd.DataFrame, weekly: pd.DataFrame,
                              season: int, qualified: list[str]) -> dict:
    """Keep the independent whole-season/weekly gate alongside subset checks.

    Weekly EPA includes conversions, so it is deliberately not this count check's
    reference. Raw air sums may agree despite missing inputs; equality is not a
    completeness certificate and never unmasks an air-yard result.
    """
    full = validate_official_counts(overall, season)
    reference = validate_official_counts(weekly, season, weekly=True)
    if full.empty or reference.empty:
        raise CandidateError(f"receiving[{season}]: missing whole/weekly reference")
    fields = list(_supported_counts(season))
    if not air_yards_unavailable([season]):
        fields.append("receiving_air_yards")
    actual = full.loc[full.player_id.isin(qualified)].groupby("player_id")[fields].sum()
    expected = reference.loc[reference.player_id.isin(qualified)].groupby("player_id")[fields].sum()
    for field in fields:
        _match(actual[field], expected[field], f"whole-season {field} versus weekly")
    return {"production_matches_weekly": True, "matched_fields": fields,
            "players": len(qualified), "scope": "whole REG nonconversion receiving counts"}


def _validate_adapted(rows: pd.DataFrame, classified: pd.DataFrame, coverage: dict,
                       season: int, qualified: list[str]) -> dict:
    expected_players = set(qualified) - set(coverage["qualified_without_classified_production"])
    if set(rows.player_id) != expected_players:
        raise CandidateError(f"receiving[{season}]: classified player missing from preview")
    counts = _supported_counts(season)
    for field, unavailable in (("att", targets_unavailable([season])),
                                ("yac", yac_unavailable([season])),
                                ("air_yards", air_yards_unavailable([season]))):
        if unavailable and rows[field].notna().any():
            raise CandidateError(f"receiving[{season}]: unsupported historical {field} must be NULL")
    reference = classified.loc[classified.player_id.isin(qualified)]
    for source, target in counts.items():
        if rows[target].isna().any():
            raise CandidateError(f"receiving[{season}]: missing supported {target} count")
        _match(rows.groupby("player_id")[target].sum(), reference.groupby("player_id")[source].sum(),
               f"classified {source}")
    air_matches = 0
    if not air_yards_unavailable([season]):
        grouped = rows.groupby("player_id")
        complete = grouped.air_yards.count().eq(grouped.size())
        players = complete[complete].index
        _match(grouped.air_yards.sum(min_count=1).reindex(players),
               reference.groupby("player_id").receiving_air_yards.sum().reindex(players),
               "classified receiving_air_yards")
        air_matches = len(players)
    return {
        "players": len(qualified), "represented_players": len(expected_players), "rows": len(rows),
        "production_matches_classified": True, "coverage": coverage,
        "targets": "unavailable" if targets_unavailable([season]) else "matched_classified",
        "yac": "unavailable" if yac_unavailable([season]) else "matched_classified",
        "first_downs": "matched_classified",
        "air_yards": {"available_rows": int(rows.air_yards.notna().sum()),
                      "unavailable_rows": int(rows.air_yards.isna().sum()),
                      "players_matched_classified": air_matches},
        "target_rates": {"definition": "original target role; EPA/tgt and percent EPA > 0",
                         "epa_rows": int(rows.epa.notna().sum()),
                         "success_rows": int(rows.success_pct.notna().sum()),
                         "unavailable_epa_rows": int(rows.epa.isna().sum()),
                         "unavailable_success_rows": int(rows.success_pct.isna().sum())},
    }


def load_receiving_preview_partition(directory: Path, manifest: dict, *, context: pd.DataFrame,
                                      overall: pd.DataFrame, season: int, dimension: str,
                                      qualified: list[str]) -> tuple[pd.DataFrame, dict]:
    """Read each bound subset once; validate raw scope before adapting/admission.

    The worker supplies the already hash-verified shared context/whole frames.
    Empty classified output is admitted only after the full partition proof.
    """
    validate_export_manifest(manifest, season)
    frames = {}
    names = [f"context-{season}.csv", f"overall-{season}.csv"]
    names.extend(["definitions.json", "producer.R"])
    if dimension in ("play_action", "blitz"):
        names.extend(["ftn-inputs.json", f"ftn-{season}.csv"])
    for kind in ("buckets", "membership", "classified", "excluded"):
        name = f"{dimension}-{season}.csv" if kind == "buckets" else f"{kind}-{dimension}-{season}.csv"
        frames[kind] = read_export_csv(directory, manifest, name, season=season)
        names.append(name)
    expected = context.copy()
    expected["split_value"] = context_split_values(context, dimension, season)
    coverage = validate_receiving_partition(
        context=expected, membership=frames["membership"], bucket_stats=frames["buckets"],
        classified=frames["classified"], excluded=frames["excluded"], overall=overall,
        season=season, buckets=DIMENSIONS[dimension], qualified_players=qualified,
        source_revisions={name: manifest["files"][name] for name in names},
        missing_reason=f"missing {dimension} play context",
    )
    coverage["definition"] = POLICIES.get(dimension, "Existing situational split definition")
    if dimension == "pressure" and season < 2006:
        coverage["reason"] = "QB-hit coverage not established before 2006"
    if dimension in ("play_action", "blitz"):
        coverage["reason"] = ("FTN charting unsupported before 2022" if season < 2022 else
                              "Uncharted play or missing/unsupported charting field" if coverage["plays"]["excluded"] else None)
    rows = adapt_receiving_splits(frames["buckets"], context=context, season=season,
                                  qualified_players=qualified, dimension=dimension, allow_empty=True)
    return rows, _validate_adapted(rows, frames["classified"], coverage, season, qualified)
