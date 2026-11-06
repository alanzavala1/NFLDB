"""HTTP receiving contract: safe totals, scoped gaps, legacy and read-only use."""
import hashlib
import json

import duckdb
import pytest
from fastapi.testclient import TestClient

import database
import main
import splits_builder
from pipeline.receiving_build import TOTALS_TABLE
from tests.test_receiving_build import build_case, fake_export


def api_for(monkeypatch, conn):
    monkeypatch.setattr(database, "_conn", conn)
    # A GET must succeed even when every lazy/offline builder is forbidden.
    monkeypatch.setattr(splits_builder, "materialize", lambda *a, **kw: pytest.fail("GET attempted a build"))
    return TestClient(main.app)  # no startup writes; exercise the actual route/middleware


@pytest.mark.parametrize("year", [1999, 2004, 2006, 2008, 2009, 2024, 2026])
def test_whole_totals_apply_historical_masks_and_target_rates(build_case, monkeypatch, year):
    conn, inputs = build_case(year)
    splits_builder.materialize(year, receiving_inputs=inputs)
    response = api_for(monkeypatch, conn).get("/api/players/receiver/receiving-splits")
    assert response.status_code == 200, response.text
    season = response.json()["seasons"][0]
    total = season["overall"]
    assert season["status"] == "prepared" and len(season["views"]) == 17
    assert (total["cmp"], total["yards"], total["td"], total["first_downs"]) == (28, 280, 0, 28)
    assert total["split_dim"] == "overall" and total["split_value"] == "all"
    assert total["att"] == (None if 2003 <= year <= 2008 else 28)
    assert total["epa"] == (None if 2003 <= year <= 2008 else .5)  # not the raw sum, 14
    assert total["success_pct"] == (None if 2003 <= year <= 2008 else 100.)
    assert total["yac"] == (None if year < 2006 else 200)
    assert total["air_yards"] == (None if year < 2009 else 56)
    for row in [total, *season["rows"]]:
        assert set(row["unavailable_metrics"]) == {key for key in (
            "att", "cmp", "yards", "td", "first_downs", "yac", "air_yards", "epa", "success_pct",
            "interceptions", "cpoe") if row[key] is None}
    assert "runtime" not in response.text and "source_revisions" not in response.text
    assert "qualifying_plays" not in response.text and "sha256" not in response.text


@pytest.mark.parametrize("fault,dimension,excluded", [
    ("partial_context", "field_zone", 4), ("unavailable_context", "field_zone", 28),
    ("unknown_surface", "surface", 4), ("charting_gap", "play_action", 4),
    ("charting_unavailable", "play_action", 28), ("rush_outlier", "blitz", 4),
])
def test_partial_views_do_not_shrink_overall_or_other_views(build_case, monkeypatch, fault, dimension, excluded):
    conn, inputs = build_case(fault=fault)
    splits_builder.materialize(2024, receiving_inputs=inputs)
    season = api_for(monkeypatch, conn).get("/api/players/receiver/receiving-splits").json()["seasons"][0]
    assert season["overall"]["cmp"] == 28 and season["overall"]["yards"] == 280
    view = season["views"][dimension]
    assert view["status"] == ("unavailable" if excluded == 28 else "partial")
    assert view["reason"] and view["excluded"]["cmp"] == excluded
    assert view["excluded"]["yards"] == excluded * 10
    assert sum(row["cmp"] for row in season["rows"] if row["split_dim"] == dimension) == 28 - excluded
    assert season["views"]["down"]["excluded"]["cmp"] == 0


def test_missing_air_does_not_erase_counts_or_verified_epa(build_case, monkeypatch):
    conn, inputs = build_case(fault="missing_air")
    splits_builder.materialize(2024, receiving_inputs=inputs)
    season = api_for(monkeypatch, conn).get("/api/players/receiver/receiving-splits").json()["seasons"][0]
    total = season["overall"]
    assert total["air_yards"] is None and "air_yards" in total["unavailable_metrics"]
    assert total["epa"] == .5 and total["success_pct"] == 100. and total["yards"] == 280
    assert any(row["air_yards"] is not None for row in season["rows"] if row["split_dim"] == "down")


def test_game_coverage_keeps_missing_and_unconfirmed_distinct(build_case, monkeypatch):
    conn, inputs = build_case()
    conn.execute("INSERT INTO schedules VALUES (2024,'missing','REG',21,10)")
    conn.execute("UPDATE schedules SET home_score=NULL WHERE game_id='game'")
    splits_builder.materialize(2024, receiving_inputs=inputs)
    season = api_for(monkeypatch, conn).get("/api/players/receiver/receiving-splits").json()["seasons"][0]
    coverage = season["game_coverage"]
    assert coverage["status"] == "partial"
    assert coverage["missing_game_ids"] == ["missing"]
    assert coverage["unconfirmed_game_ids"] == ["game"]
    assert season["overall"]["yards"] == 280


