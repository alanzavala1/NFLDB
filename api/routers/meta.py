"""Health check and season ingest endpoints."""
import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from config import CURRENT_SEASON, FIRST_SEASON
from database import query_to_dict
from ingest_queue import ingest_logs, queue_season, season_status
from schemas.meta import HealthResponse, LoadSeasonResponse, SeasonStatus

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@router.get("/seasons", response_model=list[SeasonStatus])
def get_seasons():
    try:
        loaded = {r["season"] for r in query_to_dict("SELECT DISTINCT season FROM schedules")}
    except Exception:
        loaded = set()
    return [
        {
            "season": year,
            "status": season_status.get(year, "loaded" if year in loaded else "available"),
        }
        for year in range(CURRENT_SEASON, FIRST_SEASON - 1, -1)
    ]


@router.post("/seasons/{year}/load", response_model=LoadSeasonResponse)
def load_season(year: int, force: bool = False):
    if year < FIRST_SEASON or year > CURRENT_SEASON:
        raise HTTPException(status_code=400, detail=f"Season must be between {FIRST_SEASON} and {CURRENT_SEASON}")
    status = queue_season(year, force=force)
    return {"season": year, "status": status}


@router.get("/seasons/{year}/progress")
def season_progress(year: int):
    async def event_stream():
        sent = 0
        while True:
            logs = ingest_logs.get(year, [])
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
