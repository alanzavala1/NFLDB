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
from pipeline.receiving_dimensions import DIMENSIONS, context_split_values
from pipeline.receiving_context_rules import export_definitions
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
        definitions = output / "definitions.json"
        definitions.write_text(json.dumps(export_definitions(DIMENSIONS)))
        manifest["files"][definitions.name] = preview.file_sha256(definitions)
        producer = output / "producer.R"
        producer.write_text("# deterministic test export producer")
        manifest["files"][producer.name] = preview.file_sha256(producer)
        charting_outcomes = {}
        for year in seasons:
            context = pd.DataFrame([dict(game_id="game", play_id=index, season=year,
                                        season_type="REG", two_point_attempt=0,
                                        receiver_player_id="receiver", down=index % 4 + 1,
                                        qtr=1 if index < 24 else 5,
                                        posteam_type="home" if index < 24 else "away",
                                        shotgun=1 if index < 24 else 0,
                                        yardline_100=75 if index < 24 else 20,
                                        score_differential=7 if index < 20 else 0 if index < 24 else -3,
                                        no_huddle=0 if index < 24 else 1,
                                        wp=0.5 if index < 24 else 0.99,
                                        roof="outdoors", surface="grass", defteam="BUF",
                                        pass_length="short" if index < 24 else "deep",
                                        pass_location="right" if index < 24 else "left",
                                        qb_hit=0 if index < 24 else 1,
                                        is_play_action=(0 if index < 24 else 1) if year >= 2022 else None,
                                        n_pass_rushers=(4 if index < 24 else 5) if year >= 2022 else None,
                                        ftn_matched=int(year >= 2022),
                                        complete_pass=1, incomplete_pass=0, interception=0,
                                        epa=0.5, air_yards=2) for index in range(28)])
            if fault == "missing_air":
                context.loc[0, "air_yards"] = None
            if fault == "partial_context":
                context.loc[24:, "yardline_100"] = None
            if fault == "unavailable_context":
                context["yardline_100"] = float("nan")
            if fault == "partial_game_script_context":
                context.loc[24:, "score_differential"] = None
            if fault == "unavailable_game_script_context":
                context["score_differential"] = float("nan")
            if fault == "partial_no_huddle_context":
                context.loc[24:, "no_huddle"] = None
            if fault == "unavailable_no_huddle_context":
                context["no_huddle"] = float("nan")
            if fault == "partial_depth":
                context.loc[24:, "pass_length"] = None
            if fault == "unavailable_depth":
                context["pass_length"] = None
            if fault == "unknown_surface":
                context.loc[24:, "surface"] = "unreviewed material"
            if year >= 2022 and fault in ("charting_gap", "charting_unavailable"):
                selected = context.index >= (24 if fault == "charting_gap" else 0)
                context.loc[selected, ["is_play_action", "n_pass_rushers"]] = None
                context.loc[selected, "ftn_matched"] = 0
            if year >= 2022 and fault == "rush_outlier":
                context.loc[24:, "n_pass_rushers"] = 45
            ftn = context[["season", "game_id", "play_id", "is_play_action", "n_pass_rushers"]].copy() if year >= 2022 else pd.DataFrame(columns=["season", "game_id", "play_id", "is_play_action", "n_pass_rushers"])
            if year >= 2022 and fault in ("charting_gap", "charting_unavailable"):
                ftn = ftn.loc[context.ftn_matched.eq(1)]
            charting_outcomes[str(year)] = {"source": "ftn_charting", "season": year,
                                             "status": "loaded" if year >= 2022 else "unsupported", "rows": len(ftn)}
            if year >= 2022 and fault == "charting_unavailable":
                charting_outcomes[str(year)]["status"] = "not_found"
            if year >= 2022 and fault == "ftn_join_mismatch":
                ftn.loc[0, "is_play_action"] = 1
            if year >= 2022 and fault == "duplicate_ftn":
                ftn = pd.concat([ftn, ftn.iloc[[0]]], ignore_index=True)
            credits = pd.DataFrame([dict(
                player_id="receiver", season=year, season_type="REG",
                targets=0 if year in range(2003, 2009) else 1,
                receptions=1, receiving_yards=10, receiving_tds=0,
                receiving_yards_after_catch=0 if year < 2006 else (8 if index in (2, 3, 24, 25) else 7),
                receiving_first_downs=1, receiving_epa=0.5,
                receiving_air_yards=0 if year in range(2003, 2009) else 2,
            ) for index in range(28)])
            def summarize(keep):
                return credits.loc[keep].groupby(["player_id", "season", "season_type"], as_index=False).sum()
            weekly = summarize(credits.index >= 0).assign(week=1)
            if fault == "self_consistent_wrong_total":
                credits.loc[0, "receiving_yards"] += 1
            overall = summarize(credits.index >= 0)
            exports = {f"context-{year}.csv": context, f"overall-{year}.csv": overall,
                       f"weekly-{year}.csv": weekly, f"ftn-{year}.csv": ftn}
            for dimension, buckets in DIMENSIONS.items():
                labels = context_split_values(context, dimension, year)
                membership = context[["game_id", "play_id"]].assign(split_value=labels)
                classified = summarize(labels.notna())
                excluded = summarize(labels.isna())
                parts = [summarize(labels.eq(bucket).fillna(False)).assign(split_value=bucket)
                         for bucket in buckets if labels.eq(bucket).any()]
                frame = pd.concat(parts, ignore_index=True) if parts else overall.iloc[:0].assign(split_value=pd.Series(dtype="string"))
                if fault == f"wrong_{dimension}" or (dimension == "down" and fault == "wrong_partition"):
                    if frame.empty:
                        frame = overall.iloc[:1].assign(split_value=buckets[0])
                    frame.loc[0, "receiving_yards"] += 1
                if dimension == "down":
                    if fault == "missing_player":
                        frame["player_id"] = "unqualified"
                    if fault == "wrong_membership":
                        membership.loc[0, "split_value"] = "2"
                    if fault == "duplicate_membership":
                        membership = pd.concat([membership, membership.iloc[[0]]], ignore_index=True)
                    if fault == "wrong_classified":
                        classified.loc[0, "receiving_yards"] += 1
                    if fault == "wrong_excluded":
                        excluded = overall.copy()
                    if fault == "empty_buckets":
                        frame = frame.iloc[:0]
                exports.update({f"{dimension}-{year}.csv": frame,
                                f"membership-{dimension}-{year}.csv": membership,
                                f"classified-{dimension}-{year}.csv": classified,
                                f"excluded-{dimension}-{year}.csv": excluded})
            if fault == "wrong_totals":
                weekly["receiving_yards"] = 281
            if fault == "missing_scope":
                exports[f"weekly-{year}.csv"] = weekly.drop(columns="season_type")
            if fault == "wrong_YAC" and year >= 2006:
                weekly["receiving_yards_after_catch"] += 1
            if fault == "wrong_first_downs":
                weekly["receiving_first_downs"] += 1
            if fault == "wrong_air":
                weekly["receiving_air_yards"] += 1
            if fault == "duplicate_weekly":
                exports[f"weekly-{year}.csv"] = pd.concat([weekly, weekly], ignore_index=True)
            for name, data in exports.items():
                path = output / name
                data.to_csv(path, index=False)
                manifest["files"][name] = preview.file_sha256(path)
            if fault == "missing_partition_hash":
                manifest["files"].pop(f"classified-down-{year}.csv")
        charting_path = output / "ftn-inputs.json"
        charting_path.write_text(json.dumps(charting_outcomes))
        manifest["files"][charting_path.name] = preview.file_sha256(charting_path)
        if fault == "stale_run":
            manifest["run_id"] = "old-job"
        if fault == "wrong_versions":
            manifest["runtime"]["packages"]["nflreadr"] = "unknown"
        (output / "run.json").write_text(json.dumps(manifest))
        if fault == "changed_bytes":
            path = output / f"down-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "changed_quarter_bytes":
            path = output / f"quarter-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "missing_quarter_export":
            (output / f"quarter-{seasons[0]}.csv").unlink()
        if fault == "changed_home_away_bytes":
            path = output / f"home_away-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "missing_home_away_export":
            (output / f"home_away-{seasons[0]}.csv").unlink()
        if fault == "changed_shotgun_bytes":
            path = output / f"shotgun-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "missing_shotgun_export":
            (output / f"shotgun-{seasons[0]}.csv").unlink()
        if fault == "changed_field_zone_bytes":
            path = output / f"field_zone-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "missing_field_zone_export":
            (output / f"field_zone-{seasons[0]}.csv").unlink()
        if fault == "changed_membership_bytes":
            path = output / f"membership-down-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "changed_reference_bytes":
            path = output / f"classified-down-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "missing_reference_export":
            (output / f"excluded-down-{seasons[0]}.csv").unlink()
        if fault == "missing_overall_export":
            (output / f"overall-{seasons[0]}.csv").unlink()
        if fault == "changed_game_script_bytes":
            path = output / f"game_script-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "missing_game_script_export":
            (output / f"game_script-{seasons[0]}.csv").unlink()
        if fault == "changed_no_huddle_bytes":
            path = output / f"no_huddle-{seasons[0]}.csv"
            path.write_bytes(path.read_bytes() + b"\n")
        if fault == "missing_no_huddle_export":
            (output / f"no_huddle-{seasons[0]}.csv").unlink()
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
    assert report["seasons"]["2004"]["down"]["targets"] == "unavailable"
    assert report["seasons"]["2004"]["down"]["yac"] == "unavailable"
    assert report["seasons"]["2024"]["down"]["yac"] == "matched_classified"
    assert report["format_version"] == 3
    assert report["whole_references"]["2024"]["production_matches_weekly"]
    assert report["seasons"]["2024"]["down"]["coverage"]["status"] == "complete"
    assert report["seasons"]["2024"]["down"]["coverage"]["plays"] == {
        "overall": 28, "classified": 28, "excluded": 0,
    }
    assert report["seasons"]["2024"]["quarter"]["production_matches_classified"]
    assert report["seasons"]["2024"]["home_away"]["production_matches_classified"]
    assert report["seasons"]["2024"]["shotgun"]["production_matches_classified"]
    assert report["seasons"]["2024"]["field_zone"]["production_matches_classified"]
    assert report["seasons"]["2024"]["game_script"]["coverage"]["status"] == "complete"
    assert report["seasons"]["2024"]["no_huddle"]["coverage"]["status"] == "complete"
    with duckdb.connect(str(tmp_path / "preview.duckdb"), read_only=True) as conn:
        assert conn.execute("SELECT season,SUM(att),SUM(cmp),SUM(yards),SUM(td) FROM receiving_down_preview GROUP BY season ORDER BY season").fetchall() == [(2004, None, 28, 280, 0), (2024, 28, 28, 280, 0)]
        assert conn.execute("SELECT player_id,yards FROM player_splits ORDER BY player_id").fetchall() == [("older", 88), ("receiver", 60)]
        assert conn.execute("SELECT season,SUM(yac),SUM(first_downs) FROM receiving_down_preview GROUP BY season ORDER BY season").fetchall() == [(2004, None, 28), (2024, 200, 28)]
        assert conn.execute("SELECT DISTINCT season,epa,success_pct FROM receiving_down_preview ORDER BY season").fetchall() == [(2004, None, None), (2024, 0.5, 100.0)]
        assert conn.execute("SELECT season,SUM(air_yards) FROM receiving_down_preview GROUP BY season ORDER BY season").fetchall() == [(2004, None), (2024, 56)]
        assert conn.execute("SELECT split_value,sort_order,att,cmp,yards,epa,success_pct FROM receiving_quarter_preview WHERE season=2024 ORDER BY sort_order").fetchall() == [("1", 1, 24, 24, 240, 0.5, 100.0), ("OT", 5, 4, 4, 40, 0.5, 100.0)]
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(yac) FROM receiving_quarter_preview WHERE season=2004").fetchone() == (None, 28, 280, None)
        assert conn.execute("SELECT split_value,sort_order,att,cmp,yards,epa FROM receiving_home_away_preview WHERE season=2024 ORDER BY sort_order").fetchall() == [("home", 1, 24, 24, 240, 0.5), ("away", 2, 4, 4, 40, 0.5)]
        assert conn.execute("SELECT split_value,sort_order,att,cmp,yards,epa FROM receiving_shotgun_preview WHERE season=2024 ORDER BY sort_order").fetchall() == [("shotgun", 1, 24, 24, 240, 0.5), ("under_center", 2, 4, 4, 40, 0.5)]
        assert conn.execute("SELECT split_value,sort_order,att,cmp,yards,epa FROM receiving_field_zone_preview WHERE season=2024 ORDER BY sort_order").fetchall() == [("own_territory", 1, 24, 24, 240, 0.5), ("red_zone", 3, 4, 4, 40, 0.5)]
        assert conn.execute("SELECT split_value,sort_order,att,cmp,yards,epa FROM receiving_game_script_preview WHERE season=2024 ORDER BY sort_order").fetchall() == [("leading", 1, 20, 20, 200, 0.5), ("tied", 2, 4, 4, 40, 0.5), ("trailing", 3, 4, 4, 40, 0.5)]
        assert conn.execute("SELECT split_value,sort_order,att,cmp,yards,epa FROM receiving_no_huddle_preview WHERE season=2024 ORDER BY sort_order").fetchall() == [("huddle", 1, 24, 24, 240, 0.5), ("no_huddle", 2, 4, 4, 40, 0.5)]
    assert not Path(str(tmp_path / "preview.duckdb") + ".wal").exists()


