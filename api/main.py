"""FastAPI app entry point: wires CORS, lifespan, and includes all routers."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import AUTO_LOAD_SEASONS, CURRENT_SEASON, FIRST_SEASON
from database import get_connection, query_to_dict
from ingest_queue import queue_season, start_worker
from routers import leaders, meta, players, schedule, teams


def _ensure_player_awards() -> None:
    """Build the player_awards table on startup if it's missing or empty.

    The data is a static seed (see awards_seed.py) — refreshing it doesn't
    require network calls, so we can do it transparently on every cold
    boot. Skips if the table already has rows so subsequent restarts are
    instant.
    """
    try:
        conn = get_connection()
        n = conn.execute(
            "SELECT COUNT(*) FROM player_awards"
        ).fetchone()[0] if any(
            r[0] == 'player_awards' for r in conn.execute("SHOW TABLES").fetchall()
        ) else 0
        if n == 0:
            import ingest
            ingest._load_player_awards(conn)
    except Exception as e:
        print(f"awards seed load failed (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the single background ingest worker
    start_worker()

    # Static seed data — populate on first boot if not already loaded
    _ensure_player_awards()

    # Auto-queue the N most recent seasons that aren't already in the DB.
    # If we can't read what's loaded (e.g. the DB is momentarily locked by
    # another process), DON'T treat that as "nothing loaded" — that would
    # re-ingest seasons we already have. Skip auto-load for this boot instead.
    try:
        loaded = {r["season"] for r in query_to_dict("SELECT DISTINCT season FROM schedules")}
    except Exception as e:
        print(f"startup: could not read loaded seasons ({e}); skipping auto-load this boot")
        loaded = None

    if loaded is not None:
        queued = 0
        for year in range(CURRENT_SEASON, FIRST_SEASON - 1, -1):
            if queued >= AUTO_LOAD_SEASONS:
                break
            if year not in loaded:
                queue_season(year, force=False)
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

app.include_router(meta.router)
app.include_router(schedule.router)
app.include_router(players.router)
app.include_router(teams.router)
app.include_router(leaders.router)
