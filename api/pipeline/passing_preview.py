"""Create CSV-only passing previews outside every serving/build path."""
import io
import json
import os
from pathlib import Path
import uuid

import pandas as pd

from pipeline.passing_down import CONTEXT, COUNTS, adapt_passing_down
from pipeline.passing_metrics import METRIC_CONTEXT, apply_passing_metrics, verify_passing_first_downs
from pipeline.receiving_core_collection import open_core_inputs
from pipeline.receiving_core_inputs import _same_rows
from pipeline.receiving_preview import _check_environment, file_sha256
from pipeline.receiving_splits import VERSIONS, read_export_bytes, read_export_csv
from pipeline.r_runtime import run_r_export
from pipeline.source_results import SourceError


def _csv(output, manifest, name, season):
    return pd.read_csv(io.BytesIO(read_export_bytes(output, manifest, name, season=season)),
                       keep_default_na=False, na_values=[""],
                       dtype={"player_id": "string", "passer_player_id": "string", "gsis_player_id": "string", "split_value": "string"})


def validated_passing_inputs(output, inputs, season, request, policy, *, version=2, kind="passing_down_metrics_preview"):
    """Read only hash-bound exports and compare context/reference to typed inputs."""
    manifest = json.loads((output / "run.json").read_bytes())
    if (type(manifest.get("format_version")) is not int or manifest["format_version"] != version
            or manifest.get("kind") != kind
            or type(manifest.get("season")) is not int or manifest["season"] != season
            or any(manifest.get(key) != value for key, value in VERSIONS.items())
            or manifest.get("R") != json.loads((output / "renv.lock").read_bytes())["R"]["Version"]
            or manifest.get("fresh_credits_match_capture") is not True
            or manifest.get("credit_match_scope", "entire captured season") not in
                {"entire captured season", "supplied REG nonconversion game/play keys"}
            or manifest.get("source_run_sha256") != request["source_run_sha256"]):
        raise SourceError("passing_down_preview", season, "unsupported or unbound export completion")
    for name in ("producer.R", "environment.R", "renv.lock", "request.json", "credits.rds"):
        read_export_bytes(output, manifest, name, season=season)
    if (json.loads((output / "request.json").read_bytes()) != request
            or any(file_sha256(output / name) != digest for name, digest in policy.items())):
        raise SourceError("passing_down_preview", season, "preview request or frozen policy changed")
    plays, weekly = inputs.feeds([season])
    source = plays.data.loc[plays.data.season_type.eq("REG") & ~plays.data.two_point_attempt.eq(1)]
    context = _csv(output, manifest, "context.csv", season)
    _same_rows(context, source[list(CONTEXT)], ["game_id", "play_id"], season)
    metric_context = _csv(output, manifest, "metric-context.csv", season)
    # The ordinary loader intentionally stores float32 PBP. Compare at that
    # same precision, then validate model calculations with a rounding allowance.
    expected_context = source[list(METRIC_CONTEXT)].copy()
    for column in expected_context.select_dtypes(include=["float32"]):
        metric_context[column] = metric_context[column].astype("float32")
    _same_rows(metric_context, expected_context, ["game_id", "play_id"], season)
    credits = _csv(output, manifest, "metric-credits.csv", season)
    directory, captured_manifest, _ = inputs.receiving_run(season)
    captured_credits = read_export_csv(directory, captured_manifest, f"credits-{season}.csv", season=season)
    fields = ["game_id", "play_id", "gsis_player_id", "stat_id", "yards"]
    def credit_projection(frame):
        # Credits legitimately repeat: compare their multiplicity as well.
        return frame.groupby(fields, dropna=False).size().rename("records").reset_index()
    def consumed(frame):
        return frame.merge(source[["game_id", "play_id"]], on=["game_id", "play_id"], validate="many_to_one")
    # The native calculator consumes exactly this semi-join, not later games.
    # Older v2 exporters compared the entire season (a stronger check), and
    # remain readable as immutable historical evidence.
    _same_rows(credit_projection(consumed(credits)), credit_projection(consumed(captured_credits)), fields, season)
    reference = _csv(output, manifest, "weekly.csv", season)
    weekly_reference = weekly.data.loc[weekly.data.season_type.eq("REG") & weekly.data.game_id.isin(source.game_id)]
    expected = weekly_reference.groupby("player_id", as_index=False)[list(COUNTS)].sum()
    _same_rows(reference[["player_id", *COUNTS]], expected, ["player_id"], season)
    return manifest, context, metric_context, credits, weekly_reference, reference


