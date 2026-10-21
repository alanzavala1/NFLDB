"""Quarter partitions use play periods, preserve lateral production and share rate rules."""
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pipeline.receiving_splits import adapt_receiving_splits
from pipeline.receiving_dimensions import context_split_values
from pipeline.source_results import SourceError
import splits_builder


def inputs(season=2024):
    rows = []
    for player, bucket, targets, catches, yards, td, yac, first, epa, air in [
        ("receiver", "OT", 2, 1, 12, 0, 10, 1, 2.0, 2),
        ("receiver", "4", 1, 1, 8, 0, -2, 0, 2.0, 10),
        ("lateral", "OT", 0, 0, 7, 1, 7, 0, None, 0),
    ]:
        rows.append(dict(player_id=player, season=season, season_type="REG", split_value=bucket,
                         targets=targets, receptions=catches, receiving_yards=yards, receiving_tds=td,
                         receiving_yards_after_catch=yac, receiving_first_downs=first,
                         receiving_epa=epa, receiving_air_yards=air))
    context = pd.DataFrame([dict(game_id="game", play_id=index, season=season, season_type="REG",
                                 two_point_attempt=0, qtr=qtr, down=down,
                                 receiver_player_id="receiver", complete_pass=int(index != 1),
                                 incomplete_pass=int(index == 1), interception=0, epa=epa, air_yards=air)
                            for index, (qtr, down, epa, air) in enumerate([
                                (4, 2, 2.0, 10), (5, None, -1.0, -2), (6, 3, 3.0, 4)])])
    return pd.DataFrame(rows), context


def adapt(source, context, season=2024):
    return adapt_receiving_splits(source, context=context, season=season,
                                  qualified_players=["receiver", "lateral"], dimension="quarter")


def test_overtime_periods_share_one_bucket_and_missing_down_does_not_drop_targets():
    source, context = inputs()
    rows = adapt(source, context)
    receiver = rows[rows.player_id.eq("receiver")]
    assert receiver.split_value.tolist() == ["4", "OT"]
    assert receiver.sort_order.tolist() == [4, 5]
    overtime = receiver[receiver.split_value.eq("OT")].iloc[0]
    assert [overtime.att, overtime.cmp, overtime.yards, overtime.epa, overtime.success_pct, overtime.air_yards] == [2, 1, 12, 1.0, 50.0, 2]
    lateral = rows[rows.player_id.eq("lateral")].iloc[0]
    assert [lateral.att, lateral.cmp, lateral.yards, lateral.td, lateral.yac, lateral.air_yards] == [0, 0, 7, 1, 7, 0]
    assert pd.isna(lateral.epa) and pd.isna(lateral.success_pct)
    with duckdb.connect(":memory:") as conn:
        splits_builder.ensure_table(conn)
        conn.register("quarter_rows", rows)
        conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM quarter_rows")
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td) FROM player_splits WHERE split_dim='quarter'").fetchone() == (3, 2, 27, 1)


def test_historical_target_gap_does_not_erase_quarter_YAC_or_production():
    source, context = inputs(2006)
    rows = adapt(source, context, 2006)
    assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
    assert rows.yards.sum() == 27 and rows.yac.sum() == 15 and rows.td.sum() == 1


@pytest.mark.parametrize("value", [0, -1, 1.5, float("inf"), "bad"])
def test_invalid_periods_fail_instead_of_becoming_overtime(value):
    source, context = inputs()
    context = context.astype(object)
    context.loc[0, "qtr"] = value
    with pytest.raises(SourceError):
        adapt(source, context)


def test_quarter_requires_its_own_context_and_rejects_unrecognized_buckets():
    source, context = inputs()
    with pytest.raises(SourceError, match="missing context qtr"):
        adapt(source, context.drop(columns="qtr"))
    source.loc[0, "split_value"] = "5"
    with pytest.raises(SourceError, match="invalid quarter"):
        adapt(source, context)
    with pytest.raises(SourceError, match="unsupported split dimension"):
        adapt_receiving_splits(source, context=context, season=2024, qualified_players=[], dimension="other")


def test_absent_overtime_bucket_is_not_invented():
    source, context = inputs()
    rows = adapt(source[source.split_value.eq("4")], context[context.qtr.eq(4)])
    assert rows.split_value.tolist() == ["4"]


def test_unknown_nullable_period_is_not_mislabeled_as_overtime():
    context = pd.DataFrame({"qtr": pd.Series([pd.NA, 5], dtype="Int64")})
    result = context_split_values(context, "quarter", 2024)
    assert pd.isna(result.iloc[0]) and result.iloc[1] == "OT"


def test_real_quarter_exports_conserve_reviewed_counts_and_retain_overtime():
    fixtures = Path(__file__).parent / "fixtures"
    record = json.loads((fixtures / "upstream_receiving_quarter.json").read_text())
    source = pd.DataFrame(record["rows"], columns=record["columns"])
    context = pd.read_csv(fixtures / "upstream_receiving_rate_context.csv")
    for year, players, expected in [
        (2006, ["00-0006101"], [(None, 73, 900, 5, 319, 54)]),
        (2024, ["00-0036322", "00-0039139"], [(154, 103, 1533, 10, 487, 62), (63, 52, 517, 4, 593, 24)]),
    ]:
        rows = adapt_receiving_splits(source[source.season.eq(year)],
                                      context=context[context.season.eq(year)], season=year,
                                      qualified_players=players, dimension="quarter")
        with duckdb.connect(":memory:") as conn:
            splits_builder.ensure_table(conn)
            conn.register("quarter_rows", rows)
            conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM quarter_rows")
            assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac),SUM(first_downs) FROM player_splits GROUP BY player_id ORDER BY player_id").fetchall() == expected
        if year == 2006:
            assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
        else:
            jefferson = rows[rows.player_id.eq("00-0036322") & rows.split_value.eq("OT")].iloc[0]
            assert [jefferson.att, jefferson.cmp, jefferson.yards, jefferson.air_yards, jefferson.epa, jefferson.success_pct] == [1, 1, 20, 11, 1.4133, 100.0]
