"""Read-only health/season discovery; retired ingest URLs cannot start writes."""
from fastapi import APIRouter, HTTPException, Response

from config import CURRENT_SEASON, FIRST_SEASON
from services.seasons import get_season_coverage
from schemas.meta import HealthResponse, LoadSeasonResponse, SeasonStatus

router = APIRouter()


@router.get('/health', response_model=HealthResponse)
def health():
    return {'status': 'ok'}


@router.get('/seasons', response_model=list[SeasonStatus])
def get_seasons(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    played, scheduled = get_season_coverage()
    return [{'season': year, 'status': 'loaded' if year in played else
             'scheduled' if year in scheduled else 'available'}
            for year in range(CURRENT_SEASON, FIRST_SEASON - 1, -1)]


_RETIRED = 'Ingest runs offline. This service only reads published snapshots.'


@router.post('/seasons/{year}/load', response_model=LoadSeasonResponse, deprecated=True,
             responses={410: {'description': 'Ingest moved to offline jobs'}})
def load_season(year: int):
    raise HTTPException(status_code=410, detail=_RETIRED)


@router.get('/seasons/{year}/progress', deprecated=True,
            responses={410: {'description': 'Ingest progress is available in offline job logs'}})
def season_progress(year: int):
    raise HTTPException(status_code=410, detail=_RETIRED)