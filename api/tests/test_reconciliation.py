"""Data-reconciliation invariants against the REAL materialized database.

These encode the project's core accuracy promise: the situational `player_splits`
and `defense_splits` (derived from play-by-play) must reconcile *exactly* with
the official nflfastR weekly stats for counting categories, and the standardized
passing EPA must match the league-leaders definition.

They run only when the real on-disk DuckDB is present (locally / inside the
built image) and skip cleanly otherwise (CI on a fresh checkout has no 400MB
DB). Run them against the image before deploy to gate a release on data
integrity. See reconciliation work in commits d4106d6 (counts) and 309a1fc (EPA).
"""
import os

import duckdb
import pytest

from pipeline.reconciliation import (
    count_mismatches, passing_epa_mismatches, defensive_sack_mismatches, impossible_rates,
)

pytestmark = pytest.mark.invariant

# Honours NFL_DB_PATH, the same override database.py reads, so the gate can be
# pointed at a candidate database. Without it these tests could only ever check
# the copy already in the tree — which silently made a migration look verified
# when the run had in fact read the pre-migration data.
_DB = os.environ.get(
    "NFL_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")
)
SEASON = 2023  # a complete season with full official weekly data


@pytest.fixture(scope="module")
def db():
    if not os.path.exists(_DB):
        pytest.skip("real nfl.duckdb not present (CI / fresh checkout)")
    con = duckdb.connect(_DB, read_only=True)
    tabs = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    need = {"player_splits", "defense_splits", "weekly_player_stats", "player_game_stats"}
    if not need <= tabs:
        con.close()
        pytest.skip(f"required tables not materialized: missing {need - tabs}")
    yield con
    con.close()


def _count_mismatch(db, cat, split_col, official_col, vol):
    return count_mismatches(db, SEASON, cat, split_col, official_col, vol)


@pytest.mark.parametrize("cat,col,official,vol", [
    ("passing",   "att", "attempts", 100),
    ("rushing",   "att", "carries",  50),
    ("receiving", "att", "targets",  40),
])
def test_split_counts_match_official_exactly(db, cat, col, official, vol):
    """Counting stats (attempts/carries/targets) must reconcile to the play."""
    assert _count_mismatch(db, cat, col, official, vol) == 0


def test_passing_yards_match_official_exactly(db):
    """Passing yards reconcile to the yard."""
    assert _count_mismatch(db, "passing", "yards", "passing_yards", 1000) == 0


@pytest.mark.parametrize("cat,official,vol,tol", [
    ("rushing",   "rushing_yards",   300, 2),
    ("receiving", "receiving_yards", 300, 6),
])
def test_rush_rec_yards_within_lateral_credit_tolerance(db, cat, official, vol, tol):
    """Rushing/receiving yard *totals* can differ by 1-3 yards for a handful of
    players because nflfastR credits lateral/multi-player yardage differently —
    bounded and inherent to play-by-play, not a regression. The counting stats
    (carries/targets) are still exact (tested above)."""
    assert _count_mismatch(db, cat, "yards", official, vol) <= tol


def test_passing_epa_matches_leaders_definition(db):
    assert passing_epa_mismatches(db, SEASON) == 0


def test_defense_sacks_reconcile_with_play_by_play(db):
    assert defensive_sack_mismatches(db, SEASON) == 0


def test_no_impossible_rates(db):
    assert impossible_rates(db) == 0
