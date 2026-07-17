"""Free DB-backed checks for the /ask play-query semantic layer.

The model supplies only validated values; SQL identifiers and metric
definitions remain server-owned. These tests never call the LLM.
"""
import json
import os

import duckdb
import pytest

_DB = os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")

pytestmark = pytest.mark.skipif(
    not os.path.exists(_DB),
    reason="real nfl.duckdb required for query_plays checks",
)


@pytest.fixture(autouse=True)
def _read_only_database(monkeypatch):
    import database
    import llm

    conn = duckdb.connect(_DB, read_only=True)
    monkeypatch.setattr(database, "_conn", conn)
    monkeypatch.setattr(llm, "_plays_columns_cache", None)
    monkeypatch.setattr(llm, "_plays_seasons_cache", None)
    try:
        yield
    finally:
        conn.close()


def _tool():
    import llm

    ctx = llm._Ctx()
    return next(tool.func for tool in llm._build_tools(ctx) if tool.name == "query_plays")


def test_invalid_whitelist_values_never_reach_sql(monkeypatch):
    import llm

    def unexpected_query(*args, **kwargs):
        pytest.fail("invalid query_plays value reached SQL")

    monkeypatch.setattr(llm, "query_to_dict", unexpected_query)
    query_plays = _tool()

    assert query_plays(
        season=2022, group_by="epa; DROP TABLE plays"
    ).startswith("Invalid group_by")
    assert query_plays(
        season=2022, offense="PHI; DROP TABLE plays"
    ).startswith("Invalid offense")
    assert query_plays(season=2022, play="screen").startswith("Invalid play")
    assert query_plays(season=2022, passer_id="Mahomes") == (
        "That is not a player id — call resolve_entity first and use the returned id."
    )
    hostile = query_plays(season=2022, season_type="REG'; DROP TABLE plays;--")
    assert hostile.startswith("Invalid season_type")


def test_red_zone_result_matches_handwritten_bound_query():
    from database import query_to_dict

    payload = json.loads(_tool()(season=2022, offense="PHI", red_zone=True))
    expected = query_to_dict(
        """
        SELECT COUNT(*) AS plays, ROUND(AVG(success), 3) AS success_rate
        FROM plays
        WHERE season = ? AND season_type = ? AND posteam = ?
          AND yardline_100 <= ?
        """,
        [2022, "REG", "PHI", 20],
    )[0]

    assert payload["rows"][0]["plays"] == expected["plays"] == 276
    assert payload["rows"][0]["success_rate"] == expected["success_rate"] == 0.562


def test_red_zone_population_differs_from_shaped_team_split_by_design():
    from database import query_to_dict

    row = json.loads(_tool()(season=2022, offense="PHI", red_zone=True))["rows"][0]
    split = query_to_dict(
        """
        SELECT plays, success_pct
        FROM team_splits
        WHERE team = ? AND season = ? AND side = 'offense'
          AND split_dim = 'field_zone' AND split_value = 'red_zone'
        """,
        ["PHI", 2022],
    )[0]

    # query_plays with no play filter includes all PBP event types. The shaped
    # split keeps pass/run scrimmage plays and excludes kneels, spikes, and 2PTs.
    assert (row["plays"], row["success_rate"]) == (276, 0.562)
    assert (split["plays"], split["success_pct"]) == (187, 44.9)


def test_grouped_rows_are_ordered_and_capped():
    payload = json.loads(_tool()(season=2023, group_by="offense"))
    teams = [row["offense"] for row in payload["rows"]]

    assert len(teams) == 25
    assert teams == sorted(teams)
    assert teams[0] == "ARI"
    assert teams[-1] == "NYJ"


def test_small_sample_note_and_ydstogo_refresh_message():
    small = json.loads(_tool()(
        season=2022, play="pass", passer_id="00-0032764"
    ))
    assert small["rows"][0]["plays"] == 2
    assert small["note"] == "small sample — caveat rates"

    unavailable = _tool()(season=2023, ydstogo_max=3)
    assert unavailable == (
        "not ingested yet — down-and-distance filters arrive after the next data refresh."
    )
