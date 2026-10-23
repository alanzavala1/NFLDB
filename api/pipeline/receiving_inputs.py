"""Revision-bound optional charting and shared definitions for an R preview run."""
from dataclasses import asdict
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.receiving_context_rules import export_definitions
from pipeline.receiving_dimensions import DIMENSIONS
from pipeline.receiving_splits import read_export_bytes
from pipeline.snapshots import CandidateError


FTN_COLUMNS = ["season", "game_id", "play_id", "is_play_action", "n_pass_rushers"]


def prepare_receiving_inputs(output: Path, seasons: list[int]) -> None:
    # The preview process never serves requests. Disable unrelated config's
    # schedule lookup before importing the existing vendor download owner.
    os.environ["NFL_TEST_MODE"] = "1"
    from pipeline.vendor_sources import FTN, fetch_vendor
    (output / "definitions.json").write_text(json.dumps(export_definitions(DIMENSIONS)), encoding="utf-8")
    feed = fetch_vendor(FTN, seasons)
    outcomes = {str(record.season): asdict(record) for record in feed.outcomes}
    for year, outcome in outcomes.items():
        outcome["url"] = FTN.url.format(season=int(year))
    for season in seasons:
        frame = feed.data.loc[feed.data.season.eq(season)].copy() if feed.data is not None else pd.DataFrame(columns=FTN_COLUMNS)
        if not frame.empty:
            validate_ftn(frame, season)
            frame["is_play_action"] = frame.is_play_action.astype("Int64")
        else:
            frame = pd.DataFrame(columns=FTN_COLUMNS)
        frame[FTN_COLUMNS].to_csv(output / f"ftn-{season}.csv", index=False)
    (output / "ftn-inputs.json").write_text(json.dumps(outcomes), encoding="utf-8")


def validate_ftn(frame: pd.DataFrame, season: int) -> None:
    if set(FTN_COLUMNS) - set(frame.columns):
        raise CandidateError("FTN input missing required charting fields")
    if (frame.season.isna().any() or not frame.season.eq(season).all()
            or frame[["game_id", "play_id"]].isna().any().any()
            or frame.duplicated(["game_id", "play_id"]).any()):
        raise CandidateError("FTN input has wrong season or duplicate/missing play identity")
    if not frame.is_play_action.dropna().isin([True, False, 0, 1]).all():
        raise CandidateError("FTN input has invalid play-action flag")
    try:
        ids = pd.to_numeric(frame.play_id, errors="raise").to_numpy(dtype=float)
        rushers = pd.to_numeric(frame.n_pass_rushers, errors="raise").dropna().to_numpy(dtype=float)
    except (TypeError, ValueError) as error:
        raise CandidateError("FTN input contains invalid numeric fields") from error
    if (not np.isfinite(ids).all() or not (ids == np.trunc(ids)).all()
            or not np.isfinite(rushers).all() or not (rushers == np.trunc(rushers)).all()):
        raise CandidateError("FTN play IDs/rush counts must be finite integers or missing rush counts")


def verify_receiving_inputs(directory: Path, manifest: dict, context: pd.DataFrame, season: int) -> dict:
    read_export_bytes(directory, manifest, "producer.R", season=season)
    read_export_bytes(directory, manifest, "environment.R", season=season)
    lock = json.loads(read_export_bytes(directory, manifest, "renv.lock", season=season))
    expected = {name: record["Version"] for name, record in lock["Packages"].items()}
    runtime = manifest.get("runtime", {})
    if runtime.get("R") != lock["R"]["Version"] or runtime.get("locked_packages") != expected:
        raise CandidateError("Receiving R runtime differs from bound dependency lock")
    definitions = json.loads(read_export_bytes(directory, manifest, "definitions.json", season=season))
    if definitions != export_definitions(DIMENSIONS):
        raise CandidateError("Receiving definitions differ from this builder")
    outcomes = json.loads(read_export_bytes(directory, manifest, "ftn-inputs.json", season=season))
    record = outcomes.get(str(season))
    if not isinstance(record, dict) or record.get("status") not in {"loaded", "unsupported", "not_found", "failed", "empty"}:
        raise CandidateError("Missing/invalid FTN outcome")
    if record.get("season") != season or record.get("source") != "ftn_charting":
        raise CandidateError("FTN outcome has wrong source/season")
    from pipeline.receiving_splits import read_export_csv
    frame = read_export_csv(directory, manifest, f"ftn-{season}.csv", season=season)
    validate_ftn(frame, season)
    if ((record["status"] == "loaded") != (len(frame) > 0)
            or record.get("rows") != len(frame)
            or (season < 2022 and record["status"] != "unsupported")
            or (season >= 2022 and record["status"] == "unsupported")):
        raise CandidateError("FTN outcome differs from bound charting rows/support")
    required = {"ftn_matched", "is_play_action", "n_pass_rushers"}
    if required - set(context.columns):
        raise CandidateError("Receiving context missing FTN join fields")
    joined = context.merge(frame.assign(expected_match=1), on=["season", "game_id", "play_id"],
                           how="left", validate="one_to_one", suffixes=("", "_expected"))
    if not joined.ftn_matched.eq(joined.expected_match.fillna(0)).all():
        raise CandidateError("FTN matched population differs from bound input")
    for field in ("is_play_action", "n_pass_rushers"):
        a, b = joined[field], joined[f"{field}_expected"]
        if not (a.eq(b).fillna(False) | (a.isna() & b.isna())).all():
            raise CandidateError("FTN context differs from bound charting input")
    return record