@pytest.mark.parametrize("fault", [
    'wrong_totals',
    'self_consistent_wrong_total',
    'wrong_membership',
    'duplicate_membership',
    'wrong_classified',
    'wrong_excluded',
    'empty_buckets',
    'missing_partition_hash',
    'changed_membership_bytes',
    'changed_reference_bytes',
    'missing_reference_export',
    'missing_overall_export',
    'duplicate_weekly',
    'missing_player',
    'missing_scope',
    'changed_bytes',
    'stale_run',
    'wrong_versions',
    'wrong_YAC',
    'wrong_first_downs',
    'wrong_air',
    'wrong_quarter',
    'changed_quarter_bytes',
    'missing_quarter_export',
    'wrong_home_away',
    'changed_home_away_bytes',
    'missing_home_away_export',
    'wrong_shotgun',
    'changed_shotgun_bytes',
    'missing_shotgun_export',
    'wrong_field_zone',
    'changed_field_zone_bytes',
    'missing_field_zone_export',
    'wrong_game_script',
    'changed_game_script_bytes',
    'missing_game_script_export',
    'wrong_no_huddle',
    'wrong_game_state',
    'wrong_roof',
    'wrong_surface',
    'wrong_opponent',
    'wrong_opp_division',
    'wrong_target_depth',
    'wrong_target_direction',
    'wrong_pressure',
    'wrong_play_action',
    'wrong_blitz',
    'ftn_join_mismatch',
    'duplicate_ftn',
    'changed_no_huddle_bytes',
    'missing_no_huddle_export',
])
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
    monkeypatch.setattr("pipeline.receiving_inputs.prepare_receiving_inputs", lambda *args: None)
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


