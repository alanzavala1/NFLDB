import asyncio
import queue
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from database import query_to_dict
from ingest import run_ingest

FIRST_SEASON = 1999

# All numeric stat columns on player_game_stats (excluding identity/team fields).
# Single source of truth used in SQL selects and Python aggregations.
_STAT_COLS = (
    "attempts", "completions", "pass_yards", "pass_tds",
    "interceptions_thrown", "sacks_taken", "pass_epa",
    "targets", "receptions", "rec_yards", "rec_tds",
    "air_yards", "yac", "rec_epa",
    "carries", "rush_yards", "rush_tds", "rush_epa",
    "solo_tackles", "assist_tackles", "tackles_for_loss",
    "sacks", "qb_hits", "def_interceptions",
    "pass_breakups", "forced_fumbles", "fumble_recoveries",
    "fg_att", "fg_made", "xp_att", "xp_made",
    "punts", "punt_yards",
    "punt_returns", "punt_return_yards", "punt_return_tds",
)

# Prefixed for use inside CTEs where pgs alias is in scope.
_PGS_STAT_SEL = ", ".join(f"pgs.{c}" for c in _STAT_COLS)

# De-duped roster: one row per player+season.
_ROSTER_CTE = """\
    roster AS (
        SELECT player_id, season, team, position, jersey_number, headshot_url
        FROM rosters
        QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id, season ORDER BY season DESC) = 1
    )"""

# Team-correction CASE and ROW_NUMBER rank for a known game (away/home as SQL expressions).
# Roster team is authoritative; pgs.team is only used if roster doesn't match the game.
def _team_sql(away: str, home: str) -> tuple[str, str]:
    correction = f"""\
CASE
                    WHEN r.team IN ({away}, {home})                             THEN r.team
                    WHEN pgs.team IN ({away}, {home})                           THEN pgs.team
                    ELSE COALESCE(r.team, pgs.team)
                END"""
    rank = f"""\
CASE
                        WHEN r.team = pgs.team AND pgs.team IN ({away}, {home}) THEN 0
                        WHEN r.team IN ({away}, {home})                         THEN 1
                        WHEN pgs.team IN ({away}, {home})                       THEN 2
                        ELSE 3
                    END"""
    return correction, rank


_TEAM_NAMES = {
    'ARI': 'Arizona Cardinals',    'ATL': 'Atlanta Falcons',
    'BAL': 'Baltimore Ravens',     'BUF': 'Buffalo Bills',
    'CAR': 'Carolina Panthers',    'CHI': 'Chicago Bears',
    'CIN': 'Cincinnati Bengals',   'CLE': 'Cleveland Browns',
    'DAL': 'Dallas Cowboys',       'DEN': 'Denver Broncos',
    'DET': 'Detroit Lions',        'GB':  'Green Bay Packers',
    'HOU': 'Houston Texans',       'IND': 'Indianapolis Colts',
    'JAX': 'Jacksonville Jaguars', 'KC':  'Kansas City Chiefs',
    'LAC': 'Los Angeles Chargers', 'LA':  'Los Angeles Rams',
    'LV':  'Las Vegas Raiders',    'MIA': 'Miami Dolphins',
    'MIN': 'Minnesota Vikings',    'NE':  'New England Patriots',
    'NO':  'New Orleans Saints',   'NYG': 'New York Giants',
    'NYJ': 'New York Jets',        'PHI': 'Philadelphia Eagles',
    'PIT': 'Pittsburgh Steelers',  'SEA': 'Seattle Seahawks',
    'SF':  'San Francisco 49ers',  'TB':  'Tampa Bay Buccaneers',
    'TEN': 'Tennessee Titans',     'WAS': 'Washington Commanders',
    'OAK': 'Oakland Raiders',      'SD':  'San Diego Chargers',
    'STL': 'St. Louis Rams',       'JAC': 'Jacksonville Jaguars',
}

_DIVISIONS: dict[str, str] = {
    'BUF': 'AFC East',  'MIA': 'AFC East',  'NE':  'AFC East',  'NYJ': 'AFC East',
    'BAL': 'AFC North', 'CIN': 'AFC North', 'CLE': 'AFC North', 'PIT': 'AFC North',
    'HOU': 'AFC South', 'IND': 'AFC South', 'JAX': 'AFC South', 'TEN': 'AFC South',
    'DEN': 'AFC West',  'KC':  'AFC West',  'LAC': 'AFC West',  'LV':  'AFC West',
    'DAL': 'NFC East',  'NYG': 'NFC East',  'PHI': 'NFC East',  'WAS': 'NFC East',
    'CHI': 'NFC North', 'DET': 'NFC North', 'GB':  'NFC North', 'MIN': 'NFC North',
    'ATL': 'NFC South', 'CAR': 'NFC South', 'NO':  'NFC South', 'TB':  'NFC South',
    'ARI': 'NFC West',  'LA':  'NFC West',  'SEA': 'NFC West',  'SF':  'NFC West',
    # Historical relocations
    'OAK': 'AFC West',  'SD':  'AFC West',  'STL': 'NFC West',  'JAC': 'AFC South',
}

def _current_nfl_season() -> int:
    from datetime import datetime
    now = datetime.now()
    return now.year if now.month >= 9 else now.year - 1

