"""Relocated-franchise abbreviation mapping (config.RELOCATIONS).

nflverse pbp/weekly label every season with the franchise's modern
abbreviation; schedules/rosters (and therefore the whole platform) are
era-keyed. These tests pin the mapping in both its SQL and pandas forms.
"""
import duckdb
import pandas as pd

from config import RELOCATIONS, era_team_case
from ingest import normalize_relocated_teams


def _sql_map(team: str, season: int):
    case = era_team_case("t.team", "t.season")
    return duckdb.sql(
        f"SELECT {case} FROM (SELECT '{team}' AS team, {season} AS season) t"
    ).fetchone()[0]


def test_era_team_case_maps_pre_move_seasons():
    assert _sql_map("LV", 2015) == "OAK"
    assert _sql_map("LV", 2019) == "OAK"   # last Oakland season
    assert _sql_map("LAC", 2016) == "SD"
    assert _sql_map("LA", 2015) == "STL"


def test_era_team_case_leaves_post_move_and_others_alone():
    assert _sql_map("LV", 2020) == "LV"    # first Las Vegas season
    assert _sql_map("LAC", 2017) == "LAC"
    assert _sql_map("LA", 2016) == "LA"
    assert _sql_map("KC", 2005) == "KC"


def test_normalize_relocated_teams_dataframe():
    df = pd.DataFrame({
        "team":   ["LV", "LV", "LAC", "LA", "KC"],
        "season": [2015, 2020, 2010, 2024, 2010],
        "solo_tackles": [1, 1, 1, 1, 1],
    })
    out = normalize_relocated_teams(df)
    assert list(out["team"]) == ["OAK", "LV", "SD", "LA", "KC"]


def test_normalize_relocated_teams_handles_missing_columns():
    df = pd.DataFrame({"player_id": ["x"]})
    assert normalize_relocated_teams(df) is df
    empty = pd.DataFrame()
    assert normalize_relocated_teams(empty) is empty


def test_relocations_map_shape():
    # (modern, era, last_era_season) — guard against accidental reordering
    for modern, era, last in RELOCATIONS:
        assert isinstance(last, int) and 2015 <= last <= 2019
        assert modern != era