def test_r_invocation_freezes_source_bytes_before_starting(tmp_path, monkeypatch):
    api = tmp_path / "api"
    (api / "pipeline").mkdir(parents=True)
    (api / "experiments").mkdir()
    output = tmp_path / "output"
    output.mkdir()
    source = api / "experiments/upstream_receiving_splits.R"
    source.write_text("print('original invocation')")
    original = source.read_bytes()
    monkeypatch.setattr(preview, "__file__", str(api / "pipeline/receiving_preview.py"))
    monkeypatch.setattr("pipeline.receiving_inputs.prepare_receiving_inputs", lambda *args: None)
    class Done:
        def wait(self):
            return 0
    def start(command, **kwargs):
        assert Path(command[2]) == output / "producer.R"
        source.write_text("print('edited during build')")
        assert (output / "producer.R").read_bytes() == original
        return Done()
    monkeypatch.setattr(preview.subprocess, "Popen", start)
    preview._run_export(Path(sys.executable), tmp_path, output, [2024], "fixture")
    assert (output / "producer.R").read_bytes() == original


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


@pytest.mark.parametrize("table", [
    *(f"receiving_{dim}_preview" for dim in DIMENSIONS),
    'receiving_future_preview',
    'receiving_preview_preparation',
])
def test_receiving_preview_cannot_pass_full_snapshot_gate(table):
    from pipeline.validation import SnapshotValidationError, validate_snapshot
    with duckdb.connect(":memory:") as conn:
        conn.execute(f"CREATE TABLE {table} (fixture INTEGER)")
        with pytest.raises(SnapshotValidationError, match="not a publishable snapshot"):
            validate_snapshot(conn)


