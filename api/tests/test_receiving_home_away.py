"""Home/away uses each play's designated side, preserving credits and coverage."""
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
    rows = []
    for player, side, targets, catches, yards, td, yac, first, epa, air in [
        ("receiver", "away", 1, 1, 10, 1, 5, 1, 3.0, 5),
        ("receiver", "home", 2, 1, 8, 0, 6, 1, 1.0, 2),
        ("lateral", "home", 0, 0, 7, 1, 7, 0, None, 0),
    ]:
        rows.append(dict(player_id=player, season=season, season_type="REG", split_value=side,
                         recent_team="DDD", targets=targets, receptions=catches,
                         receiving_yards=yards, receiving_tds=td, receiving_yards_after_catch=yac,
                         receiving_first_downs=first, receiving_epa=epa, receiving_air_yards=air))
    context = pd.DataFrame([dict(game_id="neutral-game" if i < 2 else "later-game", play_id=i,
                                 season=season, season_type="REG", two_point_attempt=0,
                                 posteam_type="home" if i < 2 else "away",
                                 posteam="AAA" if i < 2 else "DDD",
                                 home_team="AAA" if i < 2 else "CCC",
                                 away_team="BBB" if i < 2 else "DDD",
                                 location="Neutral" if i < 2 else "Home",
                                 receiver_player_id="receiver", complete_pass=int(i != 1),
                                 incomplete_pass=int(i == 1), interception=0, epa=epa, air_yards=air)
                            for i, (epa, air) in enumerate([(2.0, 2), (-1.0, 0), (3.0, 5)])])
    return pd.DataFrame(rows), context


def adapt(source, context, season=2024):
    return adapt_receiving_splits(source, context=context, season=season,
                                  qualified_players=["receiver", "lateral"], dimension="home_away")


def test_designated_side_handles_neutral_games_trades_and_laterals_without_period_fields():
    source, context = inputs()
    rows = adapt(source, context)
    receiver = rows[rows.player_id.eq("receiver")]
    assert receiver.split_value.tolist() == ["home", "away"]
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
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac) FROM player_splits WHERE split_dim='home_away'").fetchone() == (3, 2, 25, 2, 18)


def test_historical_targets_are_unknown_without_erasing_home_away_production():
    source, context = inputs(2006)
    rows = adapt(source, context, 2006)
    assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
    assert rows.yards.sum() == 25 and rows.yac.sum() == 18 and rows.td.sum() == 2


@pytest.mark.parametrize("value", ["neutral", "HOME", "", " home ", 0])
def test_unrecognized_sides_fail_instead_of_falling_through_to_away(value):
    source, context = inputs()
    context["posteam_type"] = context.posteam_type.astype(object)
    context.loc[0, "posteam_type"] = value
    with pytest.raises(SourceError, match="invalid context posteam_type"):
        adapt(source, context)


def test_missing_side_stays_unknown_and_missing_context_column_fails():
    context = pd.DataFrame({"posteam_type": pd.Series([pd.NA, "home", "away"], dtype="string")})
    values = context_split_values(context, "home_away", 2024)
    assert pd.isna(values.iloc[0]) and values.iloc[1:].tolist() == ["home", "away"]
    source, context = inputs()
    with pytest.raises(SourceError, match="missing context posteam_type"):
        adapt(source, context.drop(columns="posteam_type"))


def test_missing_target_side_hides_only_affected_target_metrics():
    source, context = inputs()
    context.loc[0, "posteam_type"] = None
    rows = adapt(source, context)
    home = rows[rows.player_id.eq("receiver") & rows.split_value.eq("home")].iloc[0]
    assert [home.att, home.cmp, home.yards] == [2, 1, 8]
    assert pd.isna(home.epa) and pd.isna(home.success_pct) and pd.isna(home.air_yards)
    assert rows[rows.player_id.eq("receiver") & rows.split_value.eq("away")].epa.iloc[0] == 3.0


def test_absent_side_is_not_invented_and_invalid_export_label_fails():
    source, context = inputs()
    rows = adapt(source[source.split_value.eq("home")], context[context.posteam_type.eq("home")])
    assert rows.split_value.eq("home").all()
    source.loc[0, "split_value"] = "neutral"
    with pytest.raises(SourceError, match="invalid home_away"):
        adapt(source, context)


def test_real_exports_keep_traded_player_and_neutral_game_designations():
    fixtures = Path(__file__).parent / "fixtures"
    record = json.loads((fixtures / "upstream_receiving_home_away.json").read_text())
    source = pd.DataFrame(record["rows"], columns=record["columns"])
    context = pd.read_csv(fixtures / "upstream_receiving_context.csv")
    for year, players, expected in [
        (2006, ["00-0006101"], [(None, 73, 900, 5, 319, 54)]),
        (2024, ["00-0031544", "00-0036322", "00-0039139"],
         [(85, 44, 547, 4, 111, 25), (154, 103, 1533, 10, 487, 62), (63, 52, 517, 4, 593, 24)]),
    ]:
        rows = adapt_receiving_splits(source[source.season.eq(year)],
                                      context=context[context.season.eq(year)], season=year,
                                      qualified_players=players, dimension="home_away")
        with duckdb.connect(":memory:") as conn:
            splits_builder.ensure_table(conn)
            conn.register("split_rows", rows)
            conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM split_rows")
            assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td),SUM(yac),SUM(first_downs) FROM player_splits GROUP BY player_id ORDER BY player_id").fetchall() == expected
        if year == 2006:
            assert rows[["att", "epa", "success_pct", "air_yards"]].isna().all().all()
        else:
            cooper_context = context[context.season.eq(year) & context.receiver_player_id.eq("00-0031544")]
            assert set(cooper_context.posteam) == {"BUF", "CLE"}
            cooper = rows[rows.player_id.eq("00-0031544")]
            assert cooper[["split_value", "cmp", "yards", "td"]].values.tolist() == [["home", 22, 301, 4], ["away", 22, 246, 0]]
            neutral = context[context.game_id.eq("2024_05_NYJ_MIN") & context.receiver_player_id.eq("00-0036322")]
            assert not neutral.empty and neutral.location.eq("Neutral").all()
            assert neutral.posteam_type.eq("home").all() and neutral.posteam.eq(neutral.home_team).all()
