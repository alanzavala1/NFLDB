"""Create CSV-only passing count previews outside every serving/build path."""
import io
import json
import os
from pathlib import Path
import uuid

import pandas as pd

from pipeline.passing_down import CONTEXT, COUNTS, adapt_passing_down
from pipeline.receiving_core_collection import open_core_inputs
from pipeline.receiving_core_inputs import _same_rows
from pipeline.receiving_preview import _check_environment, file_sha256
from pipeline.receiving_splits import VERSIONS, read_export_bytes
from pipeline.r_runtime import run_r_export
from pipeline.source_results import SourceError


def _csv(output, manifest, name, season):
    return pd.read_csv(io.BytesIO(read_export_bytes(output, manifest, name, season=season)),
                       keep_default_na=False, na_values=[""],
                       dtype={"player_id": "string", "passer_player_id": "string", "split_value": "string"})


def validate_passing_export(output, inputs, season, request, policy):
    """Read only hash-bound exports and compare context/reference to typed inputs."""
    manifest = json.loads((output / "run.json").read_bytes())
    if (type(manifest.get("format_version")) is not int or manifest["format_version"] != 1
            or manifest.get("kind") != "passing_down_counts_preview"
            or type(manifest.get("season")) is not int or manifest["season"] != season
            or any(manifest.get(key) != value for key, value in VERSIONS.items())
            or manifest.get("R") != json.loads((output / "renv.lock").read_bytes())["R"]["Version"]
            or manifest.get("fresh_credits_match_capture") is not True
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
    reference = _csv(output, manifest, "weekly.csv", season)
    expected = weekly.data.loc[weekly.data.season_type.eq("REG") & weekly.data.game_id.isin(source.game_id)]
    expected = expected.groupby("player_id", as_index=False)[list(COUNTS)].sum()
    _same_rows(reference[["player_id", *COUNTS]], expected, ["player_id"], season)
    rows, report = adapt_passing_down(context=context, weekly=reference, season=season,
        **{name: _csv(output, manifest, name + ".csv", season) for name in ("whole", "classified", "excluded", "down")})
    report.update(core_revision=inputs.revision(), source_run_sha256=request["source_run_sha256"],
                  export_manifest_sha256=file_sha256(output / "run.json"), producer_sha256=policy["producer.R"])
    return rows, report


def prepare_passing_preview(core_inputs: Path, output: Path, season: int, *, rscript: Path, library: Path, log=print):
    """Own a new output directory; retain failed logs and never open a source DB."""
    os.environ.setdefault("NFL_TEST_MODE", "1")
    if type(season) is not int or season < 1999:
        raise ValueError("Provide one integer season from 1999 onward")
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
    log(f"Exporting passing counts for {season}; log: {output / 'R-job.log'}")
    run_r_export([str(rscript), "--vanilla", str(output / "producer.R"), str(output)],
                 cwd=api, env=env, logfile=output / "R-job.log")
    rows, report = validate_passing_export(output, inputs, season, request, policy)
    rows.to_csv(output / "canonical-down.csv", index=False)
    report["canonical_down_sha256"] = file_sha256(output / "canonical-down.csv")
    (output / "preview.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    log(f"Passing Down preview: {len(rows)} rows; CSV only, not accepted for publication")
    return report
