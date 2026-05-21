"""Response schemas for /standings."""
from pydantic import BaseModel


class StandingsRow(BaseModel):
    team: str
    w: int
    l: int
    t: int
    pct: float
    pf: int
    pa: int
    home: str   # "W-L" or "W-L-T"
    away: str
    div:  str
    strk: str   # "W2", "L1", "—"
    gb:   str   # "—" for the division leader, e.g. "1", "2.5" otherwise


class DivisionStandings(BaseModel):
    division: str
    teams: list[StandingsRow]
