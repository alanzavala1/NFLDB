"""Known target gaps fail closed at serving time; source production survives."""
import duckdb
import pytest

from services.receiving_coverage import mask_target_fields, targets_unavailable
from tests.conftest import _create_schema, _seed


@pytest.mark.parametrize("season, unavailable", [(2002, False), (2003, True), (2004, True), (2008, True), (2009, False), (2024, False)])
def test_policy_boundaries_and_positive_legacy_counts(season, unavailable):
    raw = {"targets": 52, "receptions": 52, "rec_yards": -3, "rec_tds": 1}
    result = mask_target_fields(raw, season)
    assert result["targets"] == (None if unavailable else 52)
    assert {k: v for k, v in result.items() if k != "targets"} == {k: v for k, v in raw.items() if k != "targets"}
    assert raw["targets"] == 52  # Stored/cached input never mutated.
    assert targets_unavailable([2024, season]) == unavailable


@pytest.fixture
def historical_db(client, monkeypatch):
    import database
    import game_ratings_builder
    with duckdb.connect(":memory:") as conn:
        _create_schema(conn)
        _seed(conn)
        for table in ("schedules", "rosters", "player_game_stats", "plays"):
            conn.execute(f"UPDATE {table} SET season = 2004")
        # A plausible legacy target count must also be withheld.
        conn.execute("UPDATE player_game_stats SET targets = 52, receptions = 4, rec_yards = -3, rec_tds = 1 WHERE player_id = '00-BUF-WR1'")
        monkeypatch.setattr(database, "_conn", conn)
        game_ratings_builder.ensure_table(conn)
        monkeypatch.setattr(game_ratings_builder, "read_or_materialize", lambda _: [])
        yield conn


def test_historical_http_views_preserve_production_and_withhold_targets(client, historical_db):
    def get(path):
        response = client.get(path)
        assert response.status_code == 200, response.text
        return response.json()

    leaders = get("/api/leaders?season=2004")
    receiver = next(p for p in leaders if p["player_id"] == "00-BUF-WR1")
    assert receiver["targets"] is None
    assert receiver["receptions"] > 0 and receiver["rec_yards"] < 0 and receiver["rec_tds"] > 0

    team = get("/api/teams/BUF?season=2004")
    assert team["leaders"] and all(p["targets"] is None for p in team["leaders"])
    detail = get("/api/games/2024_01_BUF_MIA")
    assert detail["away"] and all(p["targets"] is None for p in detail["away"] + detail["home"])
    profile = get("/api/players/00-BUF-WR1")
    assert profile["season_totals"]["targets"] is None
    assert all(g["targets"] is None for g in profile["games"])
    assert profile["season_totals"]["receptions"] == receiver["receptions"]
    for families, keys in [(profile["adv_stats"], ("target_share", "air_yards_share")), (profile["situational"], ("rz_targets", "third_targets"))]:
        assert all(row.get(key) is None for row in families.values() for key in keys)
    chart = get("/api/games/2024_01_BUF_MIA/players/00-BUF-WR1/chart")
    assert chart["stats"]["targets"] is None
    assert chart["stats"]["rec_yards"] == -3
    assert historical_db.execute("SELECT targets FROM player_game_stats WHERE player_id = '00-BUF-WR1' LIMIT 1").fetchone()[0] == 52


def test_mixed_career_profile_never_returns_a_partial_target_total(client, historical_db):
    historical_db.execute("UPDATE schedules SET season = 2009 WHERE game_id = '2024_01_BUF_MIA'")
    historical_db.execute("UPDATE player_game_stats SET season = 2009 WHERE game_id = '2024_01_BUF_MIA'")
    response = client.get("/api/players/00-BUF-WR1")
    assert response.status_code == 200
    profile = response.json()
    assert {g["season"] for g in profile["games"]} == {2004, 2009}
    assert any(g["targets"] == 52 for g in profile["games"])
    assert profile["season_totals"]["targets"] is None
    assert profile["season_totals"]["receptions"] == sum(g["receptions"] for g in profile["games"])


def test_receiving_splits_mask_target_counts_and_rates_without_touching_other_categories(client, monkeypatch):
    import routers.players
    rows = [{"season": s, "category": category, "split_dim": "down", "split_value": "1", "sort_order": 1,
             "att": 52, "cmp": 4, "yards": -3, "td": 1, "interceptions": 0, "air_yards": 10,
             "yac": 2, "first_downs": 1, "epa": 1.5, "success_pct": 100, "cpoe": None}
            for s, category in [(2004, "receiving"), (2009, "receiving"), (2004, "passing"), (2004, "rushing")]]
    monkeypatch.setattr(routers.players.splits_builder, "read_or_materialize", lambda _: rows)
    response = client.get("/api/players/test-player/splits")
    assert response.status_code == 200
    masked, *unchanged = response.json()
    assert masked["att"] is None and masked["epa"] is None and masked["success_pct"] is None
    assert masked["cmp"] == 4 and masked["yards"] == -3 and masked["td"] == 1
    assert unchanged == rows[1:]
    assert rows[0]["att"] == 52


def test_assistant_compact_career_line_does_not_sum_only_known_targets():
    from llm import _season_stat_line
    line = _season_stat_line([{"targets": None, "receptions": 4}, {"targets": 20, "receptions": 10}])
    assert "targets" not in line
    assert line["receptions"] == 14


def test_comparable_display_withholds_targets_for_career_ranges_touching_the_gap(client, monkeypatch):
    import routers.players
    row = {"player_id": "old", "player_name": "Historical receiver", "position": "WR",
           "team": "BUF", "headshot_url": None, "similarity": 80, "games": 50,
           "first_season": 2002, "last_season": 2009, "pass_yards": 0, "pass_tds": 0,
           "rush_yards": 0, "rush_tds": 0, "carries": 0, "rec_yards": 500, "rec_tds": 4,
           "targets": 90, "att": 0, "cmp": 0, "ints": 0}
    modern = dict(row, player_id="modern", first_season=2009, last_season=2010, targets=0)
    monkeypatch.setattr(routers.players.comparables_builder, "read_or_materialize", lambda *_: [row, modern])
    response = client.get("/api/players/test-player/comparables")
    assert response.status_code == 200
    old, new = response.json()
    assert old["targets"] is None and old["rec_yards"] == 500
    assert new["targets"] == 0
    assert row["targets"] == 90


def test_postseason_uses_the_same_conservative_season_policy(client, historical_db):
    historical_db.execute("UPDATE schedules SET game_type = 'POST' WHERE game_id = '2024_01_BUF_MIA'")
    response = client.get("/api/teams/BUF?season=2004")
    assert response.status_code == 200
    rows = response.json()["playoff_leaders"]
    assert rows and all(row["targets"] is None for row in rows)
    receiver = next(row for row in rows if row["player_id"] == "00-BUF-WR1")
    assert receiver["receptions"] == 4 and receiver["rec_yards"] == -3