CURRENT_SEASON = _current_nfl_season()
AUTO_LOAD_SEASONS = 5  # load this many recent seasons automatically on startup

# Season state: "queued" | "loading" | "error" — absent means loaded or not yet touched
_season_status: dict[int, str] = {}
_ingest_logs:   dict[int, list[str]] = {}

# Single-writer queue: one background thread loads seasons sequentially
_load_queue: queue.SimpleQueue[int] = queue.SimpleQueue()


def _ingest_season(year: int) -> None:
    _ingest_logs[year] = []

    def log(msg: str):
        line = str(msg).strip()
        print(line)
        _ingest_logs.setdefault(year, []).append(line)

    try:
        run_ingest([year], log=log)
        _season_status.pop(year, None)          # remove → treated as "loaded"
        _ingest_logs[year].append("__DONE__")
    except Exception as e:
        print(f"Ingest failed for {year}: {e}")
        _season_status[year] = "error"
        _ingest_logs[year].append(f"__ERROR__ {e}")


def _load_worker() -> None:
    """Single daemon thread — consumes the queue, one season at a time."""
    while True:
        year = _load_queue.get()
        if _season_status.get(year) not in ("queued", "loading"):
            continue   # was cancelled / already done
        _season_status[year] = "loading"
        _ingest_season(year)


def _queue_season(year: int, force: bool = False) -> str:
    """Enqueue a season for loading. Returns the resulting status string."""
    current = _season_status.get(year)
    if current in ("queued", "loading"):
        return current

    if not force:
        try:
            loaded = {r["season"] for r in query_to_dict("SELECT DISTINCT season FROM schedules")}
            if year in loaded:
                return "loaded"
        except Exception:
            pass

    _season_status[year] = "queued"
    _load_queue.put(year)
    return "queued"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the single background worker
    threading.Thread(target=_load_worker, daemon=True).start()

    # Auto-queue the N most recent seasons that aren't already in the DB
    try:
        loaded = {r["season"] for r in query_to_dict("SELECT DISTINCT season FROM schedules")}
    except Exception:
        loaded = set()

    queued = 0
    for year in range(CURRENT_SEASON, FIRST_SEASON - 1, -1):
        if queued >= AUTO_LOAD_SEASONS:
            break
        if year not in loaded:
            _queue_season(year, force=False)
            queued += 1

    yield


app = FastAPI(title="NFL Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/seasons")
def get_seasons():
    try:
        loaded = {r["season"] for r in query_to_dict("SELECT DISTINCT season FROM schedules")}
    except Exception:
        loaded = set()
    return [
        {
            "season": year,
            "status": _season_status.get(year, "loaded" if year in loaded else "available"),
        }
        for year in range(CURRENT_SEASON, FIRST_SEASON - 1, -1)
    ]


@app.post("/seasons/{year}/load")
def load_season(year: int, force: bool = False):
    if year < FIRST_SEASON or year > CURRENT_SEASON:
        raise HTTPException(status_code=400, detail=f"Season must be between {FIRST_SEASON} and {CURRENT_SEASON}")
    status = _queue_season(year, force=force)
    return {"season": year, "status": status}


@app.get("/seasons/{year}/progress")
def season_progress(year: int):
    async def event_stream():
        sent = 0
        while True:
            logs = _ingest_logs.get(year, [])
            while sent < len(logs):
                line = logs[sent]
                yield f"data: {line}\n\n"
                sent += 1
                if line.startswith("__DONE__") or line.startswith("__ERROR__"):
                    return
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


def _attach_records(games: list[dict]) -> list[dict]:
    """Add away_record / home_record (entering each game) by walking weeks in order."""
    team_records: dict[str, tuple[int, int, int]] = {}  # team -> (W, L, T)

    def fmt(wlt: tuple[int, int, int]) -> str:
        w, l, t = wlt
        return f"{w}-{l}-{t}" if t else f"{w}-{l}"

    by_week: dict[int, list[dict]] = {}
    for g in games:
        by_week.setdefault(g["week"], []).append(g)

    for week in sorted(by_week):
        for g in by_week[week]:
            g["away_record"] = fmt(team_records.get(g["away_team"], (0, 0, 0)))
            g["home_record"] = fmt(team_records.get(g["home_team"], (0, 0, 0)))

        for g in by_week[week]:
            a, h = g["away_team"], g["home_team"]
            as_, hs = g["away_score"], g["home_score"]
            if as_ is None or hs is None:
                continue
            aw, al, at = team_records.get(a, (0, 0, 0))
            hw, hl, ht = team_records.get(h, (0, 0, 0))
            if as_ > hs:
                team_records[a] = (aw + 1, al, at)
                team_records[h] = (hw, hl + 1, ht)
            elif hs > as_:
                team_records[a] = (aw, al + 1, at)
                team_records[h] = (hw + 1, hl, ht)
            else:
                team_records[a] = (aw, al, at + 1)
                team_records[h] = (hw, hl, ht + 1)

    return games


