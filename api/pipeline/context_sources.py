"""Schedule and roster adapters; retain the installed library's normalization."""
from urllib.error import HTTPError

import nfl_data_py
import pandas as pd

from pipeline.source_results import SourceError, SeasonalFeed

SCHEDULE_CSV = 'http://www.habitatring.com/games.csv'


def _fetch(source, season, fetch, *, allow_missing=False):
    try:
        frame = fetch()
    except HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        raise SourceError(source, season, f'download failed (HTTP {error.code})') from error
    except Exception as error:
        raise SourceError(source, season, f'download failed ({type(error).__name__})') from error
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise SourceError(source, season, 'published asset returned no usable rows')
    return frame


def fetch_schedules(seasons: list[int]) -> SeasonalFeed:
    requested = list(dict.fromkeys(seasons))
    frame = _fetch('schedules', requested[0], lambda: pd.read_csv(SCHEDULE_CSV))
    required = ('season', 'game_id', 'week', 'away_team', 'home_team', 'away_score', 'home_score')
    absent = [c for c in required if c not in frame.columns]
    if absent:
        raise SourceError('schedules', requested[0], f'feed is missing required columns {absent}')
    frame = frame[frame['season'].isin(requested)].copy()
    for season in requested:
        if not frame['season'].eq(season).any():
            raise SourceError('schedules', season, 'requested season has no schedule rows')
    return SeasonalFeed(frame, requested, [])


def fetch_rosters(seasons: list[int]) -> SeasonalFeed:
    """Keep roster naming, date/age calculation and unidentified-row filtering."""
    frames, loaded, missing = [], [], []
    for season in dict.fromkeys(seasons):
        frame = _fetch('rosters', season,
                       lambda: nfl_data_py.import_seasonal_rosters([season]), allow_missing=True)
        if frame is None:
            missing.append(season)
            continue
        absent = [c for c in ('season', 'player_id', 'player_name') if c not in frame.columns]
        if absent:
            raise SourceError('rosters', season, f'feed is missing required columns {absent}')
        if frame['season'].isna().any() or not frame['season'].eq(season).all():
            raise SourceError('rosters', season, 'asset contains unexpected seasons')
        frames.append(frame)
        loaded.append(season)
    return SeasonalFeed(pd.concat(frames, ignore_index=True) if frames else None, loaded, missing)