def test_legacy_rows_never_become_verified_whole_totals(build_case, monkeypatch):
    conn, _ = build_case()
    api = api_for(monkeypatch, conn)
    old = api.get("/api/players/old/splits")
    assert old.status_code == 200 and old.json()[0]["yards"] == 999
    assert "unavailable_metrics" not in old.json()[0]
    season = api.get("/api/players/old/receiving-splits").json()["seasons"][0]
    assert season["status"] == "unverified" and season["reason"]
    assert season["overall"] is None and season["rows"] == [] and season["views"] == {}
    assert api.get("/api/players/unknown/receiving-splits").json()["seasons"] == []
    assert api.get("/api/players/' OR true --/receiving-splits").json()["seasons"] == []


def test_corrupt_prepared_records_fail_without_falling_back_to_legacy(build_case, monkeypatch):
    conn, inputs = build_case()
    splits_builder.materialize(2024, receiving_inputs=inputs)
    record = json.loads(conn.execute(f"SELECT record FROM {TOTALS_TABLE}").fetchone()[0])
    record["rows"][0]["season"] = 2023
    conn.execute(f"UPDATE {TOTALS_TABLE} SET record=?", [json.dumps(record)])
    response = api_for(monkeypatch, conn).get("/api/players/receiver/receiving-splits")
    assert response.status_code == 503
    assert response.json() == {"detail": "Prepared receiving data is unavailable"}


def test_lost_row_in_partial_view_is_not_relabelled_as_a_source_gap(build_case, monkeypatch):
    conn, inputs = build_case(fault="partial_context")
    splits_builder.materialize(2024, receiving_inputs=inputs)
    conn.execute("DELETE FROM player_splits WHERE split_dim='field_zone' AND category='receiving'")
    response = api_for(monkeypatch, conn).get("/api/players/receiver/receiving-splits")
    assert response.status_code == 503


def test_invalid_coverage_fails_with_controlled_error_before_commit(build_case, monkeypatch):
    from pipeline.receiving_build import PREPARATION_TABLE
    conn, inputs = build_case()
    splits_builder.materialize(2024, receiving_inputs=inputs)
    record = json.loads(conn.execute(f"SELECT record FROM {PREPARATION_TABLE}").fetchone()[0])
    record["game_coverage"]["status"] = "invented"
    conn.execute(f"UPDATE {PREPARATION_TABLE} SET record=?", [json.dumps(record)])
    response = api_for(monkeypatch, conn).get("/api/players/receiver/receiving-splits")
    assert response.status_code == 503
    assert "ROLLBACK" not in response.text


def test_charting_explanation_does_not_expose_provider_diagnostics(build_case, monkeypatch):
    from pipeline.receiving_build import PREPARATION_TABLE
    conn, inputs = build_case(fault="charting_unavailable")
    splits_builder.materialize(2024, receiving_inputs=inputs)
    record = json.loads(conn.execute(f"SELECT record FROM {PREPARATION_TABLE}").fetchone()[0])
    record["dimensions"]["play_action"]["coverage"]["reason"] = "FTN not_found: C:/private/provider-error"
    conn.execute(f"UPDATE {PREPARATION_TABLE} SET record=?", [json.dumps(record)])
    response = api_for(monkeypatch, conn).get("/api/players/receiver/receiving-splits")
    assert response.status_code == 200
    assert "provider-error" not in response.text
    assert response.json()["seasons"][0]["views"]["play_action"]["reason"] == "Play charting is unavailable for this season."


def test_http_reads_succeed_on_readonly_database_without_changing_bytes(build_case, monkeypatch, tmp_path):
    conn, inputs = build_case(fault="partial_context")
    splits_builder.materialize(2024, receiving_inputs=inputs)
    path = tmp_path / "readonly.duckdb"
    escaped = str(path).replace("'", "''")
    conn.execute(f"ATTACH '{escaped}' AS candidate")
    conn.execute("COPY FROM DATABASE memory TO candidate")
    conn.execute("DETACH candidate")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with duckdb.connect(str(path), read_only=True) as readonly:
        api = api_for(monkeypatch, readonly)
        for _ in range(2):
            response = api.get("/api/players/receiver/receiving-splits")
            assert response.status_code == 200, response.text
            assert response.json()["seasons"][0]["overall"]["yards"] == 280
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not path.with_suffix(".duckdb.wal").exists()
