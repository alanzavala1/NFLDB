"""Passing metric availability from matching per-play player populations.

Counts come from detailed credits; modeled EPA/CPOE come from the PBP passer.
Never combine them silently when those identities or contributions disagree.
"""
import numpy as np
import pandas as pd

from pipeline.passing_down import CONTEXT, COUNTS, _equal, _require
from pipeline.passing_dimensions import DIMENSIONS, context_split_values


METRIC_CONTEXT = (*CONTEXT, "play_type", "complete_pass", "incomplete_pass", "interception",
                  "passing_yards", "pass_touchdown", "first_down", "qb_epa", "epa", "cpoe",
                  "air_yards", "yards_after_catch")
UPSTREAM_METRICS = ("passing_air_yards", "passing_yards_after_catch", "passing_first_downs",
                    "passing_epa", "passing_cpoe")
KEYS = ["game_id", "play_id", "player_id"]


def _numeric(frame, columns, season, *, integers=False, missing=True):
    result = frame.copy()
    for column in columns:
        try:
            values = pd.to_numeric(result[column], errors="raise")
            array = values.to_numpy(dtype=float, na_value=np.nan)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError(f"passing metric {column} must be numeric") from error
        known = array[~np.isnan(array)] if missing else array
        _require(not result[column].map(lambda v: isinstance(v, (bool, np.bool_))).astype(bool).any()
                 and np.isfinite(known).all(), season, f"invalid metric {column}")
        if integers:
            _require((known == np.trunc(known)).all() and (np.abs(known) <= 2147483647).all(),
                     season, f"invalid integral metric {column}")
        result[column] = values
    return result


def _credit_counts(credits, context, season):
    _require(not set([*KEYS[:2], "gsis_player_id", "stat_id", "yards"]) - set(credits),
             season, "missing metric credit fields")
    credits = _numeric(credits, ["play_id", "stat_id", "yards"], season, integers=True, missing=False)
    _require(not credits.game_id.isna().any() and credits.game_id.map(
        lambda v: isinstance(v, str) and bool(v.strip())).all(), season, "invalid credit game identity")
    _require(credits.gsis_player_id.dropna().map(lambda v: isinstance(v, str) and bool(v)
        and v == v.strip()).astype(bool).all(), season, "invalid credit player identity")
    selected = credits.loc[credits.stat_id.isin([14, 15, 16, 19, 20]) & credits.gsis_player_id.notna()].copy()
    selected = selected.merge(context[["game_id", "play_id"]], on=["game_id", "play_id"], validate="many_to_one")
    selected = selected.rename(columns={"gsis_player_id": "player_id"})
    selected["attempts"] = selected.stat_id.isin([14, 15, 16, 19]).astype(int)
    selected["completions"] = selected.stat_id.isin([15, 16]).astype(int)
    selected["passing_yards"] = selected.yards.where(selected.stat_id.isin([15, 16]), 0)
    for name, stat in (("passing_tds", 16), ("passing_interceptions", 19), ("sacks_suffered", 20)):
        selected[name] = selected.stat_id.eq(stat).astype(int)
    return selected.groupby(KEYS, as_index=False)[list(COUNTS)].sum()


def verify_passing_first_downs(frames, weekly, season):
    """Validate the native count against captured weekly data and partitions."""
    totals = {}
    for name, frame in [*frames.items(), ("weekly", weekly)]:
        _require(not {"passing_first_downs", "completions", "player_id"} - set(frame),
                 season, "missing passing first-down reference")
        values = _numeric(frame, ["passing_first_downs", "completions"], season,
                          integers=True, missing=False)
        _require(values.passing_first_downs.ge(0).all()
                 and values.passing_first_downs.le(values.completions).all(),
                 season, "impossible passing first-down reference")
        totals[name] = values.loc[values.player_id.notna()].groupby("player_id")[["passing_first_downs"]].sum()
    _equal(totals["whole"], totals["weekly"], season, "passing first downs: whole versus weekly")
    _equal(totals["down"], totals["classified"], season, "passing first downs: Down versus classified")
    _equal(totals["classified"].add(totals["excluded"], fill_value=0), totals["whole"],
           season, "passing first downs: classified plus excluded versus whole")


