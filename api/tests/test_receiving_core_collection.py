"""Disjoint historical captures must compose without hiding a missing/changed year."""
import json
from pathlib import Path
import subprocess

import duckdb
import pytest

from pipeline import loading, snapshots
from pipeline.receiving_core_collection import assemble_core_inputs, open_core_inputs
from pipeline.receiving_core_inputs import ReceivingCoreInputs
from pipeline.receiving_preview import file_sha256
from pipeline.source_results import SourceError
from tests.test_receiving_core_inputs import bundle, CORE_WORKER


def copy_year(bundle: Path, destination: Path, year: int) -> Path:
    """Create a distinct captured season; keep calculator/converter policies equal."""
    destination.mkdir()
    original = json.loads((bundle / "run.json").read_text())
    exports = destination / "receiving"
    core = destination / "core"
    exports.mkdir()
    core.mkdir()
    rename = lambda text: text.replace("2024", str(year))
    for path in Path(original["source_directory"]).iterdir():
        if path.name != "run.json":
            (exports / rename(path.name)).write_bytes(path.read_bytes().replace(b"2024", str(year).encode()))
    parent = json.loads((Path(original["source_directory"]) / "run.json").read_text())
    parent["seasons"] = [year]
    parent["files"] = {path.name: file_sha256(path) for path in exports.iterdir()}
    (exports / "run.json").write_text(json.dumps(parent))
    for path in bundle.iterdir():
        if path.name not in ("run.json", "receiving-run.json"):
            (core / rename(path.name)).write_bytes(path.read_bytes().replace(b"2024", str(year).encode()))
    (core / "receiving-run.json").write_bytes((exports / "run.json").read_bytes())
    original["source_directory"] = str(exports)
    original["seasons"] = [year]
    original["tables"] = {rename(name): {**record, "source": rename(record["source"]),
                                          "source_sha256": parent["files"][rename(record["source"])]}
                          for name, record in original["tables"].items()}
    original["files"] = {path.name: file_sha256(path) for path in core.iterdir()}
    (core / "run.json").write_text(json.dumps(original))
    return core


@pytest.fixture
def two_years(bundle, tmp_path):
    return [copy_year(bundle, tmp_path / "history", 1999), bundle]


def test_compose_unsorted_runs_route_scope_and_bind_index(two_years, tmp_path):
    output = tmp_path / "collection"
    before = {path: file_sha256(path / "run.json") for path in two_years}
    inputs = assemble_core_inputs(list(reversed(two_years)), output)
    plays, weekly = open_core_inputs(output).load_feeds([2024], [1999, 2024])
    assert plays.loaded_seasons == [2024] and set(plays.data.season) == {2024}
    assert weekly.loaded_seasons == [1999, 2024] and len(weekly.data) == 6
    assert len(plays.data) == 4  # historical PBP was validated, not retained
    assert inputs.seasons == [1999, 2024]
    assert inputs.manifest["bundles"][0]["directory"] == str(two_years[0])
    assert "collection SHA256" in inputs.revision()
    assert {path: file_sha256(path / "run.json") for path in two_years} == before


def test_missing_middle_year_rejected_before_reading_any_season(two_years, tmp_path, monkeypatch):
    inputs = assemble_core_inputs(two_years, tmp_path / "collection")
    monkeypatch.setattr(ReceivingCoreInputs, "feeds", lambda *a: pytest.fail("missing range reached table reads"))
    with pytest.raises(SourceError, match="every requested season"):
        inputs.load_feeds([2024], [1999, 2000, 2024])


def test_ambiguous_season_and_duplicate_paths_refused_without_output(two_years, tmp_path):
    duplicate = copy_year(two_years[1], tmp_path / "duplicate", 2024)
    for number, paths in enumerate(([two_years[1], duplicate], [two_years[1]] * 2)):
        output = tmp_path / f"bad-{number}"
        with pytest.raises(SourceError, match="same season"):
            assemble_core_inputs(paths, output)
        assert not output.exists()


@pytest.mark.parametrize("policy", ["bridge.R", "renv.lock", "producer.R", "definitions.json"])
def test_mixed_policy_revisions_refused(two_years, tmp_path, policy):
    path = two_years[0]
    record = json.loads((path / "run.json").read_text())
    if policy in ("producer.R", "definitions.json"):
        parent_path = Path(record["source_directory"])
        with (parent_path / policy).open("ab") as stream:
            stream.write(b"\n")
        parent = json.loads((parent_path / "run.json").read_text())
        parent["files"][policy] = file_sha256(parent_path / policy)
        (parent_path / "run.json").write_text(json.dumps(parent))
        (path / "receiving-run.json").write_bytes((parent_path / "run.json").read_bytes())
        record["files"]["receiving-run.json"] = file_sha256(path / "receiving-run.json")
    else:
        with (path / policy).open("ab") as stream:
            stream.write(b"\n")
        record["files"][policy] = file_sha256(path / policy)
    (path / "run.json").write_text(json.dumps(record))
    with pytest.raises(SourceError, match="mixes"):
        assemble_core_inputs(two_years, tmp_path / "mixed")
    assert not (tmp_path / "mixed").exists()


