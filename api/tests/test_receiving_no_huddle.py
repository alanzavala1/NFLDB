"""Tempo uses the provider's binary flag, with explicit unknown coverage."""
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pipeline.receiving_dimensions import context_split_values
from pipeline.receiving_splits import adapt_receiving_splits
from pipeline.source_results import SourceError
import splits_builder


def inputs(season=2024):
    source = pd.DataFrame([dict(
        player_id=player, season=season, season_type="REG", split_value=bucket,
        targets=targets, receptions=catches, receiving_yards=yards, receiving_tds=td,
        receiving_yards_after_catch=yac, receiving_first_downs=first,
        receiving_epa=epa, receiving_air_yards=air,
    ) for player, bucket, targets, catches, yards, td, yac, first, epa, air in [
        ("receiver", "huddle", 2, 1, 20, 1, 15, 1, 2.0, 35),
        ("receiver", "no_huddle", 1, 1, 68, 0, 48, 1, 4.0, 20),
        ("lateral", "no_huddle", 0, 0, 7, 1, 7, 0, None, 0),
    ]])
    context = pd.DataFrame([dict(
        game_id="game", play_id=index, season=season, season_type="REG",
        two_point_attempt=0, no_huddle=flag,
        receiver_player_id="receiver", complete_pass=int(index != 1),
        incomplete_pass=int(index == 1), interception=0, epa=epa, air_yards=air,
    ) for index, (flag, epa, air) in enumerate([(1, 4.0, 20), (0, -1.0, 30), (0, 3.0, 5)])])
    return source, context


def adapt(source, context, season=2024):
    return adapt_receiving_splits(source, context=context, season=season,
                                  qualified_players=["receiver", "lateral"], dimension="no_huddle")


def test_recorded_tempo_preserves_lateral_production_rates_and_existing_sort_order():
    source, context = inputs()
    rows = adapt(source, context)
    receiver = rows[rows.player_id.eq("receiver")]
    assert receiver.split_value.tolist() == ["huddle", "no_huddle"]
    assert receiver.sort_order.tolist() == [1, 2]
    assert receiver.epa.tolist() == [1.0, 4.0]
    assert receiver.success_pct.tolist() == [50.0, 100.0]
    lateral = rows[rows.player_id.eq("lateral")].iloc[0]
    assert [lateral.split_value, lateral.att, lateral.cmp, lateral.yards, lateral.td, lateral.yac] == ["no_huddle", 0, 0, 7, 1, 7]
    assert pd.isna(lateral.epa) and pd.isna(lateral.success_pct) and lateral.air_yards == 0
    with duckdb.connect(":memory:") as conn:
        splits_builder.ensure_table(conn)
        conn.register("split_rows", rows)
        conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM split_rows")
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac) FROM player_splits").fetchone() == (3, 2, 95, 2, 70)


def test_known_zero_means_huddle_but_nullable_unknown_does_not():
    values = context_split_values(pd.DataFrame({"no_huddle": pd.Series([0, 1, pd.NA], dtype="Int64")}), "no_huddle", 2024)
    assert values.iloc[:2].tolist() == ["huddle", "no_huddle"]
    assert pd.isna(values.iloc[2])


@pytest.mark.parametrize("value", [-1, 2, 0.5, float("inf"), "yes"])
def test_invalid_flag_cannot_become_a_tempo_bucket(value):
    with pytest.raises(SourceError, match="invalid context no_huddle"):
        context_split_values(pd.DataFrame({"no_huddle": [value]}), "no_huddle", 2024)


def test_missing_flag_column_and_invalid_export_label_fail():
    source, context = inputs()
    with pytest.raises(SourceError, match="missing context no_huddle"):
        adapt(source, context.drop(columns="no_huddle"))
    source.loc[0, "split_value"] = "slow"
    with pytest.raises(SourceError, match="invalid no_huddle"):
        adapt(source, context)


@pytest.mark.parametrize("season", [2004, 2006])
def test_historical_masks_preserve_independently_supported_production(season):
    source, context = inputs(season)
    rows = adapt(source, context, season)
    assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
    assert [rows.cmp.sum(), rows.yards.sum(), rows.td.sum()] == [2, 95, 2]
    if season == 2004:
        assert rows.yac.isna().all()
    else:
        assert rows.yac.sum() == 70


def test_absent_tempo_is_not_invented_and_other_missing_context_is_irrelevant():
    source, context = inputs()
    context["shotgun"] = None
    context["score_differential"] = None
    rows = adapt(source[source.split_value.eq("huddle")], context[context.no_huddle.eq(0)])
    assert rows.split_value.tolist() == ["huddle"]
    assert rows.epa.iloc[0] == 1.0


def test_real_official_tempo_counts_and_field_specific_gaps():
    fixtures = Path(__file__).parent / "fixtures"
    record = json.loads((fixtures / "upstream_receiving_no_huddle.json").read_text())
    source = pd.DataFrame(record["rows"], columns=record["columns"])
    context = pd.read_csv(fixtures / "upstream_receiving_context.csv")
    for year, players, expected in [
        (2006, ["00-0006101"], [(None, 73, 900, 5, 319, 54)]),
        (2009, ["00-0006101"], [(135, 83, 867, 6, 240, 54)]),
        (2024, ["00-0036322", "00-0039139"], [(154, 103, 1533, 10, 487, 62), (63, 52, 517, 4, 593, 24)]),
    ]:
        rows = adapt_receiving_splits(source[source.season.eq(year)],
                                      context=context[context.season.eq(year)], season=year,
                                      qualified_players=players, dimension="no_huddle")
        with duckdb.connect(":memory:") as conn:
            splits_builder.ensure_table(conn)
            conn.register("split_rows", rows)
            conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM split_rows")
            assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac),SUM(first_downs) FROM player_splits GROUP BY player_id ORDER BY player_id").fetchall() == expected
        if year == 2006:
            assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
        elif year == 2009:
            assert rows.epa.notna().all() and rows.success_pct.notna().all()
            assert rows.air_yards.isna().any()
        else:
            assert rows[["epa", "success_pct", "air_yards"]].notna().all().all()
