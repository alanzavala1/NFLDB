"""Field position uses the pre-play spot, with disjoint boundaries and unknown handling."""
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
    source = pd.DataFrame([dict(player_id=player, season=season, season_type="REG",
                                split_value=bucket, targets=targets, receptions=catches,
                                receiving_yards=yards, receiving_tds=td,
                                receiving_yards_after_catch=yac, receiving_first_downs=first,
                                receiving_epa=epa, receiving_air_yards=air)
                          for player, bucket, targets, catches, yards, td, yac, first, epa, air in [
                              ("receiver", "red_zone", 1, 1, 20, 1, 15, 1, 3.0, 5),
                              ("receiver", "own_territory", 1, 1, 68, 0, 48, 1, 4.0, 20),
                              ("receiver", "opp_territory", 1, 0, 0, 0, 0, 0, -1.0, 30),
                              ("lateral", "own_territory", 0, 0, 7, 1, 7, 0, None, 0),
                          ]])
    context = pd.DataFrame([dict(game_id="game", play_id=i, season=season, season_type="REG",
                                 two_point_attempt=0, yardline_100=spot,
                                 receiver_player_id="receiver", complete_pass=int(i != 1),
                                 incomplete_pass=int(i == 1), interception=0, epa=epa, air_yards=air)
                            for i, (spot, epa, air) in enumerate([(75, 4.0, 20), (50, -1.0, 30), (20, 3.0, 5)])])
    return source, context


def adapt(source, context, season=2024):
    return adapt_receiving_splits(source, context=context, season=season,
                                  qualified_players=["receiver", "lateral"], dimension="field_zone")


def test_preplay_territory_keeps_lateral_touchdown_and_does_not_follow_play_end_position():
    source, context = inputs()
    rows = adapt(source, context)
    receiver = rows[rows.player_id.eq("receiver")]
    assert receiver.split_value.tolist() == ["own_territory", "opp_territory", "red_zone"]
    assert receiver.sort_order.tolist() == [1, 2, 3]
    assert receiver.epa.tolist() == [4.0, -1.0, 3.0]
    assert receiver.success_pct.tolist() == [100.0, 0.0, 100.0]
    lateral = rows[rows.player_id.eq("lateral")].iloc[0]
    assert [lateral.split_value, lateral.att, lateral.cmp, lateral.yards, lateral.td, lateral.yac] == ["own_territory", 0, 0, 7, 1, 7]
    assert pd.isna(lateral.epa) and pd.isna(lateral.success_pct) and lateral.air_yards == 0
    with duckdb.connect(":memory:") as conn:
        splits_builder.ensure_table(conn)
        conn.register("split_rows", rows)
        conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM split_rows")
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac) FROM player_splits WHERE split_dim='field_zone'").fetchone() == (3, 2, 95, 2, 70)


def test_midfield_and_red_zone_boundaries_are_disjoint_and_missing_is_unknown():
    context = pd.DataFrame({"yardline_100": pd.Series([0, 20, 20.5, 50, 50.5, 100, pd.NA], dtype="Float64")})
    values = context_split_values(context, "field_zone", 2024)
    assert values.iloc[:6].tolist() == ["red_zone", "red_zone", "opp_territory", "opp_territory", "own_territory", "own_territory"]
    assert pd.isna(values.iloc[6])


@pytest.mark.parametrize("value", [-1, 100.1, float("inf"), "unknown"])
def test_invalid_spots_fail_instead_of_becoming_a_territory(value):
    source, context = inputs()
    context["yardline_100"] = context.yardline_100.astype(object)
    context.loc[0, "yardline_100"] = value
    with pytest.raises(SourceError, match="invalid context yardline_100"):
        adapt(source, context)


def test_missing_spot_masks_affected_target_metrics_and_missing_column_fails():
    source, context = inputs()
    with pytest.raises(SourceError, match="missing context yardline_100"):
        adapt(source, context.drop(columns="yardline_100"))
    context.loc[0, "yardline_100"] = None
    rows = adapt(source, context)
    own = rows[rows.player_id.eq("receiver") & rows.split_value.eq("own_territory")].iloc[0]
    assert [own.att, own.cmp, own.yards] == [1, 1, 68]
    assert pd.isna(own.epa) and pd.isna(own.air_yards)
    assert rows[rows.player_id.eq("receiver") & rows.split_value.eq("red_zone")].epa.iloc[0] == 3.0


def test_historical_counts_and_YAC_survive_unknown_targets():
    source, context = inputs(2006)
    rows = adapt(source, context, 2006)
    assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
    assert rows.yards.sum() == 95 and rows.yac.sum() == 70 and rows.td.sum() == 2


def test_absent_zone_is_not_invented_and_invalid_export_label_fails():
    source, context = inputs()
    rows = adapt(source[source.split_value.eq("own_territory")], context[context.yardline_100.eq(75)])
    assert rows.split_value.eq("own_territory").all()
    source.loc[0, "split_value"] = "midfield"
    with pytest.raises(SourceError, match="invalid field_zone"):
        adapt(source, context)


def test_real_exports_conserve_counts_and_preserve_historical_field_gaps():
    fixtures = Path(__file__).parent / "fixtures"
    record = json.loads((fixtures / "upstream_receiving_field_zone.json").read_text())
    source = pd.DataFrame(record["rows"], columns=record["columns"])
    context = pd.read_csv(fixtures / "upstream_receiving_context.csv")
    for year, players, expected in [
        (2006, ["00-0006101"], [(None, 73, 900, 5, 319, 54)]),
        (2009, ["00-0006101"], [(135, 83, 867, 6, 240, 54)]),
        (2024, ["00-0036322", "00-0039139"], [(154, 103, 1533, 10, 487, 62), (63, 52, 517, 4, 593, 24)]),
    ]:
        rows = adapt_receiving_splits(source[source.season.eq(year)],
                                      context=context[context.season.eq(year)], season=year,
                                      qualified_players=players, dimension="field_zone")
        with duckdb.connect(":memory:") as conn:
            splits_builder.ensure_table(conn)
            conn.register("split_rows", rows)
            conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM split_rows")
            assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac),SUM(first_downs) FROM player_splits GROUP BY player_id ORDER BY player_id").fetchall() == expected
        if year == 2006:
            assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
        elif year == 2009:
            assert rows.air_yards.isna().sum() == 1
            assert rows.epa.notna().all() and rows.success_pct.notna().all()
        else:
            assert rows.groupby("player_id").split_value.apply(list).tolist() == [
                ["own_territory", "opp_territory", "red_zone"],
                ["own_territory", "opp_territory", "red_zone"],
            ]
            assert rows[["epa", "success_pct", "air_yards"]].notna().all().all()