@pytest.mark.parametrize("changed", ["index", "child_marker", "historical_table", "historical_rds"])
def test_changed_index_or_required_historical_inputs_fail(two_years, tmp_path, changed):
    output = tmp_path / "collection"
    inputs = assemble_core_inputs(two_years, output)
    path = {"index": output / "run.json", "child_marker": two_years[0] / "run.json",
            "historical_table": two_years[0] / "weekly-1999.csv",
            "historical_rds": Path(inputs.owners[1999].manifest["source_directory"]) / "weekly-1999.rds"}[changed]
    with path.open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(SourceError):
        inputs.load_feeds([2024], [1999, 2024])


def test_corrupt_capture_prevents_completed_collection_marker(two_years, tmp_path):
    (two_years[0] / "plays-1999.csv").write_text("corrupt")
    with pytest.raises(SourceError, match="SHA256"):
        assemble_core_inputs(two_years, tmp_path / "failed")
    assert not (tmp_path / "failed" / "run.json").exists()


def test_existing_index_is_never_overwritten(two_years, tmp_path):
    output = tmp_path / "collection"
    assemble_core_inputs(two_years, output)
    before = (output / "run.json").read_bytes()
    with pytest.raises(FileExistsError):
        assemble_core_inputs(two_years, output)
    assert (output / "run.json").read_bytes() == before


@pytest.mark.parametrize('latest_stored', [2023, 2025])
def test_real_loader_completes_legacy_migration_with_full_bound_range(two_years, tmp_path, monkeypatch, latest_stored):
    from pipeline.source_results import SeasonalFeed
    import pandas as pd
    # Shorten this synthetic league's history while exercising the actual range
    # calculation, old-table replacement and two-season stored outcomes.
    monkeypatch.setattr(loading, "FIRST_SEASON", 2023)
    prior = copy_year(two_years[1], tmp_path / "prior", 2023)
    later = copy_year(two_years[1], tmp_path / "later", 2025)
    inputs = assemble_core_inputs([prior, two_years[1], later], tmp_path / "short-history")
    schedules = pd.DataFrame({"season": [2024], "game_id": ["regular"], "away_score": [10], "home_score": [20]})
    rosters = pd.DataFrame({"season": [2024], "player_id": ["00-0123"], "player_name": ["Receiver"]})
    monkeypatch.setattr(loading, "fetch_schedules", lambda years: SeasonalFeed(schedules, years, []))
    monkeypatch.setattr(loading, "fetch_rosters", lambda years: SeasonalFeed(rosters, years, []))
    monkeypatch.setattr(loading, "fetch_weekly_stats", lambda *a, **k: pytest.fail("unexpected redownload"))
    monkeypatch.setattr(loading, "fetch_play_by_play", lambda *a, **k: pytest.fail("unexpected redownload"))
    with duckdb.connect(":memory:") as conn:
        conn.execute(f"CREATE TABLE weekly_player_stats AS SELECT {latest_stored} AS season, 'KC' AS recent_team")
        raw = loading.load_and_store_raw(conn, [2024], core_inputs=inputs)
        assert set(raw.plays.season) == {2024}
        expected = [(year, 2) for year in range(2023, max(2024, latest_stored) + 1)]
        assert conn.execute("SELECT season,COUNT(*) FROM weekly_player_stats GROUP BY season ORDER BY season").fetchall() == expected
        assert "team" in {row[0] for row in conn.execute("DESCRIBE weekly_player_stats").fetchall()}
        assert [(item.season, item.rows, item.detail) for item in raw.outcomes if item.source == "weekly_player_stats"] == [(year, count, inputs.revision()) for year, count in expected]


def test_candidate_worker_reads_collection_through_ordinary_prepare_cli(two_years, tmp_path, monkeypatch):
    collection = assemble_core_inputs(two_years, tmp_path / "collection")
    source, candidate = tmp_path / "source.duckdb", tmp_path / "candidate.duckdb"
    with duckdb.connect(str(source)) as conn:
        conn.execute("CREATE TABLE sentinel AS SELECT 42 AS value")
    before = file_sha256(source)
    popen = subprocess.Popen
    monkeypatch.setattr(snapshots.subprocess, "Popen", lambda command, **kwargs:
                        popen([command[0], "-c", CORE_WORKER, *command[3:]], **kwargs))
    checked = []
    def gate(path, *, core_inputs=None):
        assert core_inputs == collection.directory
        with duckdb.connect(str(path), read_only=True) as conn:
            outcomes = json.loads(conn.execute("SELECT source_outcomes FROM snapshot_preparation").fetchone()[0])
            assert all(item["detail"] == collection.revision() for item in outcomes if item["source"] in ("plays", "weekly_player_stats"))
        checked.append(path)
    monkeypatch.setattr(snapshots, "_run_validation", gate)
    snapshots.prepare_candidate(source, candidate, [2024], core_inputs=collection.directory)
    assert checked == [candidate] and file_sha256(source) == before


def test_collection_cli_needs_no_r_runtime(two_years, tmp_path):
    from jobs.receiving_core_inputs import main
    output = tmp_path / "collection"
    main(["--bundles", *(str(path) for path in two_years), "--output", str(output)])
    assert open_core_inputs(output).seasons == [1999, 2024]
