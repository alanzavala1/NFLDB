"""The weekly feed loader: the columns it requires, and partial availability.

nflverse renamed and moved the weekly stats feed once already. The cost was not
the rename — it was that nothing failed when the data stopped arriving. These
tests cover the seams where that silence could come back.
"""
import re
import inspect

import duckdb
import pandas as pd
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


def _feed_frame(season: int, week: int = 1) -> pd.DataFrame:
    """One row shaped like the stats_player feed, valid enough to be ingested."""
    row = {c: 0.0 for c in ingest.WEEKLY_STAT_COLUMNS}
    row.update(player_id=f"00-000{season}", season=season, week=week,
               season_type="REG", team="KC")
    return pd.DataFrame([row])


def test_a_season_that_fails_to_download_is_not_deleted(monkeypatch):
    """A 404 on one season must not take that season's stored rows with it.

    _upsert_by_season DELETEs every season it is handed before inserting, so
    handing it the requested seasons rather than the retrieved ones turns a
    transient upstream gap into data loss. nflverse publishes a season as its
    games are charted, so asking for one that is not up yet is routine.
    """
    conn = duckdb.connect()
    seed = pd.concat([_feed_frame(2024), _feed_frame(2025)], ignore_index=True)
    conn.register("seed", seed)
    conn.execute("CREATE TABLE weekly_player_stats AS SELECT * FROM seed")

    def only_2024(url):
        if "2024" in url:
            return _feed_frame(2024, week=2)
        raise OSError("404 — not published yet")

    monkeypatch.setattr(ingest.pd, "read_parquet", only_2024)
    ingest.load_weekly_player_stats(conn, [2024, 2025], log=lambda *a, **k: None)

    stored = dict(conn.execute(
        "SELECT season, COUNT(*) FROM weekly_player_stats GROUP BY 1"
    ).fetchall())
    assert stored == {2024: 1, 2025: 1}, "the undownloaded season was dropped"
    assert conn.execute(
        "SELECT week FROM weekly_player_stats WHERE season = 2024"
    ).fetchone()[0] == 2, "the downloaded season was not replaced"


def test_no_seasons_available_leaves_the_table_alone(monkeypatch):
    conn = duckdb.connect()
    conn.register("seed", _feed_frame(2024))
    conn.execute("CREATE TABLE weekly_player_stats AS SELECT * FROM seed")

    monkeypatch.setattr(ingest.pd, "read_parquet",
                        lambda url: (_ for _ in ()).throw(OSError("404")))
    ingest.load_weekly_player_stats(conn, [2025], log=lambda *a, **k: None)

    assert conn.execute("SELECT COUNT(*) FROM weekly_player_stats").fetchone()[0] == 1