def test_2006_preview_keeps_YAC_and_first_downs_with_unknown_targets(source, tmp_path, fake_export):
    report = preview.prepare_receiving_preview(source, tmp_path / "preview.duckdb", tmp_path / "exports", [2006],
                                                rscript=Path(sys.executable), library=tmp_path)
    assert report["seasons"]["2006"]["down"]["targets"] == "unavailable"
    assert report["seasons"]["2006"]["down"]["yac"] == "matched_classified"
    with duckdb.connect(str(tmp_path / "preview.duckdb"), read_only=True) as conn:
        assert conn.execute("SELECT SUM(att),SUM(yac),SUM(first_downs) FROM receiving_down_preview").fetchone() == (None, 200, 28)


def test_missing_target_air_yards_preserves_rates_and_reports_partial_coverage(source, tmp_path, fake_export, monkeypatch):
    monkeypatch.setenv("PREVIEW_TEST_FAULT", "missing_air")
    report = run(source, tmp_path)
    assert report["seasons"]["2024"]["down"]["air_yards"] == {
        "available_rows": 3, "unavailable_rows": 1, "players_matched_classified": 0,
    }
    with duckdb.connect(str(tmp_path / "preview.duckdb"), read_only=True) as conn:
        assert conn.execute("SELECT air_yards,epa,success_pct,cmp,yards FROM receiving_down_preview WHERE season=2024 AND split_value='1'").fetchone() == (None, 0.5, 100.0, 7, 70)


