"""Real R outputs map to existing SQL rows; corrupt exports fail before filtering."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pipeline.receiving_splits import (
    EXPORT_CONTRACT, VERSIONS, adapt_receiving_down, load_receiving_down_export,
)
from pipeline.source_results import SourceError
import splits_builder


FIXTURE = json.loads((Path(__file__).parent / "fixtures/upstream_receiving_down.json").read_text())
GIBBS = "00-0039139"
JEFFERSON = "00-0036322"
GONZALEZ = "00-0006101"


def frame(season=2024):
    source = pd.DataFrame(FIXTURE["rows"], columns=FIXTURE["columns"])
    return source[source.season.eq(season)].reset_index(drop=True)


def adapt(source=None, season=2024, players=(GIBBS, JEFFERSON)):
    return adapt_receiving_down(frame(season) if source is None else source,
                                season=season, qualified_players=players)


def test_real_counts_round_trip_through_actual_player_splits_schema():
    with duckdb.connect(":memory:") as conn:
        splits_builder.ensure_table(conn)
        for year, players in ((2024, [GIBBS, JEFFERSON]), (2004, [GONZALEZ])):
            rows = adapt(season=year, players=players)
            assert tuple(rows.columns) == splits_builder._COLUMNS
            conn.register("adapted", rows)
            conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM adapted")
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td) FROM player_splits WHERE player_id=?", [GIBBS]).fetchone() == (63, 52, 517, 4)
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td) FROM player_splits WHERE player_id=?", [JEFFERSON]).fetchone() == (154, 103, 1533, 10)
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td) FROM player_splits WHERE player_id=?", [GONZALEZ]).fetchone() == (None, 102, 1258, 7)
        assert conn.execute("SELECT SUM(yac),SUM(first_downs) FROM player_splits WHERE player_id=?", [GIBBS]).fetchone() == (593, 24)
        assert conn.execute("SELECT SUM(yac),SUM(first_downs) FROM player_splits WHERE player_id=?", [JEFFERSON]).fetchone() == (487, 62)
        assert conn.execute("SELECT SUM(yac),SUM(first_downs) FROM player_splits WHERE player_id=?", [GONZALEZ]).fetchone() == (None, 69)
        assert conn.execute("SELECT COUNT(*) FROM player_splits WHERE epa IS NOT NULL OR success_pct IS NOT NULL OR air_yards IS NOT NULL").fetchone()[0] == 0


def test_historical_positive_credits_remain_unknown_without_erasing_production():
    source = frame(2004)
    source.loc[0, "targets"] = 1
    result = adapt(source, season=2004, players=[GONZALEZ])
    assert result.att.isna().all()
    assert result.cmp.sum() == 102
    assert result.yards.sum() == 1258
    assert result.td.sum() == 7


def test_lateral_negative_yards_real_zeros_and_explicit_admission():
    source = frame().iloc[:1].copy()
    source.loc[0, ["targets", "receptions", "receiving_yards", "receiving_tds"]] = [0, 0, -3, 1]
    source.loc[0, ["receiving_yards_after_catch", "receiving_first_downs"]] = [-3, 0]
    result = adapt(source, players=[GIBBS])
    assert result[["att", "cmp", "yards", "td"]].iloc[0].tolist() == [0, 0, -3, 1]
    assert result.yac.iloc[0] == -3
    assert adapt(source, players=[JEFFERSON]).empty
    source.loc[0, ["targets", "receptions", "receiving_yards", "receiving_tds", "receiving_yards_after_catch", "receiving_first_downs"]] = 0
    assert adapt(source).empty


def test_unidentified_players_are_excluded_without_mutating_input():
    source = frame().iloc[:2].copy()
    source.loc[0, "player_id"] = None
    before = source.copy(deep=True)
    result = adapt(source)
    assert len(result) == 1
    pd.testing.assert_frame_equal(source, before)


@pytest.mark.parametrize("column,value", [
    ("targets", None), ("receiving_yards", float("nan")), ("receiving_yards", float("inf")),
    ("receiving_yards", 1.5), ("receptions", -1), ("receiving_tds", -1),
    ("receiving_yards", 2**31), ("targets", "bad"),
    ("receiving_yards_after_catch", None), ("receiving_yards_after_catch", float("inf")),
    ("receiving_yards_after_catch", 1.5), ("receiving_first_downs", -1),
    ("receiving_first_downs", None),
    ("receiving_first_downs", 100),
    ("season", None), ("season", 2023), ("season_type", "POST"),
    ("season_type", None), ("split_value", "5"), ("split_value", None),
    ("player_id", " "), ("player_id", " padded "),
])
def test_bad_source_rows_fail_even_when_player_is_not_admitted(column, value):
    source = frame().astype(object)
    source.loc[0, column] = value
    with pytest.raises(SourceError):
        adapt(source, players=[JEFFERSON])


def test_missing_columns_empty_input_and_duplicate_rows_fail():
    for source in (frame().drop(columns="targets"), frame().iloc[:0], pd.concat([frame(), frame().iloc[:1]])):
        with pytest.raises(SourceError):
            adapt(source)


def test_player_ids_must_be_an_explicit_collection():
    with pytest.raises(SourceError):
        adapt(players=GIBBS)


@pytest.fixture
def export(tmp_path):
    manifest = {**VERSIONS, "seasons": [2024], "receiving_export": deepcopy(EXPORT_CONTRACT)}
    frame().to_csv(tmp_path / "down-2024.csv", index=False)
    manifest["files"] = {"down-2024.csv": hashlib.sha256((tmp_path / "down-2024.csv").read_bytes()).hexdigest()}
    (tmp_path / "run.json").write_text(json.dumps(manifest))
    return tmp_path, manifest


def test_completed_export_loads_without_r_or_network(export):
    directory, _ = export
    result = load_receiving_down_export(directory, season=2024, qualified_players=[GIBBS])
    assert result.yards.sum() == 517
    assert result.player_id.unique().tolist() == [GIBBS]


@pytest.mark.parametrize("field,value", [
    ("season_type", "POST"), ("summary_level", "week"), ("split_dimension", "quarter"),
    ("excludes_two_point_attempts", False), ("excludes_two_point_attempts", 1),
    ("schema_version", 4), ("schema_version", True),
])
def test_scope_drift_fails(export, field, value):
    directory, manifest = export
    manifest["receiving_export"][field] = value
    (directory / "run.json").write_text(json.dumps(manifest))
    with pytest.raises(SourceError):
        load_receiving_down_export(directory, season=2024, qualified_players=[GIBBS])


@pytest.mark.parametrize("field,value", [
    ("nflfastR", "unknown"), ("nflreadr", "1.0.0"), ("seasons", [2004]),
    ("receiving_export", None),
])
def test_version_or_completion_metadata_drift_fails(export, field, value):
    directory, manifest = export
    manifest[field] = value
    (directory / "run.json").write_text(json.dumps(manifest))
    with pytest.raises(SourceError):
        load_receiving_down_export(directory, season=2024, qualified_players=[GIBBS])


@pytest.mark.parametrize("name", ["run.json", "down-2024.csv"])
def test_partial_exports_fail(export, name):
    directory, _ = export
    (directory / name).unlink()
    with pytest.raises(SourceError):
        load_receiving_down_export(directory, season=2024, qualified_players=[GIBBS])


def test_changed_export_bytes_are_rejected_even_if_counts_still_parse(export):
    directory, _ = export
    path = directory / "down-2024.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SourceError, match="SHA256 mismatch"):
        load_receiving_down_export(directory, season=2024, qualified_players=[GIBBS])


def test_missing_export_hash_is_rejected(export):
    directory, manifest = export
    manifest.pop("files")
    (directory / "run.json").write_text(json.dumps(manifest))
    with pytest.raises(SourceError, match="missing SHA256"):
        load_receiving_down_export(directory, season=2024, qualified_players=[GIBBS])


def test_historical_YAC_is_unknown_even_with_a_positive_stray_value():
    source = frame(2004)
    source.loc[0, "receiving_yards_after_catch"] = 42
    rows = adapt(source, season=2004, players=[GONZALEZ])
    assert rows.yac.isna().all()
    assert rows.first_downs.sum() == 69
    assert rows.yards.sum() == 1258


def test_2006_YAC_does_not_acquire_a_target_dependency():
    source = frame(2006)
    rows = adapt(source, season=2006, players=[GONZALEZ])
    assert rows.att.isna().all()
    assert rows.cmp.sum() == 73
    assert rows.yards.sum() == 900
    assert rows.yac.sum() == 319
    assert rows.first_downs.sum() == 54


def test_supported_zero_YAC_is_not_missing_and_YAC_can_exceed_receiving_yards():
    source = frame().iloc[:1].copy()
    assert adapt(source).yac.iloc[0] > adapt(source).yards.iloc[0]
    source["receiving_yards_after_catch"] = 0
    assert adapt(source).yac.iloc[0] == 0


def test_missing_new_fields_is_not_treated_as_a_zero_valued_legacy_export():
    for column in ("receiving_yards_after_catch", "receiving_first_downs"):
        with pytest.raises(SourceError, match="missing columns"):
            adapt(frame().drop(columns=column))
