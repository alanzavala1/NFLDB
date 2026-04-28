import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from database import query_to_dict
from ingest import run_ingest

FIRST_SEASON = 1999
CURRENT_SEASON = 2025

_season_status: dict[int, str] = {}  # year -> "loading" | "error"
_ingest_logs: dict[int, list[str]] = {}  # year -> list of log lines
_ingest_lock = threading.Lock()


def _ingest_season(year: int):
    _ingest_logs[year] = []

    def log(msg: str):
        line = str(msg).strip()
        print(line)
        _ingest_logs.setdefault(year, []).append(line)

    with _ingest_lock:
        try:
            run_ingest([year], log=log)
            _season_status.pop(year, None)
            _ingest_logs.setdefault(year, []).append("__DONE__")
        except Exception as e:
            print(f"Ingest failed for {year}: {e}")
            _season_status[year] = "error"
            _ingest_logs.setdefault(year, []).append(f"__ERROR__ {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-load current season on startup if not already present
    try:
        loaded = {r["season"] for r in query_to_dict("SELECT DISTINCT season FROM schedules")}
    except Exception:
        loaded = set()
    if CURRENT_SEASON not in loaded and _season_status.get(CURRENT_SEASON) != "loading":
        _season_status[CURRENT_SEASON] = "loading"
        threading.Thread(target=_ingest_season, args=(CURRENT_SEASON,), daemon=True).start()
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
def load_season(year: int, background_tasks: BackgroundTasks, force: bool = False):
    if year < FIRST_SEASON or year > CURRENT_SEASON:
        raise HTTPException(status_code=400, detail=f"Season must be between {FIRST_SEASON} and {CURRENT_SEASON}")

    if _season_status.get(year) == "loading":
        return {"season": year, "status": "loading"}

    loaded = {r["season"] for r in query_to_dict("SELECT DISTINCT season FROM schedules")}
    if year in loaded and not force:
        return {"season": year, "status": "loaded"}

    _season_status[year] = "loading"
    background_tasks.add_task(_ingest_season, year)
    return {"season": year, "status": "loading"}


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

    players = query_to_dict(
        """
        SELECT
            pgs.player_id,
            pgs.player_name,
            pgs.team,
            pgs.week,
            r.position,
            r.jersey_number,
            r.headshot_url,
            pgs.attempts, pgs.completions, pgs.pass_yards, pgs.pass_tds,
            pgs.interceptions_thrown, pgs.sacks_taken, pgs.pass_epa,
            pgs.targets, pgs.receptions, pgs.rec_yards, pgs.rec_tds,
            pgs.air_yards, pgs.yac, pgs.rec_epa,
            pgs.carries, pgs.rush_yards, pgs.rush_tds, pgs.rush_epa,
            pgs.solo_tackles, pgs.assist_tackles, pgs.tackles_for_loss,
            pgs.sacks, pgs.qb_hits, pgs.def_interceptions,
            pgs.pass_breakups, pgs.forced_fumbles, pgs.fumble_recoveries,
            pgs.fg_att, pgs.fg_made, pgs.xp_att, pgs.xp_made,
            pgs.punts, pgs.punt_yards,
            pgs.punt_returns, pgs.punt_return_yards, pgs.punt_return_tds
        FROM player_game_stats pgs
        LEFT JOIN rosters r ON pgs.player_id = r.player_id AND r.season = pgs.season
        WHERE pgs.game_id = ?
        ORDER BY pgs.team, r.position, pgs.player_name
        """,
        [game_id],
    )

    away_team = game["away_team"]
    home_team = game["home_team"]

    return {
        **game,
        "away": [p for p in players if p["team"] == away_team],
        "home": [p for p in players if p["team"] == home_team],
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

    games = query_to_dict(
        """
        SELECT
            pgs.game_id,
            pgs.season,
            pgs.week,
            pgs.team,
            CASE WHEN pgs.team = s.home_team THEN s.away_team ELSE s.home_team END AS opponent,
            CASE WHEN pgs.team = s.home_team THEN 'home' ELSE 'away' END           AS location,
            s.gameday,
            s.away_score,
            s.home_score,
            CASE
                WHEN s.away_score IS NULL                                          THEN NULL
                WHEN pgs.team = s.home_team AND s.home_score > s.away_score       THEN 'W'
                WHEN pgs.team = s.away_team AND s.away_score > s.home_score       THEN 'W'
                WHEN s.home_score = s.away_score                                  THEN 'T'
                ELSE 'L'
            END AS result,
            pgs.attempts, pgs.completions, pgs.pass_yards, pgs.pass_tds,
            pgs.interceptions_thrown, pgs.sacks_taken, pgs.pass_epa,
            pgs.targets, pgs.receptions, pgs.rec_yards, pgs.rec_tds,
            pgs.air_yards, pgs.yac, pgs.rec_epa,
            pgs.carries, pgs.rush_yards, pgs.rush_tds, pgs.rush_epa,
            pgs.solo_tackles, pgs.assist_tackles, pgs.tackles_for_loss,
            pgs.sacks, pgs.qb_hits, pgs.def_interceptions,
            pgs.pass_breakups, pgs.forced_fumbles, pgs.fumble_recoveries,
            pgs.fg_att, pgs.fg_made, pgs.xp_att, pgs.xp_made,
            pgs.punts, pgs.punt_yards,
            pgs.punt_returns, pgs.punt_return_yards, pgs.punt_return_tds
        FROM player_game_stats pgs
        LEFT JOIN schedules s ON pgs.game_id = s.game_id
        WHERE pgs.player_id = ?
        ORDER BY pgs.season, pgs.week
        """,
        [player_id],
    )

    numeric_stat_cols = [
        "attempts", "completions", "pass_yards", "pass_tds", "interceptions_thrown",
        "sacks_taken", "pass_epa", "targets", "receptions", "rec_yards", "rec_tds",
        "air_yards", "yac", "rec_epa", "carries", "rush_yards", "rush_tds", "rush_epa",
        "solo_tackles", "assist_tackles", "tackles_for_loss", "sacks", "qb_hits",
        "def_interceptions", "pass_breakups", "forced_fumbles", "fumble_recoveries",
        "fg_att", "fg_made", "xp_att", "xp_made", "punts", "punt_yards",
        "punt_returns", "punt_return_yards", "punt_return_tds",
    ]
    season_totals = {col: sum(g[col] or 0 for g in games) for col in numeric_stat_cols}

    return {
        **profile,
        "games_played": len(games),
        "season_totals": season_totals,
        "games": games,
        "ngs": _get_ngs(player_id),
        "snap_totals": _get_snap_totals(player_id),
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
            SUM(pgs.carries)              AS carries,
            SUM(pgs.rush_yards)           AS rush_yards,
            SUM(pgs.rush_tds)             AS rush_tds,
            SUM(pgs.targets)              AS targets,
            SUM(pgs.receptions)           AS receptions,
            SUM(pgs.rec_yards)            AS rec_yards,
            SUM(pgs.rec_tds)              AS rec_tds,
            SUM(pgs.yac)                  AS yac,
            SUM(pgs.solo_tackles)         AS solo_tackles,
            SUM(pgs.assist_tackles)       AS assist_tackles,
            SUM(pgs.sacks)                AS sacks,
            SUM(pgs.tackles_for_loss)     AS tackles_for_loss,
            SUM(pgs.def_interceptions)    AS def_interceptions,
            SUM(pgs.pass_breakups)        AS pass_breakups,
            SUM(pgs.forced_fumbles)       AS forced_fumbles
        FROM player_game_stats pgs
        LEFT JOIN rosters r ON pgs.player_id = r.player_id AND r.season = pgs.season
        WHERE pgs.season = ? AND pgs.team = ?
        GROUP BY pgs.player_id, pgs.player_name, r.position, r.headshot_url, r.jersey_number
        """,
        [season, team],
    )

    return {"team": team, "season": season, "games": games, "leaders": leaders}