def validate_passing_export(output, inputs, season, request, policy):
    """Replay immutable version-2 Down evidence using the shared input checks."""
    manifest, context, metric_context, credits, weekly_reference, reference = validated_passing_inputs(
        output, inputs, season, request, policy)
    frames = {name: _csv(output, manifest, name + ".csv", season) for name in ("whole", "classified", "excluded", "down")}
    rows, report = adapt_passing_down(context=context, weekly=reference, season=season, **frames)
    verify_passing_first_downs(frames, weekly_reference, season)
    rows, metrics = apply_passing_metrics(rows, frames["down"], metric_context, credits, season)
    report.pop("unavailable_metrics")
    report.update(scope="supplied REG nonconversion games; passing counts and verified metrics", metric_availability=metrics)
    report["first_down_checks"] = "whole/weekly, Down/classified, classified+excluded/whole: exact for all identified players"
    report.update(core_revision=inputs.revision(), source_run_sha256=request["source_run_sha256"],
                  credit_match_scope=manifest.get("credit_match_scope", "entire captured season"),
                  export_manifest_sha256=file_sha256(output / "run.json"), producer_sha256=policy["producer.R"])
    return rows, report


def prepare_passing_preview(core_inputs: Path, output: Path, season: int, *, rscript: Path, library: Path,
                            dimensions=None, log=print):
    """Own a new output directory; retain failed logs and never open a source DB."""
    os.environ.setdefault("NFL_TEST_MODE", "1")
    if type(season) is not int or season < 1999:
        raise ValueError("Provide one integer season from 1999 onward")
    if dimensions is not None:
        from pipeline.passing_dimensions import DIMENSIONS
        if (not isinstance(dimensions, (list, tuple)) or not dimensions or len(set(dimensions)) != len(dimensions)
                or any(dimension not in DIMENSIONS for dimension in dimensions)):
            raise ValueError("Provide distinct supported passing dimensions")
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    rscript, library = rscript.resolve(), library.resolve()
    if not rscript.is_file() or not library.is_dir():
        raise ValueError("Provide an existing Rscript executable and R library")
    inputs = open_core_inputs(core_inputs.resolve())
    inputs.feeds([season])  # Validate captured source/conversion hashes before creating output.
    source, _, source_sha = inputs.receiving_run(season)
    request = {"run_id": uuid.uuid4().hex, "season": season, "source_directory": str(source),
               "source_run_sha256": source_sha, "core_revision": inputs.revision()}
    if dimensions is not None:
        request["dimensions"] = list(dimensions)
    output.mkdir()
    api = Path(__file__).resolve().parents[1]
    for name, path in (("producer.R", api / "experiments/upstream_passing_down.R"),
                       ("environment.R", api / "r/environment.R"), ("renv.lock", api / "r/renv.lock")):
        with (output / name).open("xb") as stream:
            stream.write(path.read_bytes())
    (output / "request.json").write_text(json.dumps(request, sort_keys=True), encoding="utf-8")
    policy = {name: file_sha256(output / name) for name in ("producer.R", "environment.R", "renv.lock")}
    env = {**os.environ, "R_LIBS_USER": str(library), "NFL_RECEIVING_LIBRARY": str(library), "LC_ALL": "C"}
    _check_environment(rscript, library, output, env)
    log(f"Exporting passing counts and metrics for {season}; log: {output / 'R-job.log'}")
    run_r_export([str(rscript), "--vanilla", str(output / "producer.R"), str(output)],
                 cwd=api, env=env, logfile=output / "R-job.log")
    if dimensions is None:
        rows, report = validate_passing_export(output, inputs, season, request, policy)
        filename, digest_key = "canonical-down.csv", "canonical_down_sha256"
    else:
        from pipeline.passing_exports import load_passing_season
        prepared = load_passing_season(output, inputs, season, require_all=False)
        rows, report = pd.concat(list(prepared.rows.values()), ignore_index=True), prepared.report
        filename, digest_key = "canonical-splits.csv", "canonical_splits_sha256"
    rows.to_csv(output / filename, index=False)
    report[digest_key] = file_sha256(output / filename)
    (output / "preview.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    log(f"Passing preview: {len(rows)} rows; CSV only, not accepted for publication")
    return report
