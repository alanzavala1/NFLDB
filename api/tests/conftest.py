"""Test fixtures: in-memory DuckDB seeded with a mini-league.

The seed is intentionally small but exercises every interesting case:

  - Multiple weeks (records walked over time)
  - Tied games (T column non-zero)
  - Divisional games (div_w / div_l counted separately)
  - Home-underdog upset (spread_line > 0 means home favored; if home wins,
    not an upset; if away wins, the upset detector should fire)
  - Blowout (margin >= 28)
  - Unfinished games (NULL scores)
  - Mid-season state (some teams have more completed games than others)

The fixture replaces database._conn with this in-memory connection, so the
real FastAPI app sees test data without any code change in routers.
"""
import os

# Pin the test DB path before importing the app so the lifespan auto-ingest
# doesn't try to talk to the real on-disk DuckDB file. The app reads DB_PATH
# at first connect, but we'll monkey-patch the connection directly anyway.
os.environ.setdefault("NFL_TEST_MODE", "1")

import duckdb
import pytest
from fastapi.testclient import TestClient


# ── Seed data ────────────────────────────────────────────────────────────────

SEASON = 2024

# (week, away, home, away_score, home_score, spread_line, div_game, game_type)
# spread_line convention (nflfastR): POSITIVE = home favored.
GAMES = [
    (1, "BUF", "MIA", 17,   24,   -3.5, 1, "REG"),  # MIA home underdog wins → upset
    (1, "DEN", "KC",  14,   42,   10.0, 1, "REG"),  # KC home favored by 10, wins by 28 → blowout
    (2, "KC",  "BUF", 21,   21,    1.5, 0, "REG"),  # tied thriller (BUF home, slightly favored)
    (2, "MIA", "DEN", 28,   27,   -2.0, 0, "REG"),  # MIA away wins by 1 → closest non-tie
    (3, "BUF", "DEN", 30,   24,   -4.0, 0, "REG"),  # BUF away favored wins
    (3, "KC",  "MIA", None, None,  1.0, 0, "REG"),  # unfinished
]

# Roster: one QB per team, plus one WR per team to give /leaders more rows.
ROSTER = [
    # player_id,    name,                position, team, jersey, height, weight
    ("00-BUF-QB1",  "Josh Allen",        "QB",     "BUF", 17, 77, 237),
    ("00-MIA-QB1",  "Tua Tagovailoa",    "QB",     "MIA",  1, 73, 217),
    ("00-KC-QB1",   "Patrick Mahomes",   "QB",     "KC",  15, 74, 230),
    ("00-DEN-QB1",  "Bo Nix",            "QB",     "DEN", 10, 74, 217),
    ("00-BUF-WR1",  "Stefon Diggs",      "WR",     "BUF", 14, 72, 191),
    ("00-MIA-WR1",  "Tyreek Hill",       "WR",     "MIA", 10, 70, 191),
]

# (game_id, player_id, week, team, pass_yds, pass_tds, ints, cmp, att, rec_yds, rec_tds, rec, tgts)
# Build per-finished-game stats. Each QB's stats reflect that game's score loosely.
PGS = [
    # week 1: BUF @ MIA, 17-24 (MIA wins)
    ("2024_01_BUF_MIA", "00-BUF-QB1", 1, "BUF", 240,  1, 2, 22, 35,   0,   0,  0,  0),
    ("2024_01_BUF_MIA", "00-MIA-QB1", 1, "MIA", 285,  2, 0, 25, 32,   0,   0,  0,  0),
    ("2024_01_BUF_MIA", "00-BUF-WR1", 1, "BUF",   0,  0, 0,  0,  0,  98,   0,  7, 10),
    ("2024_01_BUF_MIA", "00-MIA-WR1", 1, "MIA",   0,  0, 0,  0,  0, 142,   2, 10, 12),
    # week 1: DEN @ KC, 14-42 (KC blowout)
    ("2024_01_DEN_KC",  "00-DEN-QB1", 1, "DEN", 160,  1, 3, 14, 28,   0,   0,  0,  0),
    ("2024_01_DEN_KC",  "00-KC-QB1",  1, "KC",  380,  5, 0, 30, 38,   0,   0,  0,  0),
    # week 2: KC @ BUF, 21-21 (tie)
    ("2024_02_KC_BUF",  "00-KC-QB1",  2, "KC",  295,  2, 1, 24, 36,   0,   0,  0,  0),
    ("2024_02_KC_BUF",  "00-BUF-QB1", 2, "BUF", 310,  2, 1, 26, 35,   0,   0,  0,  0),
    ("2024_02_KC_BUF",  "00-BUF-WR1", 2, "BUF",   0,  0, 0,  0,  0, 115,   1,  8, 11),
    # week 2: MIA @ DEN, 28-27 (close)
    ("2024_02_MIA_DEN", "00-MIA-QB1", 2, "MIA", 320,  3, 1, 27, 33,   0,   0,  0,  0),
    ("2024_02_MIA_DEN", "00-DEN-QB1", 2, "DEN", 290,  3, 0, 26, 38,   0,   0,  0,  0),
    ("2024_02_MIA_DEN", "00-MIA-WR1", 2, "MIA",   0,  0, 0,  0,  0, 130,   1,  9, 11),
    # week 3: BUF @ DEN, 30-24
    ("2024_03_BUF_DEN", "00-BUF-QB1", 3, "BUF", 330,  3, 0, 28, 39,   0,   0,  0,  0),
    ("2024_03_BUF_DEN", "00-DEN-QB1", 3, "DEN", 250,  2, 2, 22, 34,   0,   0,  0,  0),
    ("2024_03_BUF_DEN", "00-BUF-WR1", 3, "BUF",   0,  0, 0,  0,  0, 105,   1,  7,  9),
]


