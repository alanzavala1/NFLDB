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
    ("00-KC-DE1",   "Edge Dude",         "DE",     "KC",  95, 76, 260),
    ("00-KC-S1",    "Quiet Safety",      "S",      "KC",  26, 72, 205),
    ("00-KC-K1",    "Kicker Person",     "K",      "KC",   7, 72, 190),
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

DEF_PGS = [
    {
        "game_id": "2024_01_DEN_KC",
        "player_id": "00-KC-DE1",
        "team": "KC",
        "week": 1,
        "solo_tackles": 3,
        "assist_tackles": 2,
        "tackles_for_loss": 1,
        "qb_hits": 2,
        "sacks": 2,
        "def_interceptions": 1,
        "pass_breakups": 1,
        "forced_fumbles": 1,
        "fumble_recoveries": 1,
    },
    {
        "game_id": "2024_01_DEN_KC",
        "player_id": "00-KC-S1",
        "team": "KC",
        "week": 1,
        "solo_tackles": 0,
        "assist_tackles": 0,
        "tackles_for_loss": 0,
        "qb_hits": 0,
        "sacks": 0,
        "def_interceptions": 0,
        "pass_breakups": 0,
        "forced_fumbles": 0,
        "fumble_recoveries": 0,
    },
]


# Depth chart snapshots (new nflverse format): a current snapshot (Nov 2024 →
# NFL season 2024) plus one older snapshot that queries must ignore. Mahomes
# holds two slots (QB starter + Holder) to exercise the non-ST preference.
DEPTH = [
    # dt, team, player_name, gsis_id, pos_grp, pos_name, pos_abb, pos_slot, pos_rank
    ("2024-11-05T07:00:00Z", "KC", "Patrick Mahomes", "00-KC-QB1", "3WR 1TE",       "Quarterback",        "QB",  9, 1),
    ("2024-11-05T07:00:00Z", "KC", "Backup Guy",      "00-KC-QB2", "3WR 1TE",       "Quarterback",        "QB",  9, 2),
    ("2024-11-05T07:00:00Z", "KC", "Edge Dude",       "00-KC-DE1", "Base 4-3 D",    "Left Defensive End", "LDE", 1, 1),
    ("2024-11-05T07:00:00Z", "KC", "Kicker Person",   "00-KC-K1",  "Special Teams", "Place Kicker",       "PK",  1, 1),
    ("2024-11-05T07:00:00Z", "KC", "Patrick Mahomes", "00-KC-QB1", "Special Teams", "Holder",             "H",   4, 1),
    # stale snapshot: must never surface (Mahomes was "QB2" the day before)
    ("2024-11-04T07:00:00Z", "KC", "Patrick Mahomes", "00-KC-QB1", "3WR 1TE",       "Quarterback",        "QB",  9, 2),
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
            week           INTEGER,
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

    # New-format nflverse depth charts: dt-stamped daily snapshots.
    conn.execute("""
        CREATE TABLE depth_charts (
            dt          VARCHAR,
            team        VARCHAR,
            player_name VARCHAR,
            espn_id     VARCHAR,
            gsis_id     VARCHAR,
            pos_grp_id  VARCHAR,
            pos_grp     VARCHAR,
            pos_id      VARCHAR,
            pos_name    VARCHAR,
            pos_abb     VARCHAR,
            pos_slot    INTEGER,
            pos_rank    INTEGER
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

    conn.execute("""
        CREATE TABLE plays (
            play_id               DOUBLE,
            game_id               VARCHAR,
            season                INTEGER,
            season_type           VARCHAR,
            week                  INTEGER,
            posteam               VARCHAR,
            defteam               VARCHAR,
            play_type             VARCHAR,
            drive                 INTEGER,
            yardline_100          DOUBLE,
            yards_gained          DOUBLE,
            epa                   DOUBLE,
            qb_epa                DOUBLE,
            success               DOUBLE,
            pass_oe               DOUBLE,
            pass_attempt          INTEGER,
            rush_attempt          INTEGER,
            sack                  INTEGER,
            qb_kneel              INTEGER,
            qb_spike              INTEGER,
            two_point_attempt     INTEGER,
            touchdown             INTEGER,
            td_team               VARCHAR,
            interception          INTEGER,
            fumble_lost           INTEGER,
            complete_pass         INTEGER,
            passer_player_id      VARCHAR,
            receiver_player_id    VARCHAR,
            rusher_player_id      VARCHAR,
            field_goal_attempt    INTEGER,
            field_goal_result     VARCHAR,
            kick_distance         DOUBLE,
            extra_point_attempt   INTEGER,
            extra_point_result    VARCHAR,
            kicker_player_id      VARCHAR,
            third_down_converted  INTEGER,
            third_down_failed     INTEGER
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

    for dt, team, name, gsis, grp, pos_name, abb, slot, rank in DEPTH:
        conn.execute(
            """INSERT INTO depth_charts (
                dt, team, player_name, gsis_id, pos_grp, pos_name,
                pos_abb, pos_slot, pos_rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [dt, team, name, gsis, grp, pos_name, abb, slot, rank],
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

    for row in DEF_PGS:
        player_name = next(r[1] for r in ROSTER if r[0] == row["player_id"])
        conn.execute(
            """INSERT INTO player_game_stats (
                game_id, player_id, player_name, season, week, team,
                solo_tackles, assist_tackles, tackles_for_loss, qb_hits,
                sacks, def_interceptions, pass_breakups, forced_fumbles,
                fumble_recoveries
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                row["game_id"], row["player_id"], player_name, SEASON, row["week"], row["team"],
                row["solo_tackles"], row["assist_tackles"], row["tackles_for_loss"],
                row["qb_hits"], row["sacks"], row["def_interceptions"],
                row["pass_breakups"], row["forced_fumbles"], row["fumble_recoveries"],
            ],
        )

    play_id = 1

    def insert_play(
        game_id: str,
        week: int,
        posteam: str,
        defteam: str,
        epa: float,
        *,
        passer: str | None = None,
        receiver: str | None = None,
        rusher: str | None = None,
        sack: int = 0,
        interception: int = 0,
        fumble_lost: int = 0,
        fg_result: str | None = None,
        kick_distance: float | None = None,
        xp_result: str | None = None,
        kicker: str | None = None,
    ) -> None:
        nonlocal play_id
        is_fg = 1 if fg_result is not None else 0
        is_xp = 1 if xp_result is not None else 0
        pass_attempt = 1 if passer is not None and not is_fg and not is_xp and rusher is None else 0
        rush_attempt = 1 if rusher is not None else 0
        play_type = "field_goal" if is_fg else "extra_point" if is_xp else "pass" if pass_attempt or sack else "run"
        conn.execute(
            """INSERT INTO plays (
                play_id, game_id, season, season_type, week, posteam, defteam,
                play_type, drive, yardline_100, yards_gained, epa, qb_epa,
                success, pass_oe, pass_attempt, rush_attempt, sack, qb_kneel,
                qb_spike, two_point_attempt, touchdown, td_team, interception,
                fumble_lost, complete_pass, passer_player_id, receiver_player_id,
                rusher_player_id, field_goal_attempt, field_goal_result,
                kick_distance, extra_point_attempt, extra_point_result,
                kicker_player_id, third_down_converted, third_down_failed
            ) VALUES (?, ?, ?, 'REG', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)""",
            [
                play_id, game_id, SEASON, week, posteam, defteam, play_type,
                play_id // 6 + 1, 50.0, 5.0 if epa > 0 else -1.0,
                epa, epa, 1.0 if epa > 0 else 0.0, 0.0,
                pass_attempt, rush_attempt, sack, interception, fumble_lost,
                1 if pass_attempt and not interception else 0,
                passer, receiver, rusher, is_fg, fg_result, kick_distance,
                is_xp, xp_result, kicker,
            ],
        )
        play_id += 1

    # Week 1: Mahomes posts a great EPA game, Denver's QB has a disaster,
    # and Diggs has two targets to exercise the WR involvement floor.
    for _ in range(12):
        insert_play("2024_01_DEN_KC", 1, "KC", "DEN", 1.0, passer="00-KC-QB1")
    for i in range(12):
        insert_play("2024_01_DEN_KC", 1, "DEN", "KC", -1.0, passer="00-DEN-QB1", interception=1 if i < 2 else 0)
    for _ in range(2):
        insert_play("2024_01_BUF_MIA", 1, "BUF", "MIA", 1.0, passer="00-BUF-QB1", receiver="00-BUF-WR1")
    for _ in range(8):
        insert_play("2024_01_BUF_MIA", 1, "BUF", "MIA", 0.2, passer="00-BUF-QB1")
    for _ in range(10):
        insert_play("2024_01_BUF_MIA", 1, "MIA", "BUF", 0.5, passer="00-MIA-QB1", receiver="00-MIA-WR1")
    insert_play("2024_01_DEN_KC", 1, "KC", "DEN", 0.0, fg_result="made", kick_distance=45, kicker="00-KC-K1")
    insert_play("2024_01_DEN_KC", 1, "KC", "DEN", 0.0, xp_result="good", kicker="00-KC-K1")

    # Week 2 gives BUF enough EPA to climb relative to Week 1.
    for _ in range(12):
        insert_play("2024_02_KC_BUF", 2, "BUF", "KC", 2.0, passer="00-BUF-QB1")
    for _ in range(12):
        insert_play("2024_02_KC_BUF", 2, "KC", "BUF", -0.5, passer="00-KC-QB1")
    for _ in range(10):
        insert_play("2024_02_MIA_DEN", 2, "MIA", "DEN", 0.4, passer="00-MIA-QB1")
    for _ in range(10):
        insert_play("2024_02_MIA_DEN", 2, "DEN", "MIA", -0.2, passer="00-DEN-QB1")

    # Week 3 keeps the season grid populated for endpoint/default-week tests.
    for _ in range(10):
        insert_play("2024_03_BUF_DEN", 3, "BUF", "DEN", 0.3, passer="00-BUF-QB1")
    for _ in range(10):
        insert_play("2024_03_BUF_DEN", 3, "DEN", "BUF", -0.1, passer="00-DEN-QB1")


# ── Pytest fixtures ──────────────────────────────────────────────────────────

# Work around a DuckDB segfault during interpreter finalization on Linux.
# DuckDB's C-extension (and its Arrow/numpy interop) can crash while the Python
# interpreter tears down at process exit — *after* every test has passed and
# the summary has printed — failing CI with exit 139 (SIGSEGV). Closing
# connections doesn't reliably prevent it; the crash is in module finalization,
# not our objects. We capture pytest's real exit status, then in
# pytest_unconfigure (which runs after the terminal summary is printed but
# before interpreter teardown) exit immediately with that status via os._exit,
# skipping the crash-prone C-extension teardown. Correct semantics are kept: a
# genuine test failure still produces a non-zero exit.
_real_exit_status = 0


def pytest_sessionfinish(session, exitstatus):
    global _real_exit_status
    _real_exit_status = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_real_exit_status)


@pytest.fixture(scope="session")
def seeded_conn() -> duckdb.DuckDBPyConnection:
    """A fresh in-memory DuckDB with mini-league data. Shared across the session."""
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    _seed(conn)
    yield conn
    conn.close()


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
    import routers.meta

    monkeypatch.setattr(database, "_conn", seeded_conn)
    # queue_season is imported by name into main and routers.meta, so patching
    # the ingest_queue module alone does NOT reach them — the lifespan's
    # auto-load was hitting the real queue and ingesting actual seasons over
    # the network into this in-memory DB mid-suite. Patch every reference,
    # and stub the worker's run_ingest so nothing already queued can ingest.
    stub = lambda year, force=False: "loaded"  # noqa: E731
    monkeypatch.setattr(ingest_queue, "queue_season", stub)
    monkeypatch.setattr(main, "queue_season", stub)
    monkeypatch.setattr(routers.meta, "queue_season", stub)
    monkeypatch.setattr(ingest_queue, "run_ingest", lambda years, log=print: None)

    # TestClient runs lifespan; with queue_season stubbed, no network calls happen.
    with TestClient(main.app) as c:
        yield c
