"""FastAPI app entry point: wires CORS, lifespan, and includes all routers."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import AUTO_LOAD_SEASONS, CURRENT_SEASON, FIRST_SEASON
from database import query_to_dict
from ingest_queue import queue_season, start_worker
from routers import leaders, meta, players, schedule, teams


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the single background ingest worker
    start_worker()

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
