"""Depth-chart endpoints against the new-format (dt-snapshot) vendor table.

The fixture seeds a current snapshot (2024-11-05 → NFL season 2024) and a
stale one the day before; only the latest snapshot may ever surface.
"""


def test_player_profile_depth_badge(client):
    r = client.get("/api/players/00-KC-QB1")
    assert r.status_code == 200
    depth = r.json()["depth"]
    assert depth is not None
    # season derived from the snapshot date (Nov 2024 → season 2024)
    assert depth["season"] == 2024
    assert depth["week"] is None
    assert depth["team"] == "KC"
    # Mahomes is both QB1 and the holder; the offense slot must win over ST
    assert depth["depth_position"] == "QB"
    assert depth["formation"] == "Offense"
    # rank 1 from the LATEST snapshot (the stale one says rank 2)
    assert depth["depth_team"] == "1"


def test_player_without_depth_entry(client):
    r = client.get("/api/players/00-BUF-QB1")
    assert r.status_code == 200
    assert r.json()["depth"] is None


def test_team_depth_chart_current(client):
    r = client.get("/api/teams/KC/depth-chart?season=2024")
    assert r.status_code == 200
    rows = r.json()
    # 5 rows in the latest snapshot (stale-snapshot row excluded)
    assert len(rows) == 5
    # ordered offense → defense → special teams
    formations = [row["formation"] for row in rows]
    assert formations == sorted(formations, key=["Offense", "Defense", "Special Teams"].index)
    # starter filter the frontend applies still works
    starters = [row for row in rows if row["depth_team"] == "1"]
    assert {(row["formation"], row["depth_position"]) for row in starters} == {
        ("Offense", "QB"), ("Defense", "LDE"), ("Special Teams", "PK"), ("Special Teams", "H"),
    }


def test_team_depth_chart_week_param_ignored(client):
    with_week = client.get("/api/teams/KC/depth-chart?season=2024&week=9").json()
    without = client.get("/api/teams/KC/depth-chart?season=2024").json()
    assert with_week == without


def test_team_depth_chart_past_season_empty(client):
    # No historical snapshots exist — a past season must NOT get today's chart
    r = client.get("/api/teams/KC/depth-chart?season=2023")
    assert r.status_code == 200
    assert r.json() == []
