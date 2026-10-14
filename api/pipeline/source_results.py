"""Source outcomes shared by downloads, storage orchestration and refresh tracking."""
from dataclasses import dataclass
from typing import Literal

import pandas as pd


class SourceError(RuntimeError):
    """A feed failed validation or cannot supply data required by this refresh."""

    def __init__(self, source: str, season: int | None, reason: str):
        self.source = source
        self.season = season
        label = season if season is not None else 'reference'
        super().__init__(f'{source}[{label}]: {reason}')


@dataclass(frozen=True)
class SourceOutcome:
    source: str
    season: int | None
    status: Literal['loaded', 'empty', 'not_found', 'unsupported', 'unsupported_format', 'failed']
    rows: int = 0
    detail: str = ''


@dataclass
class VendorFeed:
    source: str
    data: pd.DataFrame | None
    outcomes: list[SourceOutcome]

    @property
    def loaded_seasons(self) -> list[int]:
        return [o.season for o in self.outcomes if o.status == 'loaded' and o.season is not None]
