"""Player HTTP endpoints; statistical assembly belongs to services."""
from fastapi import APIRouter, HTTPException, Query
from schemas.leaders import PlayerComparable
from schemas.players import PlayerProfile, PlayerSplit, DefensiveSplit
from services.player_profile import get_player_profile
from services.receiving_coverage import mask_target_fields, targets_unavailable
import comparables_builder
import splits_builder
import def_splits_builder

router = APIRouter()


@router.get("/players/{player_id}", response_model=PlayerProfile)
def get_player(player_id: str):
    profile = get_player_profile(player_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
    return profile


@router.get("/players/{player_id}/comparables", response_model=list[PlayerComparable])
def get_player_comparables(player_id: str, n: int = Query(default=8, ge=1, le=20)):
    rows = comparables_builder.read_or_materialize(player_id, n)
    # A career range touching a gap cannot claim a complete career target total.
    return [dict(row, targets=None) if targets_unavailable(range(row["first_season"], row["last_season"] + 1))
            else row for row in rows]


@router.get("/players/{player_id}/splits", response_model=list[PlayerSplit])
def get_player_splits(player_id: str):
    rows = splits_builder.read_or_materialize(player_id)
    return [mask_target_fields(row, row["season"], split=True) if row["category"] == "receiving"
            else row for row in rows]


@router.get("/players/{player_id}/def-splits", response_model=list[DefensiveSplit])
def get_player_def_splits(player_id: str):
    """A defender's event line conditioned on one situational dimension."""
    return def_splits_builder.read_or_materialize(player_id)