@app.get("/schedule")
def get_schedule(season: int = Query(2025)):
    rows = query_to_dict(
        """
        SELECT
            game_id, season, game_type, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            away_qb_name, home_qb_name, spread_line, total_line,
            roof, surface, temp, wind, stadium, overtime, div_game
        FROM schedules
        WHERE season = ?
        ORDER BY week, gametime
        """,
        [season],
    )
    _attach_records(rows)
    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row["week"], []).append(row)
    return [{"week": w, "games": games} for w, games in sorted(grouped.items())]


@app.get("/games")
def get_games(
    week: int = Query(..., ge=1, le=22),
    season: int = Query(2025),
):
    rows = query_to_dict(
        """
        SELECT
            game_id,
            season,
            game_type,
            week,
            gameday,
            gametime,
            away_team,
            home_team,
            away_score,
            home_score,
            away_qb_name,
            home_qb_name,
            spread_line,
            total_line,
            roof,
            surface,
            temp,
            wind,
            stadium,
            overtime,
            div_game
        FROM schedules
        WHERE week = ? AND season = ?
        ORDER BY gametime
        """,
        [week, season],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No games found for week {week}, season {season}")
    return rows


@app.get("/games/{game_id}")
def get_game(game_id: str):
    games = query_to_dict(
        """
        SELECT
            game_id, season, game_type, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            away_qb_name, home_qb_name,
            spread_line, total_line, overtime, div_game,
            roof, surface, temp, wind, stadium
        FROM schedules
        WHERE game_id = ?
        """,
        [game_id],
    )
    if not games:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    game = games[0]

    # Compute each team's record entering this game
    prior = query_to_dict(
        """
        SELECT away_team, home_team, away_score, home_score, week
        FROM schedules
        WHERE season = ? AND week < ? AND away_score IS NOT NULL
        ORDER BY week
        """,
        [game["season"], game["week"]],
    )
    _attach_records(prior + [game])  # mutates game in-place

    away_team = game["away_team"]
    home_team = game["home_team"]
    team_sel, team_rank = _team_sql("?", "?")

    players = query_to_dict(
        f"""
        WITH {_ROSTER_CTE},
        ranked AS (
            SELECT
                pgs.player_id,
                pgs.player_name,
                {team_sel} AS team,
                pgs.week,
                r.position, r.jersey_number, r.headshot_url,
                {_PGS_STAT_SEL},
                ROW_NUMBER() OVER (
                    PARTITION BY pgs.player_id
                    ORDER BY {team_rank}
                ) AS rn
            FROM player_game_stats pgs
            LEFT JOIN roster r ON r.player_id = pgs.player_id AND r.season = pgs.season
            WHERE pgs.game_id = ?
        )
        SELECT * EXCLUDE (rn)
        FROM ranked
        WHERE rn = 1
        ORDER BY team, position, player_name
        """,
        [away_team, home_team, away_team, home_team,
         away_team, home_team, away_team, home_team, away_team, home_team,
         game_id],
    )

    # Quarter-by-quarter scores from play-by-play
    quarter_scores = []
    try:
        q_rows = _safe_query(
            """
            SELECT
                qtr,
                MAX(CASE WHEN posteam = ? THEN posteam_score
                         WHEN defteam  = ? THEN defteam_score END) AS away_cumul,
                MAX(CASE WHEN posteam = ? THEN posteam_score
                         WHEN defteam  = ? THEN defteam_score END) AS home_cumul
            FROM plays
            WHERE game_id = ?
            GROUP BY qtr
            ORDER BY qtr
            """,
            [away_team, away_team, home_team, home_team, game_id],
        )
        away_prev = home_prev = 0
        for row in q_rows:
            ac = int(row["away_cumul"] or 0)
            hc = int(row["home_cumul"] or 0)
            quarter_scores.append({"qtr": int(row["qtr"]), "away": ac - away_prev, "home": hc - home_prev})
            away_prev, home_prev = ac, hc
    except Exception:
        pass

    win_prob = _safe_query(
        """
        SELECT
            game_seconds_remaining,
            qtr,
            ROUND(home_wp, 4)   AS home_wp,
            COALESCE(touchdown,    0) AS touchdown,
            COALESCE(interception, 0) AS interception,
            COALESCE(fumble_lost,  0) AS fumble_lost,
            posteam,
            "desc"              AS desc
        FROM plays
        WHERE game_id = ?
          AND home_wp IS NOT NULL
          AND game_seconds_remaining IS NOT NULL
        ORDER BY game_seconds_remaining DESC
        """,
        [game_id],
    )

    return {
        **game,
        "away": [p for p in players if p["team"] == away_team],
        "home": [p for p in players if p["team"] == home_team],
        "quarter_scores": quarter_scores,
        "win_prob": win_prob,
    }


def _safe_query(sql: str, params: list = []) -> list[dict]:
    try:
        return query_to_dict(sql, params)
    except Exception:
        return []


def _get_ngs(player_id: str) -> dict:
    """Aggregate NGS weekly data by season for a player."""
    result: dict[int, dict] = {}

    for row in _safe_query("""
        SELECT season,
            ROUND(AVG(avg_time_to_throw), 2)                         AS avg_time_to_throw,
            ROUND(AVG(avg_intended_air_yards), 1)                     AS adot,
            ROUND(AVG(avg_completed_air_yards), 1)                    AS avg_completed_air_yards,
            ROUND(AVG(completion_percentage_above_expectation), 1)    AS cpoe,
            ROUND(AVG(aggressiveness), 1)                             AS aggressiveness,
            ROUND(AVG(expected_completion_percentage), 1)             AS expected_cmp_pct,
            ROUND(AVG(passer_rating), 1)                              AS ngs_passer_rating
        FROM ngs_passing
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    for row in _safe_query("""
        SELECT season,
            ROUND(SUM(rush_yards_over_expected), 1)                   AS rush_yoe,
            ROUND(AVG(rush_yards_over_expected_per_att), 2)           AS rush_yoe_per_att,
            ROUND(AVG(efficiency), 1)                                 AS rush_efficiency,
            ROUND(AVG(avg_time_to_los), 2)                            AS avg_time_to_los,
            ROUND(AVG(percent_attempts_gte_eight_defenders), 1)       AS pct_vs_8_defenders
        FROM ngs_rushing
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    for row in _safe_query("""
        SELECT season,
            ROUND(AVG(avg_separation), 2)                             AS avg_separation,
            ROUND(AVG(avg_cushion), 2)                                AS avg_cushion,
            ROUND(AVG(avg_intended_air_yards), 1)                     AS avg_target_depth,
            ROUND(AVG(avg_yac), 2)                                    AS avg_yac,
            ROUND(AVG(avg_yac_above_expectation), 2)                  AS avg_yac_above_exp,
            ROUND(AVG(catch_percentage), 1)                           AS catch_pct,
            ROUND(AVG(percent_share_of_intended_air_yards), 1)        AS air_yards_share
        FROM ngs_receiving
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    return result


def _get_snap_totals(player_id: str) -> dict:
    rows = _safe_query("""
        SELECT sc.season,
            SUM(sc.offense_snaps)               AS offense_snaps,
            SUM(sc.defense_snaps)               AS defense_snaps,
            SUM(sc.st_snaps)                    AS st_snaps,
            ROUND(AVG(sc.offense_pct) * 100, 1) AS avg_offense_pct,
            ROUND(AVG(sc.defense_pct) * 100, 1) AS avg_defense_pct,
            ROUND(AVG(sc.st_pct) * 100, 1)      AS avg_st_pct
        FROM snap_counts sc
        JOIN rosters r ON sc.pfr_player_id = r.pfr_id AND sc.season = r.season
        WHERE r.player_id = ?
        GROUP BY sc.season
    """, [player_id])
    return {r["season"]: r for r in rows}


def _get_situational_stats(player_id: str) -> dict:
    """Per-season situational stats from play-by-play: red zone, 3rd down, longest plays, first downs."""
    result: dict[int, dict] = {}
    pid = player_id

    def merge_rows(rows: list[dict]) -> None:
        for row in rows:
            s = row.pop("season", None)
            if s is None:
                continue
            cleaned = {}
            for k, v in row.items():
                if v is None:
                    continue
                cleaned[k] = int(v) if isinstance(v, float) and v.is_integer() else v
            result.setdefault(int(s), {}).update(cleaned)

    # Longest completions / rushes / receptions
    merge_rows(_safe_query("""
        WITH pp AS (
            SELECT * FROM plays
            WHERE (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
              AND season_type = 'REG'
        )
        SELECT season,
            MAX(CASE WHEN passer_player_id  = ? AND pass_attempt = 1 AND complete_pass = 1 THEN passing_yards   END) AS lng_pass,
            MAX(CASE WHEN rusher_player_id   = ? AND rush_attempt = 1                       THEN rushing_yards   END) AS lng_rush,
            MAX(CASE WHEN receiver_player_id = ? AND complete_pass = 1                      THEN receiving_yards END) AS lng_rec
        FROM pp GROUP BY season
    """, [pid, pid, pid, pid, pid, pid]))

    # Red zone (inside opponent 20 = yardline_100 <= 20)
    merge_rows(_safe_query("""
        WITH pp AS (
            SELECT * FROM plays
            WHERE (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
              AND yardline_100 <= 20
              AND season_type = 'REG'
        )
        SELECT season,
            COUNT(*)  FILTER (WHERE passer_player_id  = ? AND pass_attempt = 1)                        AS rz_pass_att,
            SUM(CASE WHEN passer_player_id  = ? AND pass_attempt = 1 AND complete_pass = 1 THEN 1 ELSE 0 END) AS rz_cmp,
            SUM(CASE WHEN passer_player_id  = ? AND pass_attempt = 1 AND touchdown = 1     THEN 1 ELSE 0 END) AS rz_pass_tds,
            COUNT(*)  FILTER (WHERE receiver_player_id = ? AND pass_attempt = 1)                       AS rz_targets,
            SUM(CASE WHEN receiver_player_id = ? AND pass_attempt = 1 AND touchdown = 1    THEN 1 ELSE 0 END) AS rz_rec_tds,
            COUNT(*)  FILTER (WHERE rusher_player_id   = ? AND rush_attempt = 1)                       AS rz_carries,
            SUM(CASE WHEN rusher_player_id   = ? AND rush_attempt = 1 AND touchdown = 1    THEN 1 ELSE 0 END) AS rz_rush_tds
        FROM pp GROUP BY season
    """, [pid, pid, pid, pid, pid, pid, pid, pid, pid, pid]))

    # 3rd down
    merge_rows(_safe_query("""
        WITH pp AS (
            SELECT * FROM plays
            WHERE (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
              AND down = 3
              AND season_type = 'REG'
        )
        SELECT season,
            COUNT(*)  FILTER (WHERE passer_player_id  = ? AND pass_attempt = 1)                                          AS third_pass_att,
            SUM(COALESCE(CASE WHEN passer_player_id  = ? AND pass_attempt = 1  THEN first_down_pass END, 0))              AS third_pass_fd,
            COUNT(*)  FILTER (WHERE receiver_player_id = ? AND pass_attempt = 1)                                          AS third_targets,
            SUM(COALESCE(CASE WHEN receiver_player_id = ? AND complete_pass = 1 THEN first_down_pass END, 0))             AS third_rec_fd,
            COUNT(*)  FILTER (WHERE rusher_player_id   = ? AND rush_attempt = 1)                                          AS third_carries,
            SUM(COALESCE(CASE WHEN rusher_player_id   = ? AND rush_attempt = 1  THEN first_down_rush END, 0))             AS third_rush_fd
        FROM pp GROUP BY season
    """, [pid, pid, pid, pid, pid, pid, pid, pid, pid]))

    # First downs generated
    merge_rows(_safe_query("""
        WITH pp AS (
            SELECT * FROM plays
            WHERE (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
              AND season_type = 'REG'
        )
        SELECT season,
            SUM(COALESCE(CASE WHEN passer_player_id  = ? AND pass_attempt = 1  THEN first_down_pass END, 0)) AS fd_pass,
            SUM(COALESCE(CASE WHEN receiver_player_id = ? AND complete_pass = 1 THEN first_down_pass END, 0)) AS fd_rec,
            SUM(COALESCE(CASE WHEN rusher_player_id   = ? AND rush_attempt = 1  THEN first_down_rush END, 0)) AS fd_rush
        FROM pp GROUP BY season
    """, [pid, pid, pid, pid, pid, pid]))

    return result


def _get_player_wpa(player_id: str) -> dict:
    """Per-season WPA attribution from play-by-play using proper split credit."""
    result: dict[int, dict] = {}
    pid = player_id

    for row in _safe_query("""
        SELECT season, ROUND(SUM(COALESCE(air_wpa, 0)), 3) AS pass_wpa
        FROM plays
        WHERE passer_player_id = ? AND pass_attempt = 1 AND season_type = 'REG'
        GROUP BY season
    """, [pid]):
        s = int(row["season"])
        result.setdefault(s, {})["pass_wpa"] = row["pass_wpa"]

    for row in _safe_query("""
        SELECT season, ROUND(SUM(COALESCE(yac_wpa, 0)), 3) AS rec_wpa
        FROM plays
        WHERE receiver_player_id = ? AND complete_pass = 1 AND season_type = 'REG'
        GROUP BY season
    """, [pid]):
        s = int(row["season"])
        result.setdefault(s, {})["rec_wpa"] = row["rec_wpa"]

    for row in _safe_query("""
        SELECT season, ROUND(SUM(COALESCE(wpa, 0)), 3) AS rush_wpa
        FROM plays
        WHERE rusher_player_id = ? AND rush_attempt = 1 AND season_type = 'REG'
        GROUP BY season
    """, [pid]):
        s = int(row["season"])
        result.setdefault(s, {})["rush_wpa"] = row["rush_wpa"]

    return result


@app.get("/players/{player_id}")
def get_player(player_id: str):
    profile_rows = query_to_dict(
        """
        SELECT
            player_id, player_name, position, team, jersey_number,
            headshot_url, height, weight, age, college,
            years_exp, entry_year, rookie_year, draft_club, draft_number
        FROM rosters
        WHERE player_id = ?
        ORDER BY season DESC
        LIMIT 1
        """,
        [player_id],
    )
    if not profile_rows:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    profile = profile_rows[0]

    team_sel, team_rank = _team_sql("s.away_team", "s.home_team")
    stat_cols_csv = ", ".join(_STAT_COLS)

    games = query_to_dict(
        f"""
        WITH {_ROSTER_CTE},
        ranked AS (
            SELECT
                pgs.game_id, pgs.season, pgs.week, pgs.player_id,
                {team_sel} AS team,
                s.away_team, s.home_team, s.gameday, s.away_score, s.home_score, s.game_type,
                r.position, r.jersey_number, r.headshot_url,
                {_PGS_STAT_SEL},
                ROW_NUMBER() OVER (
                    PARTITION BY pgs.game_id, pgs.player_id
                    ORDER BY {team_rank}
                ) AS rn
            FROM player_game_stats pgs
            LEFT JOIN schedules s ON pgs.game_id = s.game_id
            LEFT JOIN roster r    ON pgs.player_id = r.player_id AND r.season = pgs.season
            WHERE pgs.player_id = ?
        )
        SELECT
            game_id, season, week, team,
            CASE WHEN team = home_team THEN away_team ELSE home_team END AS opponent,
            CASE WHEN team = home_team THEN 'home' ELSE 'away' END       AS location,
            gameday, away_score, home_score,
            CASE
                WHEN away_score IS NULL                               THEN NULL
                WHEN team = home_team AND home_score > away_score     THEN 'W'
                WHEN team = away_team AND away_score > home_score     THEN 'W'
                WHEN home_score = away_score                          THEN 'T'
                ELSE 'L'
            END AS result,
            game_type,
            {stat_cols_csv},
            position, jersey_number, headshot_url
        FROM ranked
        WHERE rn = 1
        ORDER BY season, week
        """,
        [player_id],
    )

    season_totals = {col: sum(g[col] or 0 for g in games) for col in _STAT_COLS}

    return {
        **profile,
        "games_played": len(games),
        "season_totals": season_totals,
        "games": games,
        "ngs": _get_ngs(player_id),
        "snap_totals": _get_snap_totals(player_id),
        "situational": _get_situational_stats(player_id),
        "wpa": _get_player_wpa(player_id),
    }


@app.get("/teams/{team}")
def get_team(team: str, season: int = Query(2025)):
    games = query_to_dict(
        """
        SELECT
            game_id, season, week, gameday, gametime,
            away_team, home_team, away_score, home_score,
            stadium, roof, surface, temp, wind
        FROM schedules
        WHERE season = ? AND (away_team = ? OR home_team = ?)
        ORDER BY week
        """,
        [season, team, team],
    )
    if not games:
        raise HTTPException(status_code=404, detail=f"No games found for {team} in {season}")

    _attach_records(games)

    leaders = query_to_dict(
        """
        SELECT
            pgs.player_id,
            pgs.player_name,
            r.position,
            r.headshot_url,
            r.jersey_number,
            COUNT(DISTINCT pgs.game_id)   AS games_played,
            SUM(pgs.attempts)             AS attempts,
            SUM(pgs.completions)          AS completions,
            SUM(pgs.pass_yards)           AS pass_yards,
            SUM(pgs.pass_tds)             AS pass_tds,
            SUM(pgs.interceptions_thrown) AS interceptions_thrown,
            SUM(pgs.sacks_taken)          AS sacks_taken,
            SUM(pgs.pass_epa)             AS pass_epa,
            SUM(pgs.carries)              AS carries,
            SUM(pgs.rush_yards)           AS rush_yards,
            SUM(pgs.rush_tds)             AS rush_tds,
            SUM(pgs.rush_epa)             AS rush_epa,
            SUM(pgs.targets)              AS targets,
            SUM(pgs.receptions)           AS receptions,
            SUM(pgs.rec_yards)            AS rec_yards,
            SUM(pgs.rec_tds)              AS rec_tds,
            SUM(pgs.air_yards)            AS air_yards,
            SUM(pgs.yac)                  AS yac,
            SUM(pgs.rec_epa)              AS rec_epa,
            SUM(pgs.solo_tackles)         AS solo_tackles,
            SUM(pgs.assist_tackles)       AS assist_tackles,
            SUM(pgs.sacks)                AS sacks,
            SUM(pgs.tackles_for_loss)     AS tackles_for_loss,
            SUM(pgs.qb_hits)              AS qb_hits,
            SUM(pgs.def_interceptions)    AS def_interceptions,
            SUM(pgs.pass_breakups)        AS pass_breakups,
            SUM(pgs.forced_fumbles)       AS forced_fumbles,
            SUM(pgs.fumble_recoveries)    AS fumble_recoveries
        FROM player_game_stats pgs
        LEFT JOIN rosters r ON pgs.player_id = r.player_id AND r.season = pgs.season
        JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type = 'REG'
        WHERE pgs.season = ? AND pgs.team = ?
        GROUP BY pgs.player_id, pgs.player_name, r.position, r.headshot_url, r.jersey_number
        """,
        [season, team],
    )

    _LEADER_COLS = """
            COUNT(DISTINCT pgs.game_id)   AS games_played,
            SUM(pgs.attempts)             AS attempts,
            SUM(pgs.completions)          AS completions,
            SUM(pgs.pass_yards)           AS pass_yards,
            SUM(pgs.pass_tds)             AS pass_tds,
            SUM(pgs.interceptions_thrown) AS interceptions_thrown,
            SUM(pgs.sacks_taken)          AS sacks_taken,
            SUM(pgs.pass_epa)             AS pass_epa,
            SUM(pgs.carries)              AS carries,
            SUM(pgs.rush_yards)           AS rush_yards,
            SUM(pgs.rush_tds)             AS rush_tds,
            SUM(pgs.rush_epa)             AS rush_epa,
            SUM(pgs.targets)              AS targets,
            SUM(pgs.receptions)           AS receptions,
            SUM(pgs.rec_yards)            AS rec_yards,
            SUM(pgs.rec_tds)              AS rec_tds,
            SUM(pgs.air_yards)            AS air_yards,
            SUM(pgs.yac)                  AS yac,
            SUM(pgs.rec_epa)              AS rec_epa,
            SUM(pgs.solo_tackles)         AS solo_tackles,
            SUM(pgs.assist_tackles)       AS assist_tackles,
            SUM(pgs.sacks)                AS sacks,
            SUM(pgs.tackles_for_loss)     AS tackles_for_loss,
            SUM(pgs.qb_hits)              AS qb_hits,
            SUM(pgs.def_interceptions)    AS def_interceptions,
            SUM(pgs.pass_breakups)        AS pass_breakups,
            SUM(pgs.forced_fumbles)       AS forced_fumbles,
            SUM(pgs.fumble_recoveries)    AS fumble_recoveries
    """

    playoff_leaders = query_to_dict(
        f"""
        SELECT
            pgs.player_id,
            pgs.player_name,
            r.position,
            r.headshot_url,
            r.jersey_number,
            {_LEADER_COLS}
        FROM player_game_stats pgs
        LEFT JOIN rosters r ON pgs.player_id = r.player_id AND r.season = pgs.season
        JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type != 'REG'
        WHERE pgs.season = ? AND pgs.team = ?
        GROUP BY pgs.player_id, pgs.player_name, r.position, r.headshot_url, r.jersey_number
        """,
        [season, team],
    )

    return {"team": team, "season": season, "games": games, "leaders": leaders, "playoff_leaders": playoff_leaders}


@app.get("/leaders")
def get_leaders(season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON
    rows = query_to_dict(
        f"""
        WITH {_ROSTER_CTE},
        stats AS (
            SELECT
                pgs.player_id,
                MAX(pgs.player_name)              AS player_name,
                COUNT(DISTINCT pgs.game_id)       AS games_played,
                SUM(pgs.attempts)                 AS attempts,
                SUM(pgs.completions)              AS completions,
                SUM(pgs.pass_yards)               AS pass_yards,
                SUM(pgs.pass_tds)                 AS pass_tds,
                SUM(pgs.interceptions_thrown)     AS interceptions_thrown,
                SUM(pgs.sacks_taken)              AS sacks_taken,
                SUM(pgs.carries)                  AS carries,
                SUM(pgs.rush_yards)               AS rush_yards,
                SUM(pgs.rush_tds)                 AS rush_tds,
                SUM(pgs.targets)                  AS targets,
                SUM(pgs.receptions)               AS receptions,
                SUM(pgs.rec_yards)                AS rec_yards,
                SUM(pgs.rec_tds)                  AS rec_tds,
                SUM(pgs.yac)                      AS yac,
                SUM(pgs.pass_epa)                 AS pass_epa,
                SUM(pgs.rush_epa)                 AS rush_epa,
                SUM(pgs.rec_epa)                  AS rec_epa,
                SUM(pgs.air_yards)                AS air_yards,
                SUM(pgs.solo_tackles)             AS solo_tackles,
                SUM(pgs.assist_tackles)           AS assist_tackles,
                SUM(pgs.tackles_for_loss)         AS tackles_for_loss,
                SUM(pgs.sacks)                    AS sacks,
                SUM(pgs.qb_hits)                  AS qb_hits,
                SUM(pgs.def_interceptions)        AS def_interceptions,
                SUM(pgs.pass_breakups)            AS pass_breakups,
                SUM(pgs.forced_fumbles)           AS forced_fumbles,
                SUM(pgs.fumble_recoveries)        AS fumble_recoveries
            FROM player_game_stats pgs
            JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type = 'REG'
            WHERE pgs.season = ?
            GROUP BY pgs.player_id
        )
        SELECT s.*, r.position, r.team, r.headshot_url
        FROM stats s
        LEFT JOIN roster r ON r.player_id = s.player_id AND r.season = ?
        """,
        [season, season],
    )
    return rows


@app.get("/wpa-leaders")
def get_wpa_leaders(season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON

    passing = _safe_query(f"""
        WITH {_ROSTER_CTE},
        stats AS (
            SELECT passer_player_id AS player_id,
                   MAX(passer_player_name) AS player_name,
                   ROUND(SUM(COALESCE(air_wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) FILTER (WHERE pass_attempt = 1) AS attempts
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND pass_attempt = 1 AND passer_player_id IS NOT NULL
            GROUP BY passer_player_id
            HAVING COUNT(*) FILTER (WHERE pass_attempt = 1) >= 50
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.attempts
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    rushing = _safe_query(f"""
        WITH {_ROSTER_CTE},
        stats AS (
            SELECT rusher_player_id AS player_id,
                   MAX(rusher_player_name) AS player_name,
                   ROUND(SUM(COALESCE(wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) AS carries
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND rush_attempt = 1 AND rusher_player_id IS NOT NULL
            GROUP BY rusher_player_id
            HAVING COUNT(*) >= 50
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.carries
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    receiving = _safe_query(f"""
        WITH {_ROSTER_CTE},
        stats AS (
            SELECT receiver_player_id AS player_id,
                   MAX(receiver_player_name) AS player_name,
                   ROUND(SUM(COALESCE(yac_wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) FILTER (WHERE complete_pass = 1) AS receptions
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND complete_pass = 1 AND receiver_player_id IS NOT NULL
            GROUP BY receiver_player_id
            HAVING COUNT(*) FILTER (WHERE complete_pass = 1) >= 20
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.receptions
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    return {"passing": passing, "rushing": rushing, "receiving": receiving}


@app.get("/standings")
def get_standings(season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON

    games = query_to_dict(
        "SELECT away_team, home_team, away_score, home_score, week FROM schedules WHERE season = ? AND game_type = 'REG' ORDER BY week",
        [season],
    )

    from collections import defaultdict
    records: dict = defaultdict(lambda: {
        'w': 0, 'l': 0, 't': 0, 'pf': 0, 'pa': 0,
        'home_w': 0, 'home_l': 0, 'home_t': 0,
        'away_w': 0, 'away_l': 0, 'away_t': 0,
        'div_w':  0, 'div_l':  0, 'div_t':  0,
        'results': [],
    })

    all_teams: set[str] = set()
    for g in games:
        all_teams.add(g['away_team']); all_teams.add(g['home_team'])
        if g['away_score'] is None or g['home_score'] is None:
            continue
        a, h, as_, hs = g['away_team'], g['home_team'], g['away_score'], g['home_score']
        a_res = 'W' if as_ > hs else ('L' if hs > as_ else 'T')
        h_res = 'L' if as_ > hs else ('W' if hs > as_ else 'T')

        for team, res, home in [(a, a_res, False), (h, h_res, True)]:
            r = records[team]
            pfx = 'home_' if home else 'away_'
            opp_score = hs if home else as_
            own_score = as_ if not home else hs
            r['pf'] += own_score; r['pa'] += opp_score
            r['results'].append(res)
            if res == 'W':   r['w'] += 1; r[pfx + 'w'] += 1
            elif res == 'L': r['l'] += 1; r[pfx + 'l'] += 1
            else:            r['t'] += 1; r[pfx + 't'] += 1

        a_div, h_div = _DIVISIONS.get(a), _DIVISIONS.get(h)
        if a_div and a_div == h_div:
            if a_res == 'W':   records[a]['div_w'] += 1; records[h]['div_l'] += 1
            elif a_res == 'L': records[a]['div_l'] += 1; records[h]['div_w'] += 1
            else:              records[a]['div_t'] += 1; records[h]['div_t'] += 1

    def fmt(w: int, l: int, t: int) -> str:
        return f"{w}-{l}-{t}" if t else f"{w}-{l}"

    def streak(results: list) -> str:
        if not results: return '—'
        cur = results[-1]; cnt = 0
        for r in reversed(results):
            if r == cur: cnt += 1
            else: break
        return f"{cur}{cnt}"

    division_order = [
        'AFC East', 'AFC North', 'AFC South', 'AFC West',
        'NFC East', 'NFC North', 'NFC South', 'NFC West',
    ]
    by_div: dict[str, list] = {d: [] for d in division_order}

    for team in all_teams:
        div = _DIVISIONS.get(team)
        if not div or div not in by_div:
            continue
        r = records[team]
        gp = r['w'] + r['l'] + r['t']
        pct = (r['w'] + 0.5 * r['t']) / gp if gp else 0.0
        by_div[div].append({
            'team': team,
            'w': r['w'], 'l': r['l'], 't': r['t'],
            'pct': round(pct, 3),
            'pf': r['pf'], 'pa': r['pa'],
            'home': fmt(r['home_w'], r['home_l'], r['home_t']),
            'away': fmt(r['away_w'], r['away_l'], r['away_t']),
            'div':  fmt(r['div_w'],  r['div_l'],  r['div_t']),
            'strk': streak(r['results']),
        })

    result = []
    for div in division_order:
        teams = sorted(by_div[div], key=lambda t: (-t['pct'], -(t['pf'] - t['pa'])))
        if teams:
            lw, ll = teams[0]['w'], teams[0]['l']
            for t in teams:
                gb = ((lw - t['w']) + (t['l'] - ll)) / 2
                t['gb'] = '—' if gb == 0 else (f"{gb:.1f}".rstrip('0').rstrip('.') if gb % 1 else str(int(gb)))
        result.append({'division': div, 'teams': teams})

    return result


@app.get("/search")
def search(q: str = Query(..., min_length=1)):
    q = q.strip()
    if not q:
        return []

    ql = q.lower()

    # Team results — match abbreviation prefix or anywhere in full name
    teams = [
        {"type": "team", "id": abbrev, "name": name, "position": None, "team": abbrev, "headshot_url": None}
        for abbrev, name in _TEAM_NAMES.items()
        if ql in abbrev.lower() or ql in name.lower()
    ][:3]

    # Player results — ILIKE match, deduplicated to most recent roster entry,
    # ranked: exact match → starts-with → contains
    players = _safe_query(
        """
        SELECT
            player_id    AS id,
            player_name  AS name,
            position,
            team,
            headshot_url,
            CASE
                WHEN LOWER(player_name) = LOWER(?)            THEN 0
                WHEN LOWER(player_name) LIKE LOWER(?) || '%'  THEN 1
                ELSE 2
            END AS rank
        FROM rosters
        WHERE player_name ILIKE ?
        QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY season DESC) = 1
        ORDER BY rank, player_name
        LIMIT 8
        """,
        [q, q, f"%{q}%"],
    )

    player_results = [
        {"type": "player", "id": p["id"], "name": p["name"],
         "position": p["position"], "team": p["team"], "headshot_url": p["headshot_url"]}
        for p in players
    ]

    return (teams + player_results)[:10]
