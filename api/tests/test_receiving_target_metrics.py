"""Rates retain their target population and never turn unknown EPA into failure."""
import pandas as pd
import pytest

from pipeline.receiving_target_metrics import receiving_target_metrics
from pipeline.source_results import SourceError


def inputs():
    source = pd.DataFrame([dict(player_id="receiver", split_value="1", targets=3,
                                receiving_epa=1.0, receiving_air_yards=3)])
    context = pd.DataFrame([dict(game_id="game", play_id=i, season=2024,
                                 season_type="REG", two_point_attempt=0, down=1,
                                 receiver_player_id="receiver", complete_pass=int(i == 0),
                                 incomplete_pass=int(i == 1), interception=int(i == 2), epa=epa,
                                 air_yards=[2, 0, 1][i])
                            for i, epa in enumerate([2.0, 0.0, -1.0])])
    return source, context


def test_target_role_includes_incompletions_and_interceptions_and_zero_is_not_success():
    source, context = inputs()
    result = receiving_target_metrics(source, context, 2024)
    assert result.iloc[0].tolist() == [0.3333, 33.3, 3]
    # The same plays may contain another credited lateral player. That player
    # has no original target population, so neither rate belongs to them.
    source.loc[1] = ["lateral", "1", 0, None, 0]
    result = receiving_target_metrics(source, context, 2024)
    assert result.loc[1, ["epa", "success_pct"]].isna().all()
    assert result.loc[1, "air_yards"] == 0


@pytest.mark.parametrize("fault", ["missing_epa", "target_mismatch", "missing_target", "historical"])
def test_incomplete_populations_hide_only_rates(fault):
    source, context = inputs()
    season = 2024
    if fault == "missing_epa":
        context.loc[1, "epa"] = None
    elif fault == "target_mismatch":
        source["targets"] = 4
    elif fault == "missing_target":
        context.loc[1, "receiver_player_id"] = None
    else:
        season = 2006
        context["season"] = season
    before = source.copy(deep=True)
    assert receiving_target_metrics(source, context, season)[["epa", "success_pct"]].isna().all().all()
    pd.testing.assert_frame_equal(source, before)


def test_different_official_epa_numerator_does_not_erase_verified_success():
    source, context = inputs()
    source["receiving_epa"] = 5.0
    result = receiving_target_metrics(source, context, 2024)
    assert pd.isna(result.epa.iloc[0])
    assert result.success_pct.iloc[0] == 33.3


def test_missing_official_epa_is_not_zero_and_negative_rates_remain_valid():
    source, context = inputs()
    source["receiving_epa"] = None
    assert pd.isna(receiving_target_metrics(source, context, 2024).epa.iloc[0])
    context["epa"] = -1.0
    source["receiving_epa"] = -3.0
    assert receiving_target_metrics(source, context, 2024).iloc[0].tolist() == [-1.0, 0.0, 3]


@pytest.mark.parametrize("column,value", [
    ("epa", float("inf")), ("epa", "bad"), ("season", 2004),
    ("season_type", "POST"), ("two_point_attempt", 1),
    ("complete_pass", 3), ("down", 5), ("game_id", None),
    ("receiver_player_id", " padded "),
])
def test_malformed_context_fails_instead_of_becoming_missing_data(column, value):
    source, context = inputs()
    context = context.astype(object)
    context.loc[0, column] = value
    with pytest.raises(SourceError):
        receiving_target_metrics(source, context, 2024)


def test_duplicate_plays_and_missing_context_columns_fail():
    source, context = inputs()
    for bad in (pd.concat([context, context.iloc[:1]]), context.drop(columns="epa")):
        with pytest.raises(SourceError):
            receiving_target_metrics(source, bad, 2024)


def test_no_original_receiver_population_has_no_rate():
    source, context = inputs()
    assert receiving_target_metrics(source, context.iloc[:0], 2024).isna().all().all()


def test_missing_air_masks_only_air_without_treating_it_as_zero():
    source, context = inputs()
    context.loc[1, "air_yards"] = None
    result = receiving_target_metrics(source, context, 2024)
    assert pd.isna(result.air_yards.iloc[0])
    assert result.epa.iloc[0] == 0.3333 and result.success_pct.iloc[0] == 33.3


def test_missing_epa_does_not_erase_complete_air_yards():
    source, context = inputs()
    context.loc[1, "epa"] = None
    result = receiving_target_metrics(source, context, 2024)
    assert result.air_yards.iloc[0] == 3
    assert result[["epa", "success_pct"]].isna().all().all()


def test_air_numerator_disagreement_masks_only_air():
    source, context = inputs()
    source["receiving_air_yards"] = 4
    result = receiving_target_metrics(source, context, 2024)
    assert pd.isna(result.air_yards.iloc[0])
    assert result.epa.iloc[0] == 0.3333


@pytest.mark.parametrize("value", [-6, 0])
def test_negative_and_zero_air_are_observations_not_gaps(value):
    source, context = inputs()
    context["air_yards"] = value
    source["receiving_air_yards"] = 3 * value
    assert receiving_target_metrics(source, context, 2024).air_yards.iloc[0] == 3 * value


@pytest.mark.parametrize("column,value", [("air_yards", float("inf")), ("air_yards", 1.5),
                                         ("air_yards", "bad"), ("air_yards", 2**31),
                                         ("receiving_air_yards", None), ("receiving_air_yards", 0.5)])
def test_malformed_air_values_fail_even_if_coverage_would_be_masked(column, value):
    source, context = inputs()
    frame = source if column.startswith("receiving_") else context
    frame[column] = frame[column].astype(object)
    frame.loc[0, column] = value
    context["season"] = 2006
    with pytest.raises(SourceError):
        receiving_target_metrics(source, context, 2006)
