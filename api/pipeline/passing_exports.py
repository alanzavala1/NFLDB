"""One source-bound acceptance path for all native passing split exports."""
from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from pipeline.passing_dimensions import DIMENSIONS, RECEIVING_NAMES, context_split_values
from pipeline.passing_down import COUNTS, _require, adapt_passing_partition
from pipeline.passing_metrics import apply_passing_metrics, verify_passing_first_downs
from pipeline.passing_preview import _csv, validated_passing_inputs
from pipeline.passing_summary import prepare_passing_summary
from pipeline.receiving_context_rules import POLICIES
from pipeline.receiving_core_inputs import _same_rows
from pipeline.receiving_inputs import verify_receiving_inputs
from pipeline.receiving_preview import file_sha256
from pipeline.receiving_splits import read_export_csv


@dataclass
class PassingSeason:
    rows: dict[str, pd.DataFrame]
    report: dict


def passing_policy():
    api = Path(__file__).resolve().parents[1]
    return {name: file_sha256(path) for name, path in (
        ("producer.R", api / "experiments/upstream_passing_down.R"),
        ("environment.R", api / "r/environment.R"), ("renv.lock", api / "r/renv.lock"))}


def load_passing_season(output: Path, inputs, season: int, *, require_all=True) -> PassingSeason:
    """No R, network or writes: replay native rows against the bound core capture."""
    request = json.loads((output / "request.json").read_bytes())
    dimensions = request.get("dimensions")
    _require(isinstance(dimensions, list) and bool(dimensions)
             and len(set(dimensions)) == len(dimensions) and all(name in DIMENSIONS for name in dimensions),
             season, "invalid passing dimensions")
    _require(not require_all or dimensions == list(DIMENSIONS), season, "build requires every passing dimension")
    directory, capture, source_sha = inputs.receiving_run(season)
    _require(request.get("season") == season and isinstance(request.get("source_directory"), str)
             and bool(request["source_directory"])
             and request.get("source_run_sha256") == source_sha
             and isinstance(request.get("core_revision"), str) and bool(request["core_revision"]),
             season, "passing export uses a different core capture")
    # Data identity is the leaf manifest and consumed values. The outer index
    # and physical paths may change when another season refreshes or CI restores
    # the same immutable capture into a different workspace.
    policy = passing_policy()
    manifest, _, context, credits, weekly, reference = validated_passing_inputs(
        output, inputs, season, request, policy, version=3, kind="passing_splits_preview")
    _require(manifest.get("dimensions") == dimensions, season, "passing completion dimensions changed")
    receiving_context = read_export_csv(directory, capture, f"context-{season}.csv", season=season)
    charting = verify_receiving_inputs(directory, capture, receiving_context, season)
    extras = [name for name in receiving_context if name not in context]
    context = context.merge(receiving_context[["game_id", "play_id", *extras]],
                            on=["game_id", "play_id"], how="outer", validate="one_to_one")
    whole = _csv(output, manifest, "whole.csv", season)
    rows, views, admission = {}, {}, None
    for dimension in dimensions:
        frames = {name: _csv(output, manifest, f"{name}-{dimension}.csv", season)
                  for name in ("classified", "excluded")}
        frames.update(whole=whole, down=_csv(output, manifest, f"{dimension}.csv", season))
        labels = context_split_values(context, dimension, season)
        expected = context[["game_id", "play_id"]].assign(split_value=labels)
        membership = _csv(output, manifest, f"membership-{dimension}.csv", season)
        _same_rows(membership, expected, ["game_id", "play_id"], season)
        canonical, counts = adapt_passing_partition(context=context, weekly=reference, season=season,
                                                   dimension=dimension, **frames)
        verify_passing_first_downs(frames, weekly, season)
        canonical, metrics = apply_passing_metrics(canonical, frames["down"], context, credits,
                                                   season, dimension=dimension)
        rows[dimension] = canonical
        if admission is None:
            admission = {name: counts[name] for name in ("qualified_players", "qualifying_plays", "qualification_sql_sha256")}
        _require(counts["qualifying_plays"] == admission["qualifying_plays"], season, "passing admission differs across views")
        included = int(labels.notna().sum())
        excluded = frames["excluded"].loc[frames["excluded"].player_id.isin(admission["qualifying_plays"])]
        fields = [*COUNTS, "passing_first_downs"]
        by_player = excluded.set_index("player_id")[fields].reindex(admission["qualifying_plays"], fill_value=0)
        definition = {"pass_depth": "Recorded play-level pass depth shared by all credited passers; not separate labels for multiple throws.",
                      "pass_location": "Recorded play-level pass direction shared by all credited passers; not separate labels for multiple throws."}.get(
                          dimension, POLICIES.get(RECEIVING_NAMES.get(dimension, dimension),
                                                  "Recorded play context; missing values excluded."))
        views[dimension] = {
            "coverage": {"status": "unavailable" if not included else "complete" if included == len(context) else "partial",
                         "reason": None if included == len(context) else "Some supplied plays lack supported context for this view",
                         "definition": definition, "plays": counts["context"]},
            "qualified_excluded_counts": counts["qualified_excluded_counts"],
            "excluded_by_player": {player: {field: int(value) for field, value in values.items()}
                                   for player, values in by_player.iterrows()},
            "metric_availability": metrics,
        }
        if dimension in ("play_action", "blitz"):
            views[dimension]["coverage"]["charting_source"] = charting
    identified = whole.loc[whole.player_id.isin(admission["qualifying_plays"])]
    totals = [{"player_id": record["player_id"], **{field: int(record[field]) for field in
               (*COUNTS, "passing_first_downs")}} for record in identified.to_dict(orient="records")]
    report = {"format_version": 1, "status": "offline_integration_only", "publication_ready": False,
              "season": season, "source": "nflfastR native passing calculator", "core_revision": inputs.revision(),
              "export_core_revision": request["core_revision"],
              "source_run_sha256": source_sha, "export_manifest_sha256": file_sha256(output / "run.json"),
              "policy": policy, "dimensions": views, "admission": admission,
              "whole_counts": sorted(totals, key=lambda record: record["player_id"]),
              "summary": prepare_passing_summary(whole, context, credits, season, admission["qualifying_plays"]),
              "rows": sum(len(frame) for frame in rows.values()),
              "count_checks": "whole/weekly, buckets/classified, classified+excluded/whole: exact before admission",
              "first_down_checks": "whole/weekly and all partition counts: exact before admission",
              "credit_match_scope": manifest.get("credit_match_scope")}
    return PassingSeason(rows, report)
