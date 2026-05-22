"""Unit tests for pure helper functions (no DB, no I/O)."""
from comparables_builder import (
    comp_pos_group as _comp_pos_group,
    cosine as _cosine,
    zscore_normalize as _zscore_normalize,
)
from routers.schedule import attach_records


# ── attach_records ───────────────────────────────────────────────────────────

def _game(week, away, home, a_sc, h_sc):
    return {"week": week, "away_team": away, "home_team": home,
            "away_score": a_sc, "home_score": h_sc}


def test_attach_records_empty():
    assert attach_records([]) == []


def test_attach_records_first_week_all_zero():
    games = [_game(1, "BUF", "MIA", 17, 24)]
    attach_records(games)
    # Before week 1 every team is 0-0; T omitted for 0
    assert games[0]["away_record"] == "0-0"
    assert games[0]["home_record"] == "0-0"


def test_attach_records_walks_weeks_in_order():
    games = [
        _game(1, "BUF", "MIA", 17, 24),   # MIA wins
        _game(2, "BUF", "MIA", 30, 14),   # BUF wins; entering, BUF 0-1 MIA 1-0
    ]
    attach_records(games)
    assert games[1]["away_record"] == "0-1"
    assert games[1]["home_record"] == "1-0"


def test_attach_records_counts_ties():
    games = [
        _game(1, "BUF", "MIA", 21, 21),   # tie
        _game(2, "BUF", "KC",  20, 10),   # entering: BUF 0-0-1
    ]
    attach_records(games)
    assert games[1]["away_record"] == "0-0-1"


def test_attach_records_handles_unfinished_games():
    games = [
        _game(1, "BUF", "MIA", 17, 24),
        _game(2, "BUF", "MIA", None, None),   # unfinished must not change records
        _game(3, "BUF", "MIA", 14, 7),
    ]
    attach_records(games)
    # Entering week 3, only week 1 has counted: BUF 0-1, MIA 1-0
    assert games[2]["away_record"] == "0-1"
    assert games[2]["home_record"] == "1-0"


# ── _comp_pos_group ──────────────────────────────────────────────────────────

def test_pos_group_explicit_position_wins():
    assert _comp_pos_group("QB", 0, 0, 0) == "QB"
    assert _comp_pos_group("RB", 0, 0, 0) == "RB"
    assert _comp_pos_group("FB", 0, 0, 0) == "RB"
    assert _comp_pos_group("WR", 0, 0, 0) == "WRTE"
    assert _comp_pos_group("TE", 0, 0, 0) == "WRTE"


def test_pos_group_falls_back_to_usage_for_unknown_position():
    # Lots of attempts -> QB
    assert _comp_pos_group(None, att=400, carries=20, tgts=0) == "QB"
    # Lots of carries -> RB
    assert _comp_pos_group(None, att=0, carries=200, tgts=5) == "RB"
    # Lots of targets -> WRTE
    assert _comp_pos_group(None, att=0, carries=0, tgts=80) == "WRTE"


def test_pos_group_returns_other_when_no_signal():
    assert _comp_pos_group(None, att=0, carries=0, tgts=0) == "OTHER"


# ── _zscore_normalize ────────────────────────────────────────────────────────

def test_zscore_normalize_centers_and_scales():
    vecs = [[1.0], [2.0], [3.0]]
    out = _zscore_normalize(vecs)
    # Mean 2, std ~0.8165 -> values are -1.22, 0, 1.22 (approx)
    assert abs(out[1][0]) < 1e-9
    assert out[0][0] < 0 and out[2][0] > 0
    assert abs(out[0][0] + out[2][0]) < 1e-9  # symmetric


def test_zscore_normalize_handles_zero_std():
    vecs = [[5.0], [5.0], [5.0]]
    out = _zscore_normalize(vecs)
    # All identical -> std=0 -> all output 0 (no division by zero)
    assert out == [[0.0], [0.0], [0.0]]


def test_zscore_normalize_empty_input():
    assert _zscore_normalize([]) == []


# ── _cosine ──────────────────────────────────────────────────────────────────

def test_cosine_identical_vectors():
    assert abs(_cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) - 1.0) < 1e-9


def test_cosine_orthogonal_vectors():
    assert abs(_cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_opposite_vectors():
    assert abs(_cosine([1.0, 1.0], [-1.0, -1.0]) + 1.0) < 1e-9


def test_cosine_zero_magnitude_returns_zero():
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine([1.0, 1.0], [0.0, 0.0]) == 0.0
