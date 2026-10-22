"""Official real subset controls and failure cases for incomplete receiving views."""
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.receiving_partition_validation import COUNT_FIELDS, validate_receiving_partition
from pipeline.snapshots import CandidateError


FIXTURE = Path(__file__).parent / "fixtures/upstream_receiving_partitions.json"
TABLES = ("context", "membership", "bucket_stats", "classified", "excluded", "overall")


def control(name="missing_pass_context"):
    case = json.loads(FIXTURE.read_text())[name]
    args = {key: case[key] for key in
            ("season", "buckets", "qualified_players", "source_revisions", "missing_reason")}
    args.update({key: pd.DataFrame(case[key]) for key in TABLES})
    context = args["context"]
    # Derive expected membership from the source values, independently of the
    # R producer's exported labels. These are controls, not new public views.
    if name == "missing_pass_context":
        context["split_value"] = context.pass_length.astype("string")
    else:
        rushers = context.n_pass_rushers
        context["split_value"] = pd.Series(pd.NA, index=context.index, dtype="string")
        context.loc[rushers.between(1, 4), "split_value"] = "standard_rush"
        context.loc[rushers.between(5, 11), "split_value"] = "blitz"
    return args


def test_real_missing_pass_depth_preserves_five_yard_catch_outside_classified_view():
    args = control()
    report = validate_receiving_partition(**args)
    assert args["context"].loc[0, ["game_id", "play_id"]].tolist() == ["2009_01_PHI_CAR", 4173]
    assert pd.isna(args["context"].loc[0, "pass_length"])
    assert report["status"] == "partial"
    assert report["plays"] == {"overall": 3, "classified": 2, "excluded": 1}
    assert report["qualified_production"]["classified"]["receiving_yards"] == 28
    assert report["qualified_production"]["excluded"]["receiving_yards"] == 5
    assert report["qualified_production"]["overall"]["receiving_yards"] == 33
    assert all(report["checks"].values())


def test_real_bad_charting_keeps_touchdown_and_player_with_no_classified_production():
    args = control("unusable_charting_field")
    report = validate_receiving_partition(**args)
    assert args["context"].loc[0, ["game_id", "play_id", "n_pass_rushers"]].tolist() == ["2024_07_HOU_GB", 981, 45]
    assert report["status"] == "partial"
    assert report["qualified_without_classified_production"] == ["00-0038996"]
    production = report["qualified_production"]
    assert (production["classified"]["receiving_yards"], production["excluded"]["receiving_yards"],
            production["overall"]["receiving_yards"]) == (27, 14, 41)
    assert production["excluded"]["receiving_tds"] == production["overall"]["receiving_tds"] == 1
    assert production["classified"]["receiving_tds"] == 0
    assert report["source_revisions"] == args["source_revisions"]


def test_same_grand_totals_do_not_allow_relabelled_play_ids():
    args = control()
    args["membership"].loc[[1, 2], "split_value"] = ["deep", "short"]
    with pytest.raises(CandidateError, match="independently classified play IDs"):
        validate_receiving_partition(**args)


@pytest.mark.parametrize("table", ["context", "membership"])
def test_duplicate_membership_cannot_multiply_credits(table):
    args = control()
    args[table] = pd.concat([args[table], args[table].iloc[[0]]], ignore_index=True)
    with pytest.raises(CandidateError, match="duplicate game/play"):
        validate_receiving_partition(**args)


@pytest.mark.parametrize("fault", ["missing", "extra", "different_game", "null_key", "invalid_bucket"])
def test_exact_game_and_play_scope_is_required(fault):
    args = control()
    frame = args["membership"]
    if fault == "missing":
        args["membership"] = frame.iloc[1:]
    elif fault == "extra":
        extra = frame.iloc[[0]].copy()
        extra["play_id"] = 999999
        args["membership"] = pd.concat([frame, extra], ignore_index=True)
    elif fault == "different_game":
        frame.loc[0, "game_id"] = "other-game"
    elif fault == "null_key":
        frame.loc[0, "game_id"] = None
    else:
        frame.loc[0, "split_value"] = "unknown"
    with pytest.raises(CandidateError):
        validate_receiving_partition(**args)


@pytest.mark.parametrize("table", ["bucket_stats", "classified", "excluded", "overall"])
def test_missing_or_duplicated_official_counts_fail_conservation(table):
    args = control()
    frame = args[table]
    index = frame.index[frame.receptions.gt(0)][0]
    frame.loc[index, "receiving_yards"] += 1
    with pytest.raises(CandidateError, match="differs for receiving_yards"):
        validate_receiving_partition(**args)


def test_per_player_check_rejects_error_hidden_by_matching_grand_total():
    args = control()
    frame = args["bucket_stats"]
    indices = frame.index[frame.receptions.gt(0)]
    frame.loc[indices[0], "receiving_yards"] += 1
    frame.loc[indices[1], "receiving_yards"] -= 1
    with pytest.raises(CandidateError, match="buckets versus classified"):
        validate_receiving_partition(**args)


