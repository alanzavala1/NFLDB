"""Same-input ingestion checks: real typed CSVs, DuckDB writes and source guards."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import duckdb
import pandas as pd
import pytest

from pipeline import loading
from pipeline.receiving_core_inputs import ReceivingCoreInputs, export_core_inputs
from pipeline.receiving_preview import file_sha256
from pipeline.receiving_splits import EXPORT_CONTRACT, VERSIONS
from pipeline.source_results import SeasonalFeed, SourceError
from pipeline.sources import PLAYS_KEEP_COLUMNS
from tests.test_weekly_columns import _feed_frame


@pytest.fixture
def bundle(tmp_path):
    exports, output = tmp_path / "receiving", tmp_path / "core"
    exports.mkdir()
    output.mkdir()
    pbp = pd.DataFrame({
        "season": [2024] * 4, "season_type": ["REG", "REG", "REG", "POST"],
        "game_id": ["regular"] * 3 + ["postseason"], "play_id": [1., 2., 3., 1.], "week": [1, 1, 1, 19],
        "two_point_attempt": [0., 0., 1., 0.], "receiver_player_id": ["00-0123"] * 4,
        "complete_pass": [1.] * 4, "incomplete_pass": [0.] * 4, "interception": [0.] * 4,
        "epa": [0.123456789, None, 2., -0.5],
        "desc": ["NA", "", 'a comma, a "quote" and café', "null"],
        "surface": [None] * 4,
    })
    weekly = pd.concat([
        _feed_frame(2024).assign(player_id="00-0123", player_name="Receiver", targets=2., receptions=2.,
                                 receiving_yards=25., receiving_tds=1.),
        _feed_frame(2024).assign(player_id=None, player_name=None),
        _feed_frame(2024, 19).assign(player_id="00-0123", player_name="Receiver", season_type="POST"),
    ], ignore_index=True)
    manifest = {**VERSIONS, "receiving_export": deepcopy(EXPORT_CONTRACT), "seasons": [2024], "files": {}}
    context = pbp.loc[:1].drop(columns=["desc", "surface"])
    context.to_csv(exports / "context-2024.csv", index=False)
    weekly.drop(columns=["team", "player_name"]).loc[weekly.season_type.eq("REG")].to_csv(
        exports / "weekly-2024.csv", index=False)
    for name in ("pbp-2024.rds", "weekly-2024.rds"):
        (exports / name).write_bytes(b"deterministic captured RDS fixture")
    (exports / "producer.R").write_text("# fixture calculator producer")
    (exports / "definitions.json").write_text("{}")
    for path in exports.iterdir():
        manifest["files"][path.name] = file_sha256(path)
    (exports / "run.json").write_text(json.dumps(manifest))
    (output / "receiving-run.json").write_bytes((exports / "run.json").read_bytes())
    for name in ("bridge.R", "environment.R", "renv.lock", "columns.json"):
        (output / name).write_text("fixture")
    core = {"format_version": 1, "seasons": [2024], "missing_value": "__NFLDB_MISSING_VALUE__",
            "source_directory": str(exports), "files": {}, "tables": {}}
    for name, frame, origin in (("plays-2024.csv", pbp, "pbp-2024.rds"),
                                 ("weekly-2024.csv", weekly, "weekly-2024.rds")):
        frame.to_csv(output / name, index=False, na_rep=core["missing_value"])
        types = {column: "integer" if pd.api.types.is_integer_dtype(frame[column]) else
                 "double" if pd.api.types.is_float_dtype(frame[column]) else "character" for column in frame}
        core["tables"][name] = {"rows": len(frame), "columns": types, "source": origin,
                                 "source_sha256": manifest["files"][origin]}
    for path in output.iterdir():
        core["files"][path.name] = file_sha256(path)
    (output / "run.json").write_text(json.dumps(core))
    return output


def rewrite_table(bundle, name, change):
    """Rebind an altered CSV to exercise semantic checks beyond byte hashing."""
    manifest = json.loads((bundle / "run.json").read_text())
    frame = pd.read_csv(bundle / name, keep_default_na=False)
    change(frame)
    frame.to_csv(bundle / name, index=False)
    manifest["files"][name] = file_sha256(bundle / name)
    (bundle / "run.json").write_text(json.dumps(manifest))


def test_preserves_full_scope_string_identity_nulls_and_main_precision(bundle):
    plays, weekly = ReceivingCoreInputs(bundle).feeds([2024])
    assert len(plays.data) == 4 and len(weekly.data) == 3
    assert plays.data.two_point_attempt.sum() == 1 and plays.data.season_type.eq("POST").sum() == 1
    assert plays.data.desc.tolist() == ["NA", "", 'a comma, a "quote" and café', "null"]
    assert plays.data.surface.isna().all()
    assert plays.data.receiver_player_id.tolist() == ["00-0123"] * 4
    assert str(plays.data.epa.dtype) == "float32" and pd.isna(plays.data.epa[1])
    assert plays.data.columns.tolist() == [column for column in PLAYS_KEEP_COLUMNS if column in plays.data]


@pytest.mark.parametrize("name", ["plays-2024.csv", "weekly-2024.csv", "bridge.R", "receiving-run.json"])
def test_changed_bundle_bytes_rejected(bundle, name):
    with (bundle / name).open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(SourceError, match="SHA256"):
        ReceivingCoreInputs(bundle).feeds([2024])


@pytest.mark.parametrize("name", ["pbp-2024.rds", "weekly-2024.rds", "run.json"])
def test_changed_upstream_capture_rejected_even_after_reader_created(bundle, name):
    inputs = ReceivingCoreInputs(bundle)
    with (inputs.source / name).open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(SourceError, match="changed"):
        inputs.feeds([2024])


@pytest.mark.parametrize("name,column", [("plays-2024.csv", "epa"), ("weekly-2024.csv", "receptions")])
def test_rebound_values_must_still_match_calculator_references(bundle, name, column):
    rewrite_table(bundle, name, lambda frame: frame.__setitem__(column, 99.))
    with pytest.raises(SourceError, match="differ from receiving references"):
        ReceivingCoreInputs(bundle).feeds([2024])


def test_duplicate_play_identity_rejected(bundle):
    def duplicate(frame):
        frame.loc[1, "play_id"] = frame.loc[0, "play_id"]
    rewrite_table(bundle, "plays-2024.csv", duplicate)
    with pytest.raises(SourceError, match="play identity"):
        ReceivingCoreInputs(bundle).feeds([2024])


def test_missing_captured_year_never_falls_back_to_network(bundle):
    with pytest.raises(SourceError, match="every requested season"):
        ReceivingCoreInputs(bundle).feeds([2024, 2025])


def test_real_loader_reuses_both_feeds_preserves_history_and_reports_revisions(bundle, monkeypatch):
    inputs = ReceivingCoreInputs(bundle)
    def unexpected(*args, **kwargs):
        pytest.fail("bound plays/weekly must not be downloaded again")
    monkeypatch.setattr(loading, "fetch_play_by_play", unexpected)
    monkeypatch.setattr(loading, "fetch_weekly_stats", unexpected)
    schedules = pd.DataFrame({"season": [2024], "game_id": ["regular"], "away_score": [10], "home_score": [20]})
    rosters = pd.DataFrame({"season": [2024], "player_id": ["00-0123"], "player_name": ["Receiver"]})
    monkeypatch.setattr(loading, "fetch_schedules", lambda years: SeasonalFeed(schedules, years, []))
    monkeypatch.setattr(loading, "fetch_rosters", lambda years: SeasonalFeed(rosters, years, []))
    with duckdb.connect(":memory:") as conn:
        old = _feed_frame(2023)
        conn.register("old", old)
        conn.execute("CREATE TABLE weekly_player_stats AS SELECT * FROM old")
        raw = loading.load_and_store_raw(conn, [2024], log=lambda _: None, core_inputs=inputs)
        assert len(raw.plays) == 4
        assert conn.execute("SELECT season, COUNT(*) FROM weekly_player_stats GROUP BY season ORDER BY season").fetchall() == [(2023, 1), (2024, 2)]
        assert conn.execute("SELECT receptions, receiving_yards FROM weekly_player_stats WHERE season=2024 AND week=1").fetchone() == (2, 25)
        assert conn.execute("SELECT COUNT(*) FROM plays WHERE season_type='POST' OR two_point_attempt=1").fetchone()[0] == 2
        provenance = [item.detail for item in raw.outcomes if item.source in ("plays", "weekly_player_stats")]
        assert provenance == [inputs.revision()] * 2


def test_legacy_weekly_migration_requires_bound_history_before_any_writes(bundle, monkeypatch):
    monkeypatch.setattr(loading, "fetch_schedules", lambda years: pytest.fail("must reject before context downloads"))
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE weekly_player_stats (season INTEGER, recent_team VARCHAR)")
        conn.execute("INSERT INTO weekly_player_stats VALUES (2023,'KC')")
        with pytest.raises(SourceError, match="every requested season"):
            loading.load_and_store_raw(conn, [2024], core_inputs=ReceivingCoreInputs(bundle))
        assert conn.execute("SELECT * FROM weekly_player_stats").fetchall() == [(2023, "KC")]
        assert conn.execute("SHOW TABLES").fetchall() == [("weekly_player_stats",)]


def test_existing_output_is_preserved(bundle):
    before = (bundle / "run.json").read_bytes()
    with pytest.raises(FileExistsError):
        export_core_inputs(bundle.parent / "receiving", bundle,
                           rscript=Path(__file__), library=bundle.parent)
    assert (bundle / "run.json").read_bytes() == before


CORE_WORKER = '''
import pandas as pd
import database
import ingest
from pipeline import loading
from pipeline.source_results import SeasonalFeed
schedules = pd.DataFrame({'season':[2024], 'game_id':['regular'], 'away_score':[10], 'home_score':[20]})
rosters = pd.DataFrame({'season':[2024], 'player_id':['00-0123'], 'player_name':['Receiver']})
loading.fetch_schedules = lambda years: SeasonalFeed(schedules,years,[])
loading.fetch_rosters = lambda years: SeasonalFeed(rosters,years,[])
def forbidden(*args,**kwargs):
    raise RuntimeError('Unexpected core download')
loading.fetch_play_by_play = forbidden
loading.fetch_weekly_stats = forbidden
def player_stats(conn,plays,seasons,log):
    conn.execute('CREATE TABLE player_game_stats AS SELECT season,player_id FROM weekly_player_stats')
ingest.build_player_game_stats = player_stats
ingest.load_advanced_stats = lambda *a,**k: []
ingest.load_supplemental_data = lambda *a,**k: []
ingest.prepare_analytics = lambda *a,**k: None
database.ensure_indexes = lambda **kwargs: None
from jobs.prepare_worker import main
main()
'''


@pytest.mark.parametrize("gate_fails", [False, True])
def test_candidate_worker_consumes_captures_records_provenance_and_retains_full_gate(bundle, monkeypatch, gate_fails):
    from pipeline import snapshots
    source, candidate = bundle.parent / "published.duckdb", bundle.parent / "candidate.duckdb"
    with duckdb.connect(str(source)) as conn:
        conn.execute("CREATE TABLE sentinel AS SELECT 42 AS value")
    before = file_sha256(source)
    popen = subprocess.Popen
    def start(command, **kwargs):
        return popen([command[0], "-c", CORE_WORKER, *command[3:]], **kwargs)
    monkeypatch.setattr(snapshots.subprocess, "Popen", start)
    checked = []
    def gate(path):
        # Analytics are intentionally stubbed for this lifecycle control, so
        # inspect the real worker's core/provenance writes in place of full QA.
        with duckdb.connect(str(path), read_only=True) as conn:
            assert conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0] == 4
            assert conn.execute("SELECT value FROM sentinel").fetchone()[0] == 42
            outcomes = json.loads(conn.execute("SELECT source_outcomes FROM snapshot_preparation").fetchone()[0])
            assert [item["detail"] for item in outcomes if item["source"] in ("plays", "weekly_player_stats")] == [ReceivingCoreInputs(bundle).revision()] * 2
        checked.append(path)
        if gate_fails:
            raise RuntimeError("full validation rejected candidate")
    monkeypatch.setattr(snapshots, "_run_validation", gate)
    if gate_fails:
        with pytest.raises(RuntimeError, match="full validation rejected"):
            snapshots.prepare_candidate(source, candidate, [2024], core_inputs=bundle)
        assert not candidate.exists()
    else:
        snapshots.prepare_candidate(source, candidate, [2024], core_inputs=bundle)
        assert candidate.exists()
    assert checked == [candidate]
    assert file_sha256(source) == before
    assert not Path(str(candidate) + ".wal").exists()


def test_invalid_bundle_worker_failure_removes_only_candidate(bundle, monkeypatch):
    from pipeline import snapshots
    source, candidate = bundle.parent / "published.duckdb", bundle.parent / "failed.duckdb"
    with duckdb.connect(str(source)) as conn:
        conn.execute("CREATE TABLE sentinel AS SELECT 42 AS value")
    before = file_sha256(source)
    (bundle / "plays-2024.csv").write_text("corrupt input")
    popen = subprocess.Popen
    monkeypatch.setattr(snapshots.subprocess, "Popen",
                        lambda command, **kwargs: popen([command[0], "-c", CORE_WORKER, *command[3:]], **kwargs))
    monkeypatch.setattr(snapshots, "_run_validation", lambda path: pytest.fail("invalid inputs reached full QA"))
    with pytest.raises(subprocess.CalledProcessError):
        snapshots.prepare_candidate(source, candidate, [2024], core_inputs=bundle)
    assert not candidate.exists() and file_sha256(source) == before
    assert not Path(str(candidate) + ".wal").exists()


def test_prepare_cli_passes_explicit_core_bundle(bundle, monkeypatch):
    from jobs import prepare
    calls = []
    monkeypatch.setattr(prepare, "prepare_candidate", lambda *args, **kwargs: calls.append((args, kwargs)))
    prepare.main(["--source", "source.duckdb", "--candidate", "new.duckdb", "--seasons", "2024",
                  "--core-inputs", str(bundle)])
    assert calls == [((Path("source.duckdb"), Path("new.duckdb"), [2024]), {"core_inputs": bundle})]
