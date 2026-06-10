"""FastAPI app entry point: wires CORS, lifespan, routers, and (in the
production image) serves the built frontend so the whole app is one service."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.gzip import GZipMiddleware

from config import AUTO_LOAD_SEASONS, CURRENT_SEASON, FIRST_SEASON
from database import ensure_indexes, get_connection, query_to_dict
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

    # Point-lookup indexes on the large tables hit per request (idempotent;
    # persisted by DuckDB so this is a no-op after the first build).
    ensure_indexes()

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


@app.middleware("http")
async def cache_control(request: Request, call_next):
    """Let browsers/CDNs cache responses. Completed seasons are immutable, so
    cache them hard; everything else gets a short window so live data stays
    fresh. Endpoints that opt out (e.g. /seasons) set their own header first."""
    response = await call_next(request)
    if request.method == "GET" and response.status_code == 200:
        season = request.query_params.get("season")
        if season and season.isdigit() and int(season) < CURRENT_SEASON:
            response.headers["Cache-Control"] = "public, max-age=604800"  # 1 week
        else:
            response.headers.setdefault("Cache-Control", "public, max-age=300")  # 5 min
    return response


# Compress JSON responses — these payloads gzip ~10-20x (a veteran's splits go
# from ~570KB to ~46KB), the dominant transfer cost.
app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All API routes live under /api so the frontend (served at /) and the API can
# share one origin in production. The Vite dev proxy forwards /api unchanged.
for _r in (meta, schedule, players, teams, leaders):
    app.include_router(_r.router, prefix="/api")


@app.get("/api/health")
def health():
    """Liveness probe for the platform (Cloud Run / uptime checks)."""
    return {"status": "ok"}


# ── Serve the built frontend (production single-service deploy) ───────────────
# In dev the frontend runs on Vite; the Docker image copies the build into
# ./static and serves it here with SPA fallback to index.html for client routes.
_STATIC = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC):
    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = os.path.normpath(os.path.join(_STATIC, full_path))
        if full_path and candidate.startswith(_STATIC) and os.path.isfile(candidate):
            # content-hashed assets are immutable; the HTML shell is not
            cache = "public, max-age=31536000, immutable" if "/assets/" in full_path else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(os.path.join(_STATIC, "index.html"), headers={"Cache-Control": "no-cache"})
