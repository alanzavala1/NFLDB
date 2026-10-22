"""Game script uses the offense's pre-play score, retaining all recipient credits."""
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
        ("receiver", "leading", 1, 1, 20, 1, 15, 1, 3.0, 5),
        ("receiver", "trailing", 1, 1, 68, 0, 48, 1, 4.0, 20),
        ("receiver", "tied", 1, 0, 0, 0, 0, 0, -1.0, 30),
        ("lateral", "trailing", 0, 0, 7, 1, 7, 0, None, 0),
    ]])
    context = pd.DataFrame([dict(
        game_id="game", play_id=index, season=season, season_type="REG",
        two_point_attempt=0, score_differential=score, score_differential_post=7,
        receiver_player_id="receiver", complete_pass=int(index != 1),
        incomplete_pass=int(index == 1), interception=0, epa=epa, air_yards=air,
    ) for index, (score, epa, air) in enumerate([(-3, 4.0, 20), (0, -1.0, 30), (7, 3.0, 5)])])
    return source, context


def adapt(source, context, season=2024):
    return adapt_receiving_splits(source, context=context, season=season,
                                  qualified_players=["receiver", "lateral"], dimension="game_script")


def test_offense_preplay_state_retains_lateral_touchdown_even_when_play_changes_lead():
    source, context = inputs()
    rows = adapt(source, context)
    receiver = rows[rows.player_id.eq("receiver")]
    assert receiver.split_value.tolist() == ["leading", "tied", "trailing"]
    assert receiver.sort_order.tolist() == [1, 2, 3]
    assert receiver.epa.tolist() == [3.0, -1.0, 4.0]
    assert receiver.success_pct.tolist() == [100.0, 0.0, 100.0]
    lateral = rows[rows.player_id.eq("lateral")].iloc[0]
    assert [lateral.split_value, lateral.att, lateral.cmp, lateral.yards, lateral.td, lateral.yac] == ["trailing", 0, 0, 7, 1, 7]
    assert pd.isna(lateral.epa) and pd.isna(lateral.success_pct) and lateral.air_yards == 0
    with duckdb.connect(":memory:") as conn:
        splits_builder.ensure_table(conn)
        conn.register("split_rows", rows)
        conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM split_rows")
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac) FROM player_splits").fetchone() == (3, 2, 95, 2, 70)


def test_score_sign_and_nullable_unknown_never_default_to_tied_or_trailing():
    context = pd.DataFrame({"score_differential": pd.Series([-7, -1, 0, 1, 7, pd.NA], dtype="Float64")})
    values = context_split_values(context, "game_script", 2024)
    assert values.iloc[:5].tolist() == ["trailing", "trailing", "tied", "leading", "leading"]
    assert pd.isna(values.iloc[5])


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), 0.5, "unknown", 2**31])
def test_invalid_score_cannot_silently_become_a_game_state(value):
    context = pd.DataFrame({"score_differential": [value]})
    with pytest.raises(SourceError, match="invalid context score_differential"):
        context_split_values(context, "game_script", 2024)


def test_required_score_column_and_bucket_labels_are_checked():
    source, context = inputs()
    with pytest.raises(SourceError, match="missing context score_differential"):
        adapt(source, context.drop(columns="score_differential"))
    source.loc[0, "split_value"] = "winning"
    with pytest.raises(SourceError, match="invalid game_script"):
        adapt(source, context)


def test_historical_target_gaps_do_not_erase_receiving_production_or_YAC():
    source, context = inputs(2006)
    rows = adapt(source, context, 2006)
    assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
    assert [rows.cmp.sum(), rows.yards.sum(), rows.td.sum(), rows.yac.sum()] == [2, 95, 2, 70]


def test_absent_buckets_are_not_invented_and_other_missing_context_is_irrelevant():
    source, context = inputs()
    context["down"] = None
    context["qtr"] = None
    rows = adapt(source[source.split_value.eq("tied")], context[context.score_differential.eq(0)])
    assert rows.split_value.tolist() == ["tied"]
    assert rows.epa.iloc[0] == -1.0


def test_real_official_game_scripts_preserve_season_counts_and_field_specific_gaps():
    fixtures = Path(__file__).parent / "fixtures"
    record = json.loads((fixtures / "upstream_receiving_game_script.json").read_text())
    source = pd.DataFrame(record["rows"], columns=record["columns"])
    context = pd.read_csv(fixtures / "upstream_receiving_context.csv")
    for year, players, expected in [
        (2006, ["00-0006101"], [(None, 73, 900, 5, 319, 54)]),
        (2009, ["00-0006101"], [(135, 83, 867, 6, 240, 54)]),
        (2024, ["00-0036322", "00-0039139"], [(154, 103, 1533, 10, 487, 62), (63, 52, 517, 4, 593, 24)]),
    ]:
        rows = adapt_receiving_splits(source[source.season.eq(year)],
                                      context=context[context.season.eq(year)], season=year,
                                      qualified_players=players, dimension="game_script")
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