def test_checks_run_before_qualification_filter_and_retain_unidentified_credits():
    args = control()
    args["qualified_players"] = ["00-0020337"]
    args["excluded"].loc[args["excluded"].receptions.gt(0), "player_id"] = None
    with pytest.raises(CandidateError, match="classified plus excluded"):
        validate_receiving_partition(**args)


def test_wholly_unavailable_context_keeps_whole_production_and_global_admission():
    args = control("unusable_charting_field")
    for table in ("context", "membership"):
        args[table]["split_value"] = pd.Series(pd.NA, index=args[table].index, dtype="string")
    args["bucket_stats"] = args["bucket_stats"].iloc[:0]
    args["classified"] = args["classified"].iloc[:0]
    args["excluded"] = args["overall"].copy()
    args["missing_reason"] = "optional charting feed unavailable for this scope"
    report = validate_receiving_partition(**args)
    assert report["status"] == "unavailable"
    assert report["plays"] == {"overall": 3, "classified": 0, "excluded": 3}
    assert report["qualified_without_classified_production"] == sorted(args["qualified_players"])
    assert report["qualified_production"]["overall"]["receiving_yards"] == 41
    assert report["qualified_production"]["classified"]["receiving_yards"] == 0


def test_complete_partition_still_requires_whole_scope_equality():
    args = control()
    for table in ("context", "membership"):
        args[table] = args[table].loc[args[table].split_value.notna()]
    args["excluded"] = args["excluded"].iloc[:0]
    args["overall"] = args["classified"].copy()
    report = validate_receiving_partition(**args)
    assert report["status"] == "complete"
    assert report["reason"] is None
    assert report["qualified_production"]["overall"] == report["qualified_production"]["classified"]


def test_production_cannot_be_assigned_to_a_bucket_without_member_plays():
    args = control()
    args["context"]["split_value"] = "short"
    args["membership"]["split_value"] = "short"
    with pytest.raises(CandidateError, match="no member plays"):
        validate_receiving_partition(**args)


def test_admission_cannot_silently_lose_a_player_from_whole_reference():
    args = control()
    args["qualified_players"].append("missing-eligible-player")
    with pytest.raises(CandidateError, match="qualified player missing from whole"):
        validate_receiving_partition(**args)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1.5, 2**31])
def test_unknown_or_invalid_counts_cannot_become_zero(value):
    args = control()
    args["excluded"]["receiving_yards"] = value
    with pytest.raises(CandidateError, match="finite integers"):
        validate_receiving_partition(**args)


@pytest.mark.parametrize("fault", ["postseason", "conversion", "year", "duplicate_summary", "missing_column", "missing_revision"])
def test_scope_contract_remains_strict(fault):
    args = control()
    if fault == "postseason":
        args["context"]["season_type"] = "POST"
    elif fault == "conversion":
        args["context"].loc[0, "two_point_attempt"] = 1
    elif fault == "year":
        args["overall"]["season"] = 2010
    elif fault == "duplicate_summary":
        args["excluded"] = pd.concat([args["excluded"], args["excluded"].iloc[[0]]], ignore_index=True)
    elif fault == "missing_column":
        args["classified"] = args["classified"].drop(columns=COUNT_FIELDS[0])
    else:
        args["source_revisions"] = {}
    with pytest.raises(CandidateError):
        validate_receiving_partition(**args)


def test_observed_arithmetic_does_not_remove_historical_target_masks():
    args = control()
    args["season"] = 2004
    for table in ("context", "bucket_stats", "classified", "excluded", "overall"):
        args[table]["season"] = 2004
    report = validate_receiving_partition(**args)
    assert report["qualified_production"]["overall"]["targets"] == 3
    assert report["historical_masks"] == {"targets_unavailable": True, "yac_unavailable": True}
    assert "not a metric completeness certificate" in report["count_scope"]


def test_lateral_recipient_without_target_or_catch_keeps_yards_and_touchdown():
    args = control()
    def row(player, targets, catches, yards, td, yac):
        return dict(player_id=player, season=2009, season_type="REG", targets=targets,
                    receptions=catches, receiving_yards=yards, receiving_tds=td,
                    receiving_yards_after_catch=yac, receiving_first_downs=0, receiving_air_yards=0)
    covered = pd.DataFrame([row("original", 1, 1, 5, 0, 5), row("lateral", 0, 0, 75, 1, 75)])
    omitted = pd.DataFrame([row("excluded", 1, 1, -2, 0, -2)])
    args.update(classified=covered, excluded=omitted,
                overall=pd.concat([covered, omitted], ignore_index=True),
                bucket_stats=covered.assign(split_value="short"),
                qualified_players=["original", "lateral", "excluded"])
    args["context"] = args["context"].iloc[:2].copy()
    args["context"]["split_value"] = pd.Series([pd.NA, "short"], dtype="string")
    args["membership"] = args["context"][["game_id", "play_id", "split_value"]].copy()
    report = validate_receiving_partition(**args)
    assert report["qualified_without_classified_production"] == ["excluded"]
    assert report["qualified_production"]["overall"]["receiving_yards"] == 78
    assert report["qualified_production"]["classified"]["receiving_tds"] == 1
