"""Unit tests for pure helper functions (no DB, no I/O)."""
from comparables_builder import (
    comp_pos_group as _comp_pos_group,
    cosine as _cosine,
    zscore_normalize as _zscore_normalize,
)


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
