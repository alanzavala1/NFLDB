"""Admission uses fresh unique attempt plays and the unchanged canonical rule."""
import duckdb
import pandas as pd
import pytest

from pipeline.receiving_qualification import qualify_receiving_context
from pipeline.snapshots import CandidateError
import splits_builder


REVISION = "a" * 64


def context(count=25, season=2024):
    return pd.DataFrame([dict(game_id="game", play_id=index, season=season,
                              season_type="REG", two_point_attempt=0,
                              receiver_player_id="receiver", complete_pass=1,
                              incomplete_pass=0, interception=0) for index in range(count)])


@pytest.mark.parametrize("count,admitted", [(24, False), (25, True), (26, True)])
def test_original_attempt_threshold_without_unrelated_split_columns(count, admitted):
    players, report = qualify_receiving_context(context(count), 2024, REVISION)
    assert players == (["receiver"] if admitted else [])
    assert report["qualifying_plays"] == ({"receiver": count} if admitted else {})
    assert report["source_revisions"] == {"context-2024.csv": REVISION}


def test_completions_incompletions_and_interceptions_count_but_sacks_and_unknown_receivers_do_not():
    frame = context(28)
    frame.loc[23:, "complete_pass"] = 0
    frame.loc[23, "incomplete_pass"] = 1
    frame.loc[24, "interception"] = 1
    frame["pass_attempt"] = 1  # Sacks can carry this provider flag; we don't use it.
    frame["sack"] = 0
    frame.loc[25:26, "sack"] = 1
    frame.loc[27, "complete_pass"] = 1
    frame.loc[27, "receiver_player_id"] = None
    players, report = qualify_receiving_context(frame, 2024, REVISION)
    assert players == ["receiver"]
    assert report["qualifying_plays"] == {"receiver": 25}


def test_historical_missing_official_targets_and_optional_context_do_not_change_admission():
    frame = context(season=2004)
    frame["targets"] = 0
    for field in ("down", "pass_length", "qb_hit", "is_play_action"):
        frame[field] = None
    players, _ = qualify_receiving_context(frame, 2004, REVISION)
    assert players == ["receiver"]


@pytest.mark.parametrize("fault", ["duplicate", "missing_key", "negative_id", "fractional_id",
                                  "bad_flag", "wrong_season", "postseason", "conversion",
                                  "missing_column", "bad_receiver", "empty"])
def test_bad_fresh_context_cannot_inflate_or_silently_change_qualification(fault):
    frame = context()
    if fault == "duplicate":
        frame = pd.concat([frame.iloc[:24], frame.iloc[[0]]], ignore_index=True)
    elif fault == "missing_key":
        frame.loc[0, "game_id"] = None
    elif fault == "negative_id":
        frame.loc[0, "play_id"] = -1
    elif fault == "fractional_id":
        frame["play_id"] = frame.play_id.astype(float)
        frame.loc[0, "play_id"] = 0.5
    elif fault == "bad_flag":
        frame.loc[0, "complete_pass"] = 2
    elif fault == "wrong_season":
        frame.loc[0, "season"] = 2004
    elif fault == "postseason":
        frame.loc[0, "season_type"] = "POST"
    elif fault == "conversion":
        frame.loc[0, "two_point_attempt"] = 1
    elif fault == "missing_column":
        frame = frame.drop(columns="interception")
    elif fault == "bad_receiver":
        frame.loc[0, "receiver_player_id"] = "  "
    else:
        frame = frame.iloc[:0]
    with pytest.raises(CandidateError):
        qualify_receiving_context(frame, 2024, REVISION)


def test_qualification_requires_a_bound_context_revision():
    with pytest.raises(CandidateError, match="verified context SHA256"):
        qualify_receiving_context(context(), 2024, "unverified")


@pytest.mark.parametrize("category", ["passing", "rushing", "receiving"])
def test_minimal_and_full_canonical_qualification_agree_for_all_categories(category):
    frame = context(55)
    frame["passer_player_id"] = "passer"
    frame["rusher_player_id"] = "rusher"
    for field in ("pass_attempt", "rush_attempt"):
        frame[field] = 1
    for field in ("sack", "down", "score_differential", "qtr", "shotgun", "yardline_100",
                  "first_down", "qb_hit", "no_huddle", "wp", "passing_yards", "pass_touchdown",
                  "air_yards", "yards_after_catch", "epa", "qb_epa", "cpoe", "receiving_yards",
                  "rushing_yards", "rush_touchdown"):
        frame[field] = 0
    for field in ("defteam", "pass_length", "pass_location", "posteam_type", "roof", "surface",
                  "play_type", "run_gap", "run_location"):
        frame[field] = None
    frame.loc[0:5, "season_type"] = "POST"
    frame.loc[6:10, "two_point_attempt"] = 1
    frame.loc[11:15, "season"] = 2023
    with duckdb.connect(":memory:") as conn:
        conn.register("plays", frame)
        def admitted(minimal):
            return conn.execute(splits_builder.qualification_ctes(category, 2024, set(frame.columns), minimal=minimal)
                                + " SELECT player_id FROM qualified ORDER BY player_id").fetchall()
        assert admitted(True) == admitted(False)
        assert admitted(True) == ([] if category == "passing" else
                                  [("rusher" if category == "rushing" else "receiver",)])
