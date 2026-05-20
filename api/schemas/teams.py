"""Response schemas for the teams router."""
from pydantic import BaseModel


class RosterPlayer(BaseModel):
    player_id: str
    player_name: str
    position: str | None = None
    jersey_number: int | None = None
    headshot_url: str | None = None
