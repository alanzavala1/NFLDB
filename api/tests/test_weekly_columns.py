"""The weekly feed's columns, and what happens when one of them goes away.

nflverse renamed and moved the weekly stats feed once already. The cost was not
the rename — it was that nothing failed when the data stopped arriving. These
tests cover the two seams where that silence could come back.
"""
import re
import inspect

import duckdb
import pytest

import ingest


def test_required_list_matches_the_select_exactly():
    """Every col() call site is declared, and every declared name is read.

    Equality in both directions is the point. A new col() site that nobody adds
    to WEEKLY_STAT_COLUMNS is a column that can vanish upstream and silently
    resolve to zero — which is how passing_epa, rushing_epa, receiving_epa,
    receiving_air_yards and receiving_yards_after_catch were left unguarded.
    """
    src = inspect.getsource(ingest.build_offensive_stats_from_weekly)
    read = set(re.findall(r"col\(\s*'([a-z_]+)'", src))
    assert read == set(ingest.WEEKLY_STAT_COLUMNS)


def _table_with(conn, columns):
    cols = ", ".join(f"{c} VARCHAR" for c in columns)
    conn.execute(f"CREATE TABLE weekly_player_stats ({cols})")


def test_absent_table_falls_back_quietly():
    """No table at all is a legitimate state, not an error.

    A fresh database has no weekly stats, and build_player_game_stats is
    supposed to fall back to play-by-play. Only a table that EXISTS and is
    missing columns is a broken migration.
    """
    conn = duckdb.connect()
    assert ingest.build_offensive_stats_from_weekly(conn, [2024], log=lambda *a: None).empty


def test_missing_column_raises_instead_of_zeroing():
    conn = duckdb.connect()
    _table_with(conn, [c for c in ingest.WEEKLY_REQUIRED_COLUMNS if c != "passing_epa"])

    with pytest.raises(RuntimeError, match="passing_epa"):
        ingest.build_offensive_stats_from_weekly(conn, [2024], log=lambda *a: None)


def test_legacy_schema_raises_and_says_to_reingest():
    """The pre-stats_player table names, which are what a stale database holds.

    This is the case most likely to be hit by hand — a repair script pointed at
    a database that has not been re-ingested — so the message has to name the
    fix rather than just listing columns.
    """
    conn = duckdb.connect()
    legacy = ["player_id", "season", "week", "season_type", "recent_team",
              "completions", "attempts", "passing_yards", "passing_tds",
              "interceptions", "sacks", "passing_epa"]
    _table_with(conn, legacy)

    with pytest.raises(RuntimeError, match="re-run the ingest"):
        ingest.build_offensive_stats_from_weekly(conn, [2024], log=lambda *a: None)
