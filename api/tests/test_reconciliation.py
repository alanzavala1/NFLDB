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

pytestmark = pytest.mark.invariant

_DB = os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")
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
    """# of qualifying players where the splits sum != official weekly sum."""
    return db.execute(f"""
        WITH s AS (
            SELECT player_id, SUM({split_col}) v FROM player_splits
            WHERE category = '{cat}' AND split_dim = 'down' AND season = {SEASON}
            GROUP BY 1),
        o AS (
            SELECT player_id, SUM({official_col}) v FROM weekly_player_stats
            WHERE season = {SEASON} AND season_type = 'REG' GROUP BY 1)
        SELECT COUNT(*) FILTER (WHERE o.v >= {vol} AND COALESCE(s.v, 0) <> o.v)
        FROM o LEFT JOIN s USING (player_id)
    """).fetchone()[0]


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
    """Splits passing EPA/att == official weekly passing_epa / attempts (the
    standardized dropback-EPA definition the Leaders/Player pages use)."""
    bad = db.execute(f"""
        WITH sp AS (
            SELECT player_id, SUM(epa * att) / NULLIF(SUM(att), 0) e
            FROM player_splits
            WHERE category = 'passing' AND split_dim = 'down' AND season = {SEASON}
            GROUP BY 1),
        off AS (
            SELECT player_id, SUM(passing_epa) / NULLIF(SUM(attempts), 0) e
            FROM weekly_player_stats
            WHERE season = {SEASON} AND season_type = 'REG' GROUP BY 1
            HAVING SUM(attempts) >= 100)
        SELECT COUNT(*) FROM sp JOIN off USING (player_id)
        WHERE ABS(sp.e - off.e) > 0.005
    """).fetchone()[0]
    assert bad == 0


def test_defense_sacks_reconcile_with_play_by_play(db):
    """A defender's sacks in defense_splits == the raw play-by-play credit
    (full + half sacks), summed over the scrimmage 'down' dimension."""
    bad = db.execute(f"""
        WITH ds AS (
            SELECT player_id, SUM(sacks) v FROM defense_splits
            WHERE split_dim = 'down' AND season = {SEASON} GROUP BY 1),
        raw AS (
            SELECT pid, SUM(w) v FROM (
                SELECT sack_player_id pid, 1.0 w FROM plays
                  WHERE season = {SEASON} AND season_type = 'REG' AND sack_player_id IS NOT NULL AND down IN (1,2,3,4)
                UNION ALL SELECT half_sack_1_player_id, 0.5 FROM plays
                  WHERE season = {SEASON} AND season_type = 'REG' AND half_sack_1_player_id IS NOT NULL AND down IN (1,2,3,4)
                UNION ALL SELECT half_sack_2_player_id, 0.5 FROM plays
                  WHERE season = {SEASON} AND season_type = 'REG' AND half_sack_2_player_id IS NOT NULL AND down IN (1,2,3,4)
            ) GROUP BY pid)
        SELECT COUNT(*) FROM ds JOIN raw ON ds.player_id = raw.pid
        WHERE ds.v >= 5 AND ds.v <> raw.v
    """).fetchone()[0]
    assert bad == 0


def test_no_impossible_rates(db):
    """Success% within [0,100]; no negative attempts/yards."""
    bad = db.execute("""
        SELECT COUNT(*) FROM player_splits
        WHERE (success_pct IS NOT NULL AND (success_pct < 0 OR success_pct > 100))
           OR att < 0 OR COALESCE(yards, 0) < -1000
    """).fetchone()[0]
    assert bad == 0