def apply_passing_metrics(rows, source, context, credits, season, *, dimension="down"):
    """Verify raw exports before admission; attach values and per-field reasons.

    EPA = typed pass/spike qb_epa sum / official attempts (including sacks in
    the numerator). Success = positive-EPA attempts / attempts. CPOE = mean on
    the provider's modeled pass/spike subset, not every attempt. Missing model
    inputs never become failed plays or zero EPA. Air/YAC require complete,
    independently matching air coverage; neither is supported before 2006.
    Passing YAC follows nflfastR: credited yards minus completed-pass air yards,
    rather than summing the separate PBP receiver YAC field.
    Official first downs are independently credited counts, not a model rate.
    """
    _require(not set(METRIC_CONTEXT) - set(context) and not set(UPSTREAM_METRICS) - set(source),
             season, "missing passing metric fields")
    from pipeline.passing_down import _qualify
    _qualify(context, season)
    p = _numeric(context, ["passing_yards", "first_down", "air_yards", "yards_after_catch"], season, integers=True)
    p = _numeric(p, ["epa", "qb_epa", "cpoe"], season)
    for flag in ("complete_pass", "incomplete_pass", "interception", "pass_touchdown", "first_down"):
        _require(p[flag].dropna().isin([0, 1]).all(), season, f"invalid metric flag {flag}")
    raw = _numeric(source, UPSTREAM_METRICS[:3], season, integers=True, missing=False)
    raw = _numeric(raw, UPSTREAM_METRICS[3:], season)
    _require(raw.passing_first_downs.ge(0).all()
             and raw.passing_first_downs.le(raw.completions).all(), season, "impossible passing first downs")
    _require(raw.passing_cpoe.dropna().between(-100, 100).all(), season, "invalid upstream CPOE")
    _require(p.cpoe.dropna().between(-100, 100).all(), season, "invalid PBP CPOE")
    p["player_id"] = p.passer_player_id
    # Whole-season metrics use all supplied plays, independently of whether a
    # particular context view can classify them. No new R export is required.
    p["split_value"] = "all" if dimension == "overall" else context_split_values(p, dimension, season)
    allowed = ("all",) if dimension == "overall" else DIMENSIONS[dimension]
    native = _credit_counts(credits, p, season)
    # This independently checks that the exported detailed-credit projection
    # produces every native Down count, before low-volume players are removed.
    located = native.merge(p[["game_id", "play_id", "split_value"]], on=["game_id", "play_id"], validate="many_to_one")
    located = located.loc[located.split_value.isin(allowed)]
    reference = located.groupby(["player_id", "split_value"])[list(COUNTS)].sum()
    exported = raw.loc[raw.player_id.notna()].set_index(["player_id", "split_value"])[list(COUNTS)]
    a, b = reference.align(exported, fill_value=0)
    _require(a.eq(b).all().all(), season, "detailed credit projection differs from native Down counts")

    attempt = p[["complete_pass", "incomplete_pass", "interception"]].eq(1).any(axis=1)
    pbp = p.loc[p.player_id.notna()].copy()
    pbp["attempts"] = attempt.loc[pbp.index].astype(int)
    pbp["completions"] = pbp.complete_pass.fillna(0)
    pbp["passing_interceptions"] = pbp.interception.fillna(0)
    pbp["passing_yards"] = pbp.passing_yards.fillna(0)
    pbp["passing_tds"] = pbp.pass_touchdown.fillna(0)
    pbp["sacks_suffered"] = pbp.sack.fillna(0)
    comparison = native.merge(pbp[[*KEYS, *COUNTS]], on=KEYS, how="outer", suffixes=("_credit", "_pbp"))
    wrong = pd.Series(False, index=comparison.index)
    for field in COUNTS:
        wrong |= comparison[field + "_credit"].fillna(0).ne(comparison[field + "_pbp"].fillna(0))
    affected = comparison.loc[wrong, KEYS].merge(p[["game_id", "play_id", "split_value"]], on=["game_id", "play_id"])
    affected = affected.loc[affected.split_value.isin(allowed)]
    bad_keys = set(zip(affected.player_id, affected.split_value))

    modeled = p.loc[p.play_type.isin(["pass", "qb_spike"])].copy()
    # Native exports can contain an unidentified-player aggregate. Validate its
    # model inputs too, even though it can never become a public player row.
    model_groups = modeled.groupby(["player_id", "split_value"], dropna=False)
    model_epa = model_groups.qb_epa.sum()
    model_cpoe = model_groups.cpoe.mean()
    # Native values are total EPA and mean modeled CPOE, not canonical rates.
    for field, expected in (("passing_epa", model_epa), ("passing_cpoe", model_cpoe)):
        values = raw.set_index(["player_id", "split_value"])[field]
        want = expected.reindex(values.index)
        _require(np.isclose(values.to_numpy(dtype=float, na_value=np.nan),
                            want.to_numpy(dtype=float, na_value=np.nan), equal_nan=True,
                            rtol=1e-9, atol=2e-5).all(), season, f"native {field} differs from PBP model population")

    output = rows.copy()
    source_keys = raw.set_index(["player_id", "split_value"])
    play_groups = {key: frame for key, frame in p.loc[p.player_id.notna()].groupby(["player_id", "split_value"])}
    issues, components = [], []
    for idx, row in output.iterrows():
        key = (row.player_id, str(row.split_value))
        original = source_keys.loc[key]
        group = play_groups.get(key, p.iloc[:0])
        tries = group.loc[group[["complete_pass", "incomplete_pass", "interception"]].eq(1).any(axis=1)]
        models = group.loc[group.play_type.isin(["pass", "qb_spike"])]
        reasons = {}
        output.at[idx, "first_downs"] = int(original.passing_first_downs)
        for field in ("epa", "success_pct", "cpoe", "air_yards", "yac"):
            reason = None
            if key in bad_keys:
                reason = "Detailed passing credits and PBP player contributions disagree"
            elif field in ("epa", "success_pct") and row.att == 0:
                reason = "No passing attempts in this bucket"
            elif field == "epa":
                if models.empty or models.qb_epa.isna().any():
                    reason = "Incomplete modeled QB EPA coverage"
                else:
                    output.at[idx, field] = round(float(original.passing_epa) / row.att, 4)
            elif field == "success_pct":
                if len(tries) != row.att or tries.epa.isna().any():
                    reason = "Incomplete attempt EPA coverage"
                else:
                    output.at[idx, field] = round(100 * float(tries.epa.gt(0).sum()) / row.att, 1)
            elif field == "cpoe":
                if models.cpoe.notna().any():
                    output.at[idx, field] = round(float(original.passing_cpoe), 2)
                else:
                    reason = "No modeled CPOE observations"
            elif season < 2006:
                reason = "Air-yard decomposition is unsupported before 2006"
            elif field == "air_yards":
                if len(tries) != row.att or tries.air_yards.isna().any() or original.passing_air_yards != tries.air_yards.sum():
                    reason = "Incomplete or disagreeing attempt air-yard coverage"
                else:
                    output.at[idx, field] = int(original.passing_air_yards)
            elif field == "yac":
                completed = tries.loc[tries.complete_pass.eq(1)]
                if (len(completed) != row.cmp or completed.air_yards.isna().any()
                        or original.passing_yards_after_catch != original.passing_yards - completed.air_yards.sum()):
                    reason = "Incomplete or disagreeing completed-pass air-yard decomposition"
                else:
                    output.at[idx, field] = int(original.passing_yards_after_catch)
            if reason:
                output.at[idx, field] = None
                reasons[field] = reason
        if reasons:
            issues.append({"player_id": row.player_id, "split_value": str(row.split_value), "metrics": reasons})
        # Preserve sufficient statistics, not rounded rate * attempts. A sack-only
        # row has undefined EPA/attempt but still contributes its verified EPA.
        # No CPOE observations means a known empty model subset (0/0), whereas
        # disagreeing attribution means unknown components that cannot be added.
        matches = key not in bad_keys
        components.append({"player_id": row.player_id, "split_value": str(row.split_value),
            "epa_sum": float(models.qb_epa.sum()) if matches and not models.empty and models.qb_epa.notna().all() else None,
            "successes": int(tries.epa.gt(0).sum()) if matches and len(tries) == row.att and tries.epa.notna().all() else None,
            "cpoe_sum": float(models.cpoe.sum()) if matches else None,
            "cpoe_count": int(models.cpoe.count()) if matches else None})
    return output, {"policy_version": 1, "source": "native nflfastR metrics with per-play PBP/credit population checks",
                    "attribution_mismatch_player_buckets": [dict(player_id=pid, split_value=value) for pid, value in sorted(bad_keys)],
                    "available_rows": {field: int(output[field].notna().sum()) for field in
                                       ("first_downs", "epa", "success_pct", "cpoe", "air_yards", "yac")},
                    "unavailable": issues, "aggregation": components}
