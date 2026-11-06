"""FastAPI app entry point: wires CORS, lifespan, routers, and (in the
production image) serves the built frontend so the whole app is one service."""
import os
from contextlib import asynccontextmanager
import duckdb

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware


def _require_read_only():
    if os.environ.get('NFL_DB_READ_ONLY') == '0':
        raise RuntimeError('Serving requires a read-only snapshot; use offline jobs for writes')


# Check before config can inspect the database during import.
_require_read_only()

from config import CURRENT_SEASON
from data_errors import is_missing_data_error
from routers import assistant, leaders, live, meta, players, power_rankings, schedule, teams


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Prerequisites belong to the offline worker. Startup must not repair an
    # incomplete snapshot or accept the worker's explicit writable mode.
    _require_read_only()
    yield


app = FastAPI(title="NFL Platform", lifespan=lifespan)


@app.exception_handler(duckdb.CatalogException)
@app.exception_handler(duckdb.BinderException)
async def missing_snapshot_data(request: Request, error: Exception):
    if not is_missing_data_error(error):
        raise error
    return JSONResponse(status_code=503, content={
        'detail': 'Published data is unavailable for this view. Please try again later.'})


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
for _r in (meta, schedule, players, teams, leaders, power_rankings, assistant, live):
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