# ── DB build helpers ─────────────────────────────────────────────────────────

def _create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the tables the routers actually read from.

    Columns mirror nfl_data_py / nflfastR output; only the columns referenced
    by the SQL in routers/ are included. Everything else can be added when
    a new endpoint reaches for it.
    """
    conn.execute("""
        CREATE TABLE schedules (
            game_id       VARCHAR PRIMARY KEY,
            season        INTEGER NOT NULL,
            game_type     VARCHAR NOT NULL,
            week          INTEGER NOT NULL,
            gameday       VARCHAR,
            gametime      VARCHAR,
            away_team     VARCHAR NOT NULL,
            home_team     VARCHAR NOT NULL,
            away_score    INTEGER,
            home_score    INTEGER,
            away_qb_name  VARCHAR,
            home_qb_name  VARCHAR,
            spread_line   DOUBLE,
            total_line    DOUBLE,
            roof          VARCHAR,
            surface       VARCHAR,
            temp          INTEGER,
            wind          INTEGER,
            stadium       VARCHAR,
            overtime      INTEGER,
            div_game      INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE rosters (
            player_id      VARCHAR NOT NULL,
            season         INTEGER NOT NULL,
            team           VARCHAR,
            position       VARCHAR,
            jersey_number  INTEGER,
            player_name    VARCHAR,
            headshot_url   VARCHAR,
            height         INTEGER,
            weight         INTEGER,
            age            INTEGER,
            college        VARCHAR,
            years_exp      INTEGER,
            entry_year     INTEGER,
            rookie_year    INTEGER,
            draft_club     VARCHAR,
            draft_number   INTEGER,
            pfr_id         VARCHAR
        )
    """)

    # All STAT_COLS from sql_helpers, defined as DOUBLE so SUM() works cleanly.
    from sql_helpers import STAT_COLS  # noqa: E402
    stat_col_ddl = ", ".join(f"{c} DOUBLE DEFAULT 0" for c in STAT_COLS)
    conn.execute(f"""
        CREATE TABLE player_game_stats (
            game_id      VARCHAR NOT NULL,
            player_id    VARCHAR NOT NULL,
            player_name  VARCHAR,
            season       INTEGER NOT NULL,
            week         INTEGER NOT NULL,
            team         VARCHAR,
            {stat_col_ddl}
        )
    """)


def _seed(conn: duckdb.DuckDBPyConnection) -> None:
    for week, away, home, a_sc, h_sc, spread, div, gtype in GAMES:
        game_id = f"{SEASON}_{week:02d}_{away}_{home}"
        conn.execute(
            """INSERT INTO schedules (
                game_id, season, game_type, week, gameday, gametime,
                away_team, home_team, away_score, home_score,
                spread_line, total_line, div_game, overtime
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [game_id, SEASON, gtype, week, f"2024-09-{week*7:02d}", "13:00",
             away, home, a_sc, h_sc, spread, 45.0, div, 0],
        )

    for pid, name, pos, team, jersey, height, weight in ROSTER:
        conn.execute(
            """INSERT INTO rosters (
                player_id, season, team, position, jersey_number, player_name,
                height, weight, years_exp, entry_year
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [pid, SEASON, team, pos, jersey, name, height, weight, 4, 2020],
        )

    for row in PGS:
        game_id, pid, week, team, pass_yds, pass_tds, ints, cmp, att, rec_yds, rec_tds, rec, tgts = row
        player_name = next(r[1] for r in ROSTER if r[0] == pid)
        conn.execute(
            """INSERT INTO player_game_stats (
                game_id, player_id, player_name, season, week, team,
                pass_yards, pass_tds, interceptions_thrown,
                completions, attempts,
                rec_yards, rec_tds, receptions, targets
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [game_id, pid, player_name, SEASON, week, team,
             pass_yds, pass_tds, ints, cmp, att,
             rec_yds, rec_tds, rec, tgts],
        )


# ── Pytest fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def seeded_conn() -> duckdb.DuckDBPyConnection:
    """A fresh in-memory DuckDB with mini-league data. Shared across the session."""
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    _seed(conn)
    return conn


@pytest.fixture
def client(seeded_conn, monkeypatch) -> TestClient:
    """FastAPI TestClient wired to the seeded in-memory DB.

    We bypass the lifespan (which would try to auto-ingest seasons over the
    network) by patching ingest_queue.queue_season into a no-op, and we
    point database._conn at the seeded connection so every cursor reads
    from it.
    """
    import database
    import ingest_queue
    import main

    monkeypatch.setattr(database, "_conn", seeded_conn)
    monkeypatch.setattr(ingest_queue, "queue_season", lambda year, force=False: "loaded")

    # TestClient runs lifespan; with queue_season stubbed, no network calls happen.
    with TestClient(main.app) as c:
        yield c
