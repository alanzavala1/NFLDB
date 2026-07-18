"""Free DB-backed contract tests for the /ask coverage tools.

The tools must reconcile with the existing router payloads while returning a
small model-facing projection. These checks skip when the full local DuckDB is
absent and never call the LLM.
"""
import json
import os

import duckdb
import pytest

_DB = os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")

pytestmark = pytest.mark.skipif(
    not os.path.exists(_DB),
    reason="real nfl.duckdb required for ask coverage-tool checks",
)

_HENRY_ID = "00-0032764"
_RODGERS_ID = "00-0023459"


@pytest.fixture(autouse=True)
def _read_only_database(monkeypatch):
    import database

    conn = duckdb.connect(_DB, read_only=True)
    monkeypatch.setattr(database, "_conn", conn)
    try:
        yield
    finally:
        conn.close()


def _tool(name):
    import llm

    ctx = llm._Ctx()
    return next(tool.func for tool in llm._build_tools(ctx) if tool.name == name)


def test_find_games_filters_known_game_and_keeps_playoffs_in_capped_preview():
    find_games = _tool("find_games")
    hint = (
        "find_games returns only schedule info and scores; call "
        "get_game_detail(game_id) for coaches, quarter scores, and top performers."
    )

    filtered_raw = find_games(season=2023, team="BUF", week=14)
    filtered = json.loads(filtered_raw)
    assert filtered["matched"] == 1
    assert filtered["hint"] == hint
    assert filtered["games"][0] == {
        "game_id": "2023_14_BUF_KC",
        "week": 14,
        "game_type": "REG",
        "gameday": "2023-12-10",
        "away_team": "BUF",
        "home_team": "KC",
        "away_score": 20.0,
        "home_score": 17.0,
        "overtime": False,
    }

    preview_raw = _tool("find_games")(season=2022)
    preview = json.loads(preview_raw)
    assert preview["truncated"] is True
    assert preview["hint"] == hint
    assert len(preview["games"]) == 25
    assert all(game.get("game_id") for game in preview["games"])
    assert any(game["game_type"] == "SB" and game["home_score"] == 35
               for game in preview["games"])
    assert len(preview_raw) < 4000


def test_get_game_detail_trims_the_known_super_bowl_box_score():
    raw = _tool("get_game_detail")(game_id="2022_22_KC_PHI")
    detail = json.loads(raw)

    assert detail["game"]["away_score"] == 38.0
    assert detail["game"]["home_score"] == 35.0
    assert detail["game"]["away_coach"] == "Andy Reid"
    assert sum(q["away"] for q in detail["quarter_scores"]) == 38
    assert all(len(rows) <= 5 for rows in detail["top_performers"].values())
    assert any(row.get("pass_yards") == 182.0
               for row in detail["top_performers"]["KC"])
    assert len(raw) < 4000


def test_get_player_game_log_reconciles_with_profile_week_row():
    from routers.players import get_player

    expected = next(
        game for game in get_player(_HENRY_ID)["games"]
        if game["season"] == 2020 and game["week"] == 8 and game["game_type"] == "REG"
    )
    raw = _tool("get_player_game_log")(player_id=_HENRY_ID, season=2020)
    log = json.loads(raw)
    week = next(game for game in log["games"] if game["week"] == 8)

    assert week["opponent"] == expected["opponent"] == "CIN"
    assert week["rush_yards"] == expected["rush_yards"] == 112.0
    assert week["carries"] == expected["carries"] == 18.0
    assert len(log["games"]) <= 25
    assert len(raw) < 7000


def test_get_player_career_reconciles_with_regular_profile_games():
    from routers.players import get_player

    regular = [game for game in get_player(_RODGERS_ID)["games"] if game["game_type"] == "REG"]
    expected_tds = sum(game["pass_tds"] or 0 for game in regular)
    raw = _tool("get_player_career")(player_id=_RODGERS_ID)
    career = json.loads(raw)

    assert career["career_total"]["pass_tds"] == expected_tds
    assert career["career_total"]["games_played"] == len(regular)
    assert career["career_total"]["seasons"] == len({game["season"] for game in regular})
    assert len(career["seasons"]) <= 25
    assert len(raw) < 8000


def test_get_team_overview_returns_verified_past_standing_without_current_report():
    overview = json.loads(_tool("get_team_overview")(team="BAL", season=2023))

    assert overview["record"] == "13-4"
    assert overview["regular_season_games"] == 17
    assert overview["standing"]["division"] == "AFC North"
    assert "current_injuries" not in overview
    assert "offensive_starters" not in overview


def test_get_power_rankings_matches_platform_model_and_caps_rows():
    from routers.power_rankings import get_power_rankings

    expected = next(row for row in get_power_rankings(2023, None) if row["team"] == "KC")
    raw = _tool("get_power_rankings")(season=2023)
    payload = json.loads(raw)
    chiefs = next(row for row in payload["rankings"] if row["team"] == "KC")

    assert chiefs["rank"] == expected["rank"] == 6
    assert chiefs["record"] == expected["record"] == "11-6"
    assert chiefs["net_epa_play"] == expected["net_epa_play"]
    assert len(payload["rankings"]) <= 25
    assert len(raw) < 3000
