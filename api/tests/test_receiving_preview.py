"""Real copied DB / worker lifecycle with a deterministic offline export producer."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil

import duckdb
import pandas as pd
import pytest

from pipeline import receiving_preview as preview
from pipeline.receiving_splits import EXPORT_CONTRACT, VERSIONS
from pipeline.snapshots import CandidateError
import splits_builder


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.duckdb"
    plays = []
    for year in (2004, 2006, 2024):
        for index in range(28):
            row = {name: 0 for name in (
                "score_differential", "shotgun", "first_down", "qb_hit", "no_huddle", "wp",
                "pass_touchdown", "air_yards", "yards_after_catch", "epa", "incomplete_pass",
                "interception", "two_point_attempt",
            )}
            row.update(receiver_player_id="receiver", defteam="BUF", season=year, season_type="REG",
                       down=index % 4 + 1, qtr=1, pass_length="short", pass_location="right",
                       yardline_100=40, posteam_type="home", roof="outdoors", surface="grass",
                       complete_pass=1, receiving_yards=10, success=1)
            plays.append(row)
    with duckdb.connect(str(path)) as conn:
        conn.register("input_plays", pd.DataFrame(plays))
        conn.execute("CREATE TABLE plays AS SELECT * FROM input_plays")
        splits_builder.ensure_table(conn)
        conn.execute("""INSERT INTO player_splits
            (player_id,season,category,split_dim,split_value,att,cmp,yards,td)
            VALUES ('receiver',2024,'receiving','down','1',7,7,60,0),
                   ('older',2023,'rushing','down','1',3,NULL,88,1)""")
    return path


@pytest.fixture
def fake_export(monkeypatch):
    def produce(rscript, library, output, seasons, run_id):
        fault = os.environ.get("PREVIEW_TEST_FAULT")
        if fault == "R_failure":
            (output / "R-job.log").write_text("fixture R failure")
            raise CandidateError("R export failed")
        manifest = {**VERSIONS, "seasons": seasons, "run_id": run_id,
                    "receiving_export": deepcopy(EXPORT_CONTRACT), "files": {},
                    "runtime": {"R": "4.6.1", "platform": "test fixture", "packages": dict(VERSIONS)}}
        for year in seasons:
            count = 0 if year in range(2003, 2009) else 7
            yac = 0 if year < 2006 else 50
            frame = pd.DataFrame([dict(player_id="receiver", season=year, season_type="REG",
                                       targets=count, receptions=7, receiving_yards=70,
                                       receiving_tds=0, receiving_yards_after_catch=yac,
                                       receiving_first_downs=7, receiving_epa=3.5,
                                       receiving_air_yards=count * 2,
                                       split_value=str(down)) for down in range(1, 5)])
            context = pd.DataFrame([dict(game_id="game", play_id=index, season=year,
                                        season_type="REG", two_point_attempt=0,
                                        receiver_player_id="receiver", down=index % 4 + 1,
                                        complete_pass=1, incomplete_pass=0, interception=0,
                                        epa=0.5, air_yards=2) for index in range(28)])
            if fault == "missing_air":
                context.loc[0, "air_yards"] = None
            if fault == "missing_player":
                frame["player_id"] = "unqualified"
            weekly = pd.DataFrame([dict(player_id="receiver", season=year, season_type="REG",
                                        targets=count * 4, receptions=28, receiving_yards=280, receiving_tds=0,
                                        receiving_yards_after_catch=yac * 4, receiving_first_downs=28,
                                        receiving_air_yards=count * 8)])
            if fault == "wrong_totals":
                weekly["receiving_yards"] = 281
            if fault == "missing_scope":
                weekly = weekly.drop(columns="season_type")
            if fault == "wrong_YAC" and year >= 2006:
                weekly["receiving_yards_after_catch"] += 1
            if fault == "wrong_first_downs":
                weekly["receiving_first_downs"] += 1
            if fault == "wrong_air":
                weekly["receiving_air_yards"] += 1
            for name, data in ((f"down-{year}.csv", frame), (f"weekly-{year}.csv", weekly),
                               (f"context-{year}.csv", context)):
                path = output / name
                data.to_csv(path, index=False)
                manifest["files"][name] = preview.file_sha256(path)
        if fault == "stale_run":
            manifest["run_id"] = "old-job"
        if fault == "wrong_versions":
            manifest["runtime"]["packages"]["nflreadr"] = "unknown"
        (output / "run.json").write_text(json.dumps(manifest))
        if fault == "changed_bytes":
            path = output / f"down-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
    monkeypatch.setattr(preview, "_run_export", produce)


def run(source, tmp_path):
    return preview.prepare_receiving_preview(source, tmp_path / "preview.duckdb", tmp_path / "exports",
                                             [2024, 2004], rscript=Path(sys.executable), library=tmp_path)


def test_real_worker_adds_preview_only_and_records_exact_source_and_manifest(source, tmp_path, fake_export, monkeypatch):
    before = preview.file_sha256(source)
    monkeypatch.setenv("NFL_DB_PATH", str(source))
    monkeypatch.setenv("NFL_DB_READ_ONLY", "1")
    report = run(source, tmp_path)
    assert preview.file_sha256(source) == before == report["source_sha256"]
    assert report["status"] == "preview_only"
    assert report["export_manifest_sha256"] == preview.file_sha256(tmp_path / "exports/run.json")
    assert report["seasons"]["2004"]["targets"] == "unavailable"
    assert report["seasons"]["2004"]["yac"] == "unavailable"
    assert report["seasons"]["2024"]["yac"] == "matched_weekly"
    with duckdb.connect(str(tmp_path / "preview.duckdb"), read_only=True) as conn:
        assert conn.execute("SELECT season,SUM(att),SUM(cmp),SUM(yards),SUM(td) FROM receiving_down_preview GROUP BY season ORDER BY season").fetchall() == [(2004, None, 28, 280, 0), (2024, 28, 28, 280, 0)]
        assert conn.execute("SELECT player_id,yards FROM player_splits ORDER BY player_id").fetchall() == [("older", 88), ("receiver", 60)]
        assert conn.execute("SELECT season,SUM(yac),SUM(first_downs) FROM receiving_down_preview GROUP BY season ORDER BY season").fetchall() == [(2004, None, 28), (2024, 200, 28)]
        assert conn.execute("SELECT DISTINCT season,epa,success_pct FROM receiving_down_preview ORDER BY season").fetchall() == [(2004, None, None), (2024, 0.5, 100.0)]
        assert conn.execute("SELECT season,SUM(air_yards) FROM receiving_down_preview GROUP BY season ORDER BY season").fetchall() == [(2004, None), (2024, 56)]
    assert not Path(str(tmp_path / "preview.duckdb") + ".wal").exists()


@pytest.mark.parametrize("fault", ["wrong_totals", "missing_player", "missing_scope", "changed_bytes", "stale_run", "wrong_versions", "wrong_YAC", "wrong_first_downs", "wrong_air"])
def test_failed_validation_removes_owned_candidate_preserves_original_and_exports(source, tmp_path, fake_export, monkeypatch, fault):
    monkeypatch.setenv("PREVIEW_TEST_FAULT", fault)
    before = preview.file_sha256(source)
    with pytest.raises(subprocess.CalledProcessError):
        run(source, tmp_path)
    assert preview.file_sha256(source) == before
    assert not (tmp_path / "preview.duckdb").exists()
    assert not (tmp_path / "preview.duckdb.wal").exists()
    assert (tmp_path / "exports/run.json").exists()


def test_R_failure_removes_candidate_keeps_failure_log(source, tmp_path, fake_export, monkeypatch):
    monkeypatch.setenv("PREVIEW_TEST_FAULT", "R_failure")
    before = preview.file_sha256(source)
    with pytest.raises(CandidateError, match="R export failed"):
        run(source, tmp_path)
    assert preview.file_sha256(source) == before
    assert not (tmp_path / "preview.duckdb").exists()
    assert (tmp_path / "exports/R-job.log").read_text() == "fixture R failure"


@pytest.mark.parametrize("name", ["preview.duckdb", "preview.duckdb.wal", "exports"])
def test_existing_paths_are_refused(source, tmp_path, fake_export, name):
    path = tmp_path / name
    path.write_bytes(b"keep")
    before = preview.file_sha256(source)
    with pytest.raises(FileExistsError):
        run(source, tmp_path)
    assert path.read_bytes() == b"keep"
    assert preview.file_sha256(source) == before


def test_source_alias_and_pending_writes_are_refused(source, tmp_path, fake_export):
    with pytest.raises(CandidateError, match="different paths"):
        preview.prepare_receiving_preview(source, source, tmp_path / "exports", [2024],
                                          rscript=Path(sys.executable), library=tmp_path)
    Path(str(source) + ".wal").write_bytes(b"pending")
    with pytest.raises(CandidateError, match="WAL"):
        run(source, tmp_path)
    assert not (tmp_path / "preview.duckdb").exists()
    assert not (tmp_path / "exports").exists()


def test_missing_R_setup_fails_before_creating_candidate(source, tmp_path):
    with pytest.raises(CandidateError, match="existing Rscript"):
        preview.prepare_receiving_preview(source, tmp_path / "preview.duckdb", tmp_path / "exports", [2024],
                                          rscript=tmp_path / "absent-R", library=tmp_path)
    assert not (tmp_path / "preview.duckdb").exists()


def test_interrupted_R_tree_is_stopped_and_waited_for(tmp_path, monkeypatch):
    calls = []
    class Interrupted:
        pid = 123456
        def wait(self):
            calls.append("wait")
            if calls == ["wait"]:
                raise KeyboardInterrupt()
            return 1
    monkeypatch.setattr(preview.subprocess, "Popen", lambda *args, **kwargs: Interrupted())
    if os.name == "nt":
        def stop(command, **kwargs):
            assert command == ["taskkill", "/PID", "123456", "/T", "/F"]
            calls.append("stop tree")
        monkeypatch.setattr(preview.subprocess, "run", stop)
    else:
        monkeypatch.setattr(preview.os, "killpg", lambda *args: calls.append("stop tree"))
    with pytest.raises(KeyboardInterrupt):
        preview._run_export(Path(sys.executable), tmp_path, tmp_path, [2024], "fixture")
    assert calls == ["wait", "stop tree", "wait"]


def test_worker_has_no_default_db_fallback(monkeypatch, tmp_path):
    from jobs.receiving_preview_worker import prepare
    monkeypatch.delenv("NFL_DB_PATH", raising=False)
    with pytest.raises(CandidateError, match="absolute NFL_DB_PATH"):
        prepare(tmp_path / "source", tmp_path, [2024], "fixture", "unknown")


def test_worker_refuses_source_path(source, tmp_path, monkeypatch):
    from jobs.receiving_preview_worker import prepare
    monkeypatch.setenv("NFL_DB_PATH", str(source))
    with pytest.raises(CandidateError, match="cannot write the source"):
        prepare(source, tmp_path, [2024], "fixture", preview.file_sha256(source))


def test_worker_refuses_changed_baseline_before_opening_it(source, tmp_path, monkeypatch):
    from jobs.receiving_preview_worker import prepare
    candidate = tmp_path / "preview.duckdb"
    shutil.copyfile(source, candidate)
    baseline = preview.file_sha256(candidate)
    candidate.write_bytes(candidate.read_bytes() + b"changed")
    monkeypatch.setenv("NFL_DB_PATH", str(candidate))
    with pytest.raises(CandidateError, match="baseline changed"):
        prepare(source, tmp_path, [2024], "fixture", baseline)


@pytest.mark.parametrize("table", ["receiving_down_preview", "receiving_preview_preparation"])
def test_receiving_preview_cannot_pass_full_snapshot_gate(table):
    from pipeline.validation import SnapshotValidationError, validate_snapshot
    with duckdb.connect(":memory:") as conn:
        conn.execute(f"CREATE TABLE {table} (fixture INTEGER)")
        with pytest.raises(SnapshotValidationError, match="not a publishable snapshot"):
            validate_snapshot(conn)


def test_2006_preview_keeps_YAC_and_first_downs_with_unknown_targets(source, tmp_path, fake_export):
    report = preview.prepare_receiving_preview(source, tmp_path / "preview.duckdb", tmp_path / "exports", [2006],
                                                rscript=Path(sys.executable), library=tmp_path)
    assert report["seasons"]["2006"]["targets"] == "unavailable"
    assert report["seasons"]["2006"]["yac"] == "matched_weekly"
    with duckdb.connect(str(tmp_path / "preview.duckdb"), read_only=True) as conn:
        assert conn.execute("SELECT SUM(att),SUM(yac),SUM(first_downs) FROM receiving_down_preview").fetchone() == (None, 200, 28)


def test_missing_target_air_yards_preserves_rates_and_reports_partial_coverage(source, tmp_path, fake_export, monkeypatch):
    monkeypatch.setenv("PREVIEW_TEST_FAULT", "missing_air")
    report = run(source, tmp_path)
    assert report["seasons"]["2024"]["air_yards"] == {
        "available_rows": 3, "unavailable_rows": 1, "players_matched_weekly": 0,
    }
    with duckdb.connect(str(tmp_path / "preview.duckdb"), read_only=True) as conn:
        assert conn.execute("SELECT air_yards,epa,success_pct,cmp,yards FROM receiving_down_preview WHERE season=2024 AND split_value='1'").fetchone() == (None, 0.5, 100.0, 7, 70)
