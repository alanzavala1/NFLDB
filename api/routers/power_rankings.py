"""Weekly EPA power rankings endpoint."""
from collections import defaultdict

from fastapi import APIRouter, Query

import power_rankings_builder
from config import CURRENT_SEASON
from database import query_to_dict
from schemas.ratings import PowerRankingRow

router = APIRouter()


def _fmt_record(w: int, l: int, t: int) -> str:
    return f"{w}-{l}-{t}" if t else f"{w}-{l}"


def _records_through_week(season: int, week: int) -> dict[str, str]:
    games = query_to_dict(
        """
        SELECT away_team, home_team, away_score, home_score
        FROM schedules
        WHERE season = ?
          AND game_type = 'REG'
          AND week <= ?
          AND away_score IS NOT NULL
          AND home_score IS NOT NULL
        """,
        [int(season), int(week)],
    )
    records: dict[str, dict[str, int]] = defaultdict(lambda: {"w": 0, "l": 0, "t": 0})
    for g in games:
        a, h = g["away_team"], g["home_team"]
        as_, hs = g["away_score"], g["home_score"]
        if as_ > hs:
            records[a]["w"] += 1
            records[h]["l"] += 1
        elif hs > as_:
            records[a]["l"] += 1
            records[h]["w"] += 1
        else:
            records[a]["t"] += 1
            records[h]["t"] += 1
    return {
        team: _fmt_record(row["w"], row["l"], row["t"])
        for team, row in records.items()
    }


@router.get("/power-rankings", response_model=list[PowerRankingRow])
def get_power_rankings(
    season: int = Query(default=CURRENT_SEASON),
    week: int | None = Query(default=None, ge=1, le=22),
):
    rows = power_rankings_builder.read_or_materialize(season, week)
    if not rows:
        return []

    selected_week = int(rows[0]["week"])
    records = _records_through_week(season, selected_week)
    return [
        {
            "rank": int(row["rank"]),
            "team": row["team"],
            "record": records.get(row["team"], "0-0"),
            "net_epa_play": row["net_epa_play"],
            "movement": row["movement"],
        }
        for row in rows
    ]
