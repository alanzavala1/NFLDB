"""Definitions, missing populations and recipient attribution for remaining views."""
import duckdb
import pandas as pd
import pytest

from pipeline.receiving_dimensions import context_split_values
from pipeline.receiving_splits import adapt_receiving_splits
from pipeline.source_results import SourceError
import splits_builder


def values(dim, field, data, season=2024):
    return context_split_values(pd.DataFrame({field: data}), dim, season)


def test_win_probability_boundaries_and_unknowns():
    result = values("game_state", "wp", [0, .0499, .05, .95, .9501, 1, None])
    assert result.iloc[:6].tolist() == ["garbage", "garbage", "competitive", "competitive", "garbage", "garbage"]
    assert pd.isna(result.iloc[6])
    for invalid in (-.1, 1.1, float("inf"), "bad"):
        with pytest.raises(SourceError):
            values("game_state", "wp", [invalid])


def test_environment_maps_preserve_reviewed_legacy_aliases_and_exclude_unknowns():
    roofs = values("roof", "roof", ["dome", "closed", "open", "outdoors", "unknown", "", None])
    assert roofs.iloc[:4].tolist() == ["dome", "dome", "outdoors", "outdoors"]
    assert roofs.iloc[4:].isna().all()
    surfaces = values("surface", "surface", ["grass", "dessograss", "a_turf", "fieldturf", "", "new material", None])
    assert surfaces.iloc[:4].tolist() == ["grass", "turf", "turf", "turf"]
    assert surfaces.iloc[4:].isna().all()


@pytest.mark.parametrize("season,raw,expected", [
    (2016, "LAC", "SD"), (2017, "SD", "LAC"), (2015, "LA", "STL"),
    (2016, "STL", "LA"), (2019, "LV", "OAK"), (2020, "OAK", "LV"), (2001, "JAC", "JAX"),
])
def test_opponent_aliases_are_season_sensitive(season, raw, expected):
    assert values("opponent", "defteam", [raw], season).iloc[0] == expected


def test_division_explicitly_preserves_current_franchise_alignment_before_realignment():
    assert values("opp_division", "defteam", ["SEA", "IND", "OAK"], 2001).tolist() == ["NFC West", "AFC South", "AFC West"]
    assert values("opponent", "defteam", [None, ""]).isna().all()
    with pytest.raises(SourceError, match="defteam"):
        values("opponent", "defteam", ["XXX"])


@pytest.mark.parametrize("dimension,field,good", [
    ("target_depth", "pass_length", ["short", "deep"]),
    ("target_direction", "pass_location", ["left", "middle", "right"]),
])
def test_original_pass_context_labels_remain_explicit(dimension, field, good):
    result = values(dimension, field, [*good, None, ""])
    assert result.iloc[:len(good)].tolist() == good
    assert result.iloc[len(good):].isna().all()
    with pytest.raises(SourceError):
        values(dimension, field, ["invented"])


def test_qb_hit_is_not_certified_clean_pocket_and_early_zeros_are_unavailable():
    assert values("pressure", "qb_hit", [0, 1, None]).iloc[:2].tolist() == ["clean", "pressured"]
    assert values("pressure", "qb_hit", [0, 1, None], 2004).isna().all()
    with pytest.raises(SourceError):
        values("pressure", "qb_hit", [2])


def test_charting_distinguishes_false_missing_and_out_of_range():
    assert values("play_action", "is_play_action", [True, False, None]).iloc[:2].tolist() == ["play_action", "no_pa"]
    counts = values("blitz", "n_pass_rushers", [1, 4, 5, 11, 0, 45, None])
    assert counts.iloc[:4].tolist() == ["standard_rush", "standard_rush", "blitz", "blitz"]
    assert counts.iloc[4:].isna().all()
    assert values("blitz", "n_pass_rushers", [4, 5], 2009).isna().all()
    assert values("play_action", "is_play_action", [1, 0], 2009).isna().all()
    with pytest.raises(SourceError):
        values("blitz", "n_pass_rushers", [4.5])


@pytest.mark.parametrize("dim,bucket", [
    ("game_state", "competitive"), ("roof", "outdoors"), ("surface", "grass"),
    ("opponent", "LV"), ("opp_division", "AFC West"), ("target_depth", "short"),
    ("target_direction", "left"), ("pressure", "pressured"),
    ("play_action", "play_action"), ("blitz", "blitz"),
])
def test_all_new_views_retain_zero_target_lateral_credits_and_original_target_rates(dim, bucket):
    context = pd.DataFrame([dict(game_id="game", play_id=1, season=2024, season_type="REG", two_point_attempt=0,
                                receiver_player_id="receiver", complete_pass=1, incomplete_pass=0, interception=0,
                                epa=.5, air_yards=8, wp=.5, roof="open", surface="grass", defteam="OAK",
                                pass_length="short", pass_location="left", qb_hit=1, is_play_action=1, n_pass_rushers=5)])
    base = dict(season=2024, season_type="REG", split_value=bucket, receiving_first_downs=0)
    source = pd.DataFrame([
        dict(base, player_id="receiver", targets=1, receptions=1, receiving_yards=8, receiving_tds=0,
             receiving_yards_after_catch=0, receiving_epa=.5, receiving_air_yards=8),
        dict(base, player_id="lateral", targets=0, receptions=0, receiving_yards=2, receiving_tds=1,
             receiving_yards_after_catch=2, receiving_epa=None, receiving_air_yards=0),
    ])
    rows = adapt_receiving_splits(source, context=context, season=2024, qualified_players=["receiver", "lateral"], dimension=dim)
    assert rows.split_value.eq(bucket).all()
    receiver = rows.loc[rows.player_id.eq("receiver")].iloc[0]
    lateral = rows.loc[rows.player_id.eq("lateral")].iloc[0]
    assert receiver.epa == .5 and receiver.success_pct == 100
    assert lateral.yards == 2 and lateral.td == 1 and lateral.att == 0 and lateral.cmp == 0
    assert pd.isna(lateral.epa) and pd.isna(lateral.success_pct) and lateral.air_yards == 0
    if dim == "opponent":
        assert rows.sort_order.isna().all()
    with duckdb.connect(":memory:") as conn:
        splits_builder.ensure_table(conn)
        conn.register("rows", rows)
        conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM rows")
        assert conn.execute("SELECT SUM(att),SUM(cmp),SUM(yards),SUM(td) FROM player_splits").fetchone() == (1, 1, 10, 1)
