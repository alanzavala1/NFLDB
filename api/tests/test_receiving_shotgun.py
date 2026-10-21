"""Binary formation flags use shared receiving rules without inventing missing zeroes."""
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
                              ("receiver", "under_center", 1, 1, 10, 1, 5, 1, 3.0, 5),
                              ("receiver", "shotgun", 2, 1, 8, 0, 6, 1, 1.0, 2),
                              ("lateral", "shotgun", 0, 0, 7, 1, 7, 0, None, 0),
                          ]])
    context = pd.DataFrame([dict(game_id="game", play_id=i, season=season, season_type="REG",
                                 two_point_attempt=0, shotgun=1 if i < 2 else 0,
                                 receiver_player_id="receiver", complete_pass=int(i != 1),
                                 incomplete_pass=int(i == 1), interception=0, epa=epa, air_yards=air)
                            for i, (epa, air) in enumerate([(2.0, 2), (-1.0, 0), (3.0, 5)])])
    return source, context


def adapt(source, context, season=2024):
    return adapt_receiving_splits(source, context=context, season=season,
                                  qualified_players=["receiver", "lateral"], dimension="shotgun")


def test_formation_labels_sorting_and_lateral_counts_round_trip_without_period_fields():
    source, context = inputs()
    rows = adapt(source, context)
    receiver = rows[rows.player_id.eq("receiver")]
    assert receiver.split_value.tolist() == ["shotgun", "under_center"]
    assert receiver.sort_order.tolist() == [1, 2]
    assert receiver.epa.tolist() == [0.5, 3.0]
    assert receiver.success_pct.tolist() == [50.0, 100.0]
    lateral = rows[rows.player_id.eq("lateral")].iloc[0]
    assert [lateral.att, lateral.cmp, lateral.yards, lateral.td, lateral.yac, lateral.air_yards] == [0, 0, 7, 1, 7, 0]
    assert pd.isna(lateral.epa) and pd.isna(lateral.success_pct)
    with duckdb.connect(":memory:") as conn:
        splits_builder.ensure_table(conn)
        conn.register("split_rows", rows)
        conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM split_rows")
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac) FROM player_splits WHERE split_dim='shotgun'").fetchone() == (3, 2, 25, 2, 18)


def test_missing_nullable_flag_is_not_under_center_and_missing_column_fails():
    context = pd.DataFrame({"shotgun": pd.Series([pd.NA, 1, 0], dtype="Int64")})
    values = context_split_values(context, "shotgun", 2024)
    assert pd.isna(values.iloc[0]) and values.iloc[1:].tolist() == ["shotgun", "under_center"]
    source, context = inputs()
    with pytest.raises(SourceError, match="missing context shotgun"):
        adapt(source, context.drop(columns="shotgun"))


@pytest.mark.parametrize("value", [2, -1, 0.5, float("inf"), "unknown"])
def test_invalid_formation_flags_fail_instead_of_defaulting_under_center(value):
    source, context = inputs()
    context["shotgun"] = context.shotgun.astype(object)
    context.loc[0, "shotgun"] = value
    with pytest.raises(SourceError, match="invalid context shotgun"):
        adapt(source, context)


def test_missing_target_formation_masks_affected_target_metrics_only():
    source, context = inputs()
    context.loc[0, "shotgun"] = None
    rows = adapt(source, context)
    shotgun = rows[rows.player_id.eq("receiver") & rows.split_value.eq("shotgun")].iloc[0]
    assert [shotgun.att, shotgun.cmp, shotgun.yards] == [2, 1, 8]
    assert pd.isna(shotgun.epa) and pd.isna(shotgun.air_yards)
    assert rows[rows.player_id.eq("receiver") & rows.split_value.eq("under_center")].epa.iloc[0] == 3.0


def test_historical_YAC_and_receiving_counts_survive_unknown_targets():
    source, context = inputs(2006)
    rows = adapt(source, context, 2006)
    assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
    assert rows.yards.sum() == 25 and rows.yac.sum() == 18 and rows.td.sum() == 2


def test_absent_formation_is_not_invented_and_invalid_export_labels_fail():
    source, context = inputs()
    rows = adapt(source[source.split_value.eq("shotgun")], context[context.shotgun.eq(1)])
    assert rows.split_value.eq("shotgun").all()
    source.loc[0, "split_value"] = "0"
    with pytest.raises(SourceError, match="invalid shotgun"):
        adapt(source, context)


def test_real_formation_exports_keep_reviewed_totals_and_field_specific_gaps():
    fixtures = Path(__file__).parent / "fixtures"
    record = json.loads((fixtures / "upstream_receiving_shotgun.json").read_text())
    source = pd.DataFrame(record["rows"], columns=record["columns"])
    context = pd.read_csv(fixtures / "upstream_receiving_context.csv")
    for year, players, expected in [
        (2006, ["00-0006101"], [(None, 73, 900, 5, 319, 54)]),
        (2009, ["00-0006101"], [(135, 83, 867, 6, 240, 54)]),
        (2024, ["00-0036322", "00-0039139"], [(154, 103, 1533, 10, 487, 62), (63, 52, 517, 4, 593, 24)]),
    ]:
        rows = adapt_receiving_splits(source[source.season.eq(year)],
                                      context=context[context.season.eq(year)], season=year,
                                      qualified_players=players, dimension="shotgun")
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
            jefferson = rows[rows.player_id.eq("00-0036322")]
            assert jefferson[["split_value", "cmp", "yards", "td"]].values.tolist() == [["shotgun", 77, 1041, 7], ["under_center", 26, 492, 3]]
            assert jefferson.epa.iloc[0] == 0.3666
