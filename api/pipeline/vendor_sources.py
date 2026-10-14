"""Optional vendor adapters and the asset catalog used by refresh tracking."""
from dataclasses import dataclass, replace
from typing import Literal
from urllib.error import HTTPError, URLError

import pandas as pd

from pipeline.normalization import latest_depth_snapshot, normalize_ftn
from pipeline.source_results import SourceError, SourceOutcome, VendorFeed

RELEASE_BASE = 'https://github.com/nflverse/nflverse-data/releases/download/'
HISTORICAL_SEASONS = range(1980, 2030)


@dataclass(frozen=True)
class VendorSource:
    name: str
    release: str | None
    asset: str
    first_season: int
    scope: Literal['season', 'reference', 'snapshot'] = 'season'
    watermark: str | None = None
    required_columns: tuple[str, ...] = ('season',)

    @property
    def url(self) -> str:
        return f'{RELEASE_BASE}{self.release}/{self.asset}' if self.release else self.asset


PFR_SOURCES = tuple(
    VendorSource(f'pfr_{kind}', 'pfr_advstats', f'advstats_season_{kind}.parquet', 2018,
                 watermark=f'pfr_{kind}', required_columns=('season', 'pfr_id'))
    for kind in ('pass', 'rush', 'rec', 'def')
)
NGS_SOURCES = tuple(
    VendorSource(f'ngs_{kind}', 'nextgen_stats', f'ngs_{kind}.parquet', 2016,
                 watermark=f'ngs_{kind}', required_columns=('season', 'player_gsis_id'))
    for kind in ('passing', 'rushing', 'receiving')
)
SNAPS = VendorSource('snap_counts', 'snap_counts', 'snap_counts_{season}.parquet', 2012,
                     watermark='snaps', required_columns=('season', 'game_id', 'pfr_player_id'))
FTN = VendorSource('ftn_charting', 'ftn_charting', 'ftn_charting_{season}.parquet', 2022,
                   watermark='ftn', required_columns=('season', 'nflverse_game_id', 'nflverse_play_id'))
ADVANCED_SOURCES = (*PFR_SOURCES, *NGS_SOURCES, SNAPS, FTN)
SUPPLEMENTAL_SOURCES = (
    VendorSource('injuries', 'injuries', 'injuries_{season}.parquet', 2009),
    VendorSource('depth_charts', 'depth_charts', 'depth_charts_{season}.parquet', 2001,
                 scope='snapshot', required_columns=('dt',)),
    *(VendorSource(f'qbr_{frequency}', None,
                   f'https://raw.githubusercontent.com/nflverse/espnscrapeR-data/master/data/qbr-nfl-{frequency}.csv',
                   2006) for frequency in ('season', 'weekly')),
    VendorSource('draft_picks', 'draft_picks', 'draft_picks.parquet', 1980, scope='reference'),
    VendorSource('combine_data', 'combine', 'combine.parquet', 2000, scope='reference'),
    VendorSource('id_map', None,
                 'https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv',
                 1980, scope='reference', required_columns=('gsis_id', 'pfr_id')),
)
WATCHED_VENDOR_SOURCES = {s.watermark: s for s in ADVANCED_SOURCES if s.watermark}


def _read_optional(spec: VendorSource, url: str, seasons: list[int | None]):
    """Expected remote outages retain stored data; code/schema faults still fail."""
    try:
        frame = pd.read_csv(url) if url.endswith('.csv') else pd.read_parquet(url)
    except HTTPError as error:
        status = 'not_found' if error.code == 404 else 'failed'
        return None, [SourceOutcome(spec.name, s, status, detail=f'HTTP {error.code}') for s in seasons]
    except (URLError, TimeoutError, ConnectionError) as error:
        return None, [SourceOutcome(spec.name, s, 'failed', detail=type(error).__name__) for s in seasons]
    except Exception as error:
        raise SourceError(spec.name, seasons[0], f'download failed ({type(error).__name__})') from error
    if not isinstance(frame, pd.DataFrame):
        raise SourceError(spec.name, seasons[0], 'download did not return a data frame')
    if frame.empty:
        return None, [SourceOutcome(spec.name, s, 'empty') for s in seasons]
    if spec.scope == 'snapshot' and 'dt' not in frame.columns:
        return None, [SourceOutcome(spec.name, s, 'unsupported_format', detail='no dt column') for s in seasons]
    absent = [c for c in spec.required_columns if c not in frame.columns]
    if absent:
        raise SourceError(spec.name, seasons[0], f'feed is missing required columns {absent}')
    return frame, []


def fetch_vendor(spec: VendorSource, seasons: list[int], log=print) -> VendorFeed:
    """Fetch supported years and report every requested source/year separately."""
    requested = list(dict.fromkeys(seasons))
    outcomes = []
    frames = []
    snapshots = {}
    if spec.scope == 'reference':
        frame, outcomes = _read_optional(spec, spec.url, [None])
        if frame is not None:
            if 'season' in frame.columns:
                frame = frame[frame['season'].isin(HISTORICAL_SEASONS)]
            outcomes = [SourceOutcome(spec.name, None, 'loaded' if not frame.empty else 'empty', len(frame))]
            if not frame.empty:
                frames.append(frame)
    else:
        supported = [s for s in requested if s >= spec.first_season]
        outcomes.extend(SourceOutcome(spec.name, s, 'unsupported') for s in requested if s not in supported)
        # Whole-history PFR/NGS/QBR assets are read once, seasonal assets once
        # per supported year. No failed/missing year enters a storage replacement.
        groups = [[s] for s in supported] if '{season}' in spec.asset else ([supported] if supported else [])
        for group in groups:
            frame, gaps = _read_optional(spec, spec.url.format(season=group[0]), group)
            outcomes.extend(gaps)
            if frame is None:
                continue
            if spec.scope != 'snapshot' and '{season}' in spec.asset:
                if frame['season'].isna().any() or not frame['season'].eq(group[0]).all():
                    raise SourceError(spec.name, group[0], 'asset contains unexpected seasons')
            for season in group:
                selected = frame if spec.scope == 'snapshot' else frame[frame['season'].eq(season)]
                outcomes.append(SourceOutcome(spec.name, season, 'loaded' if not selected.empty else 'empty', len(selected)))
                if not selected.empty:
                    frames.append(selected)
                    if spec.scope == 'snapshot':
                        snapshots[season] = selected
    data = pd.concat(frames, ignore_index=True) if frames else None
    if data is not None and spec.name == 'ftn_charting':
        data = normalize_ftn(data)
    if data is not None and spec.scope == 'snapshot':
        data = latest_depth_snapshot(data)
        if data.empty:
            raise SourceError(spec.name, requested[0], 'snapshot has no valid timestamp')
        latest = data['dt'].max()
        for index, outcome in enumerate(outcomes):
            if outcome.status == 'loaded':
                rows = int(snapshots[outcome.season]['dt'].eq(latest).sum())
                outcomes[index] = replace(outcome, rows=rows, status='loaded' if rows else 'empty',
                                          detail='' if rows else 'older snapshots excluded')
    for outcome in outcomes:
        label = outcome.season if outcome.season is not None else 'reference'
        storage = 'new rows available' if outcome.status == 'loaded' else 'stored data retained'
        log(f'  {outcome.source}[{label}]: {outcome.status}, {outcome.rows} rows; {storage}'
            + (f' ({outcome.detail})' if outcome.detail else ''))
    return VendorFeed(spec.name, data, outcomes)
