"""Optional FTN inputs stay explicit, validated, and bound to consumed bytes."""
import json

import pandas as pd
import pytest

from pipeline.receiving_inputs import prepare_receiving_inputs, validate_ftn, verify_receiving_inputs
from pipeline.receiving_preview import file_sha256
from pipeline.snapshots import CandidateError
from pipeline.source_results import SourceOutcome, VendorFeed


def fixture():
    return pd.DataFrame([dict(season=2024, game_id="game", play_id=1,
                              is_play_action=False, n_pass_rushers=4)])


def prepare(tmp_path, monkeypatch, frame=None, outcome=None):
    feed = VendorFeed("ftn_charting", fixture() if frame is None else frame,
                      [outcome or SourceOutcome("ftn_charting", 2024, "loaded", 1)])
    monkeypatch.setattr("pipeline.vendor_sources.fetch_vendor", lambda *args: feed)
    prepare_receiving_inputs(tmp_path, [2024])
    (tmp_path / "producer.R").write_text("# frozen fixture producer")
    manifest = {"files": {p.name: file_sha256(p) for p in tmp_path.iterdir()}}
    context = fixture().assign(ftn_matched=1)
    return manifest, context


def test_known_false_charting_is_preserved_and_verified(tmp_path, monkeypatch):
    manifest, context = prepare(tmp_path, monkeypatch)
    record = verify_receiving_inputs(tmp_path, manifest, context, 2024)
    assert record["status"] == "loaded" and record["rows"] == 1
    assert "ftn_charting_2024.parquet" in record["url"]


def test_missing_optional_feed_is_recorded_not_converted_to_false(tmp_path, monkeypatch):
    missing = SourceOutcome("ftn_charting", 2024, "failed", 0, "TimeoutError")
    feed = VendorFeed("ftn_charting", None, [missing])
    monkeypatch.setattr("pipeline.vendor_sources.fetch_vendor", lambda *args: feed)
    prepare_receiving_inputs(tmp_path, [2024])
    (tmp_path / "producer.R").write_text("# frozen fixture producer")
    manifest = {"files": {p.name: file_sha256(p) for p in tmp_path.iterdir()}}
    context = fixture().assign(ftn_matched=0, is_play_action=float("nan"), n_pass_rushers=float("nan"))
    record = verify_receiving_inputs(tmp_path, manifest, context, 2024)
    assert record["status"] == "failed" and record["detail"] == "TimeoutError"
    assert pd.read_csv(tmp_path / "ftn-2024.csv").empty


@pytest.mark.parametrize("fault", ["duplicate", "year", "missing_key", "fraction", "flag"])
def test_malformed_charting_stops_the_build(fault):
    frame = fixture()
    if fault == "duplicate":
        frame = pd.concat([frame, frame])
    elif fault == "year":
        frame["season"] = 2023
    elif fault == "missing_key":
        frame["game_id"] = None
    elif fault == "fraction":
        frame["n_pass_rushers"] = 4.5
    else:
        frame["is_play_action"] = "unknown"
    with pytest.raises(CandidateError):
        validate_ftn(frame, 2024)


@pytest.mark.parametrize("fault", ["bytes", "definitions", "outcome", "joined_flag", "joined_match"])
def test_valid_hashes_alone_cannot_certify_wrong_sources_or_joined_context(tmp_path, monkeypatch, fault):
    manifest, context = prepare(tmp_path, monkeypatch)
    if fault == "bytes":
        with (tmp_path / "ftn-2024.csv").open("a") as stream:
            stream.write("\n")
    elif fault == "definitions":
        path = tmp_path / "definitions.json"
        data = json.loads(path.read_text())
        data["pressure_first_season"] = 1999
        path.write_text(json.dumps(data))
        manifest["files"][path.name] = file_sha256(path)
    elif fault == "outcome":
        path = tmp_path / "ftn-inputs.json"
        data = json.loads(path.read_text())
        data["2024"]["rows"] = 2
        path.write_text(json.dumps(data))
        manifest["files"][path.name] = file_sha256(path)
    elif fault == "joined_flag":
        context["is_play_action"] = True
    else:
        context["ftn_matched"] = 0
    with pytest.raises((CandidateError, RuntimeError)):
        verify_receiving_inputs(tmp_path, manifest, context, 2024)
