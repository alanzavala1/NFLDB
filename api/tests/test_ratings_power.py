import pytest


def test_player_game_ratings_builder_math(client, seeded_conn):
    import game_ratings_builder

    assert game_ratings_builder.materialize() > 0

    rows = {
        (row[0], row[1]): row
        for row in seeded_conn.execute(
            """
            SELECT player_id, game_id, position_group, rating, raw_score,
                   plays_counted, def_events_score
            FROM player_game_ratings
            """
        ).fetchall()
    }

    mahomes = rows[("00-KC-QB1", "2024_01_DEN_KC")]
    nix = rows[("00-DEN-QB1", "2024_01_DEN_KC")]
    assert mahomes[4] > nix[4]
    assert mahomes[3] > nix[3]
    assert mahomes[5] == 12

    diggs = rows[("00-BUF-WR1", "2024_01_BUF_MIA")]
    assert diggs[2] == "WR"
    assert diggs[3] is None
    assert diggs[5] == 2

    edge = rows[("00-KC-DE1", "2024_01_DEN_KC")]
    assert edge[2] == "DEF"
    assert edge[3] is not None
    assert edge[6] == pytest.approx(15.4)

    quiet = rows[("00-KC-S1", "2024_01_DEN_KC")]
    assert quiet[2] == "DEF"
    assert quiet[3] is None
    assert quiet[6] == pytest.approx(0.0)


def test_team_power_rankings_builder_rank_and_movement(client, seeded_conn):
    import power_rankings_builder

    assert power_rankings_builder.materialize(2024) == 12

    week1 = {
        row[0]: row[1]
        for row in seeded_conn.execute(
            "SELECT team, rank FROM team_power_rankings WHERE season = 2024 AND week = 1"
        ).fetchall()
    }
    week2 = {
        row[0]: (row[1], row[2])
        for row in seeded_conn.execute(
            "SELECT team, rank, movement FROM team_power_rankings WHERE season = 2024 AND week = 2"
        ).fetchall()
    }

    assert sorted(week1.values()) == [1, 2, 3, 4]
    assert week2["BUF"][1] == week1["BUF"] - week2["BUF"][0]


def test_game_ratings_endpoint_returns_rows(client):
    r = client.get("/api/games/2024_01_DEN_KC/ratings")
    assert r.status_code == 200
    rows = r.json()
    assert rows
    assert rows[0]["rating"] is not None
    assert any(row["player_id"] == "00-KC-DE1" and row["position_group"] == "DEF" for row in rows)


def test_power_rankings_endpoint_returns_latest_week(client):
    r = client.get("/api/power-rankings?season=2024")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 4
    assert [row["rank"] for row in rows] == [1, 2, 3, 4]
    buf = next(row for row in rows if row["team"] == "BUF")
    assert buf["record"] == "1-1-1"
    assert "net_epa_play" in buf