@pytest.mark.parametrize("fault,dimension,covered,excluded,status", [
    ("partial_context", "field_zone", 24, 4, "partial"),
    ("unavailable_context", "field_zone", 0, 28, "unavailable"),
    ("partial_game_script_context", "game_script", 24, 4, "partial"),
    ("unavailable_game_script_context", "game_script", 0, 28, "unavailable"),
    ("partial_no_huddle_context", "no_huddle", 24, 4, "partial"),
    ("unavailable_no_huddle_context", "no_huddle", 0, 28, "unavailable"),
    ("partial_depth", "target_depth", 24, 4, "partial"),
    ("unavailable_depth", "target_depth", 0, 28, "unavailable"),
    ("unknown_surface", "surface", 24, 4, "partial"),
    ("charting_gap", "play_action", 24, 4, "partial"),
    ("charting_unavailable", "play_action", 0, 28, "unavailable"),
    ("rush_outlier", "blitz", 24, 4, "partial"),
])
def test_missing_context_only_limits_its_view_and_retains_global_receiving_production(
    source, tmp_path, fake_export, monkeypatch, fault, dimension, covered, excluded, status,
):
    monkeypatch.setenv("PREVIEW_TEST_FAULT", fault)
    before = preview.file_sha256(source)
    report = run(source, tmp_path)
    assert preview.file_sha256(source) == before
    assert report["whole_references"]["2024"]["production_matches_weekly"]
    field = report["seasons"]["2024"][dimension]
    coverage = field["coverage"]
    assert coverage["status"] == status
    assert coverage["plays"] == {"overall": 28, "classified": covered, "excluded": excluded}
    assert coverage["qualified_production"]["classified"]["receiving_yards"] == covered * 10
    assert coverage["qualified_production"]["excluded"]["receiving_yards"] == excluded * 10
    assert coverage["qualified_production"]["overall"]["receiving_yards"] == 280
    assert field["represented_players"] == int(covered > 0)
    assert coverage["qualified_without_classified_production"] == ([] if covered else ["receiver"])
    with duckdb.connect(str(tmp_path / "preview.duckdb"), read_only=True) as conn:
        assert conn.execute("SELECT SUM(cmp),SUM(yards) FROM receiving_down_preview WHERE season=2024").fetchone() == (28, 280)
        assert conn.execute(f"SELECT SUM(cmp),SUM(yards) FROM receiving_{dimension}_preview WHERE season=2024").fetchone() == ((covered, covered * 10) if covered else (None, None))
        assert conn.execute("SELECT att FROM receiving_down_preview WHERE season=2004").df().att.isna().all()
        assert conn.execute("SELECT yards FROM player_splits WHERE player_id='receiver'").fetchone() == (60,)
    assert not Path(str(tmp_path / "preview.duckdb") + ".wal").exists()
