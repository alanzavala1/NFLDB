def test_game_lineup_endpoint_returns_snap_starters_and_scoring(client):
    r = client.get("/api/games/2024_01_DEN_KC/lineup")
    assert r.status_code == 200
    data = r.json()

    assert data["game_id"] == "2024_01_DEN_KC"
    assert data["join_match_rate"] == 1.0
    assert any(s["kind"] == "TD" and s["player_id"] == "00-KC-OFF3" for s in data["scoring"])
    assert any(s["kind"] == "FG" and s["player_id"] == "00-KC-K1" for s in data["scoring"])
    defensive_td = next(s for s in data["scoring"] if s["kind"] == "TD" and s["player_id"] == "00-KC-DE1")
    assert defensive_td["team"] == "KC"
    assert defensive_td["player_name"] == "Edge Dude"

    kc = next(t for t in data["teams"] if t["team"] == "KC")
    assert len(kc["offense"]) == 11
    assert len(kc["defense"]) == 11
    assert kc["offense_personnel"] == "21 personnel"
    assert kc["defense_personnel"] == "Nickel"
    assert any(p["player_id"] == "00-KC-QB1" and p["rating"] is not None for p in kc["offense"])
    assert any(p["player_id"] == "00-KC-DE1" and p["rating"] is not None for p in kc["defense"])


def test_game_player_chart_endpoint_returns_role_stats_and_events(client):
    r = client.get("/api/games/2024_01_DEN_KC/players/00-KC-OFF3/chart")
    assert r.status_code == 200
    data = r.json()

    assert data["player_id"] == "00-KC-OFF3"
    assert data["role"] == "receiver"
    assert data["snap_pct"] == 1.0
    assert data["events"]
    assert data["events"][0]["role"] == "receiver"
    assert data["events"][0]["outcome"] == "TD"


def test_lineup_and_chart_ratings_match_materialized_row(client, seeded_conn):
    import game_ratings_builder

    game_ratings_builder.materialize()
    expected = seeded_conn.execute(
        """
        SELECT rating, def_events_score
        FROM player_game_ratings
        WHERE game_id = '2024_01_DEN_KC' AND player_id = '00-KC-DE1'
        """
    ).fetchone()
    expected_rating, expected_def_events = expected

    lineup = client.get("/api/games/2024_01_DEN_KC/lineup").json()
    edge = next(
        p
        for team in lineup["teams"]
        for p in team["defense"] + team["rotation"]
        if p["player_id"] == "00-KC-DE1"
    )
    chart = client.get("/api/games/2024_01_DEN_KC/players/00-KC-DE1/chart").json()

    table_row = seeded_conn.execute(
        """
        SELECT rating, def_events_score
        FROM player_game_ratings
        WHERE game_id = '2024_01_DEN_KC' AND player_id = '00-KC-DE1'
        """
    ).fetchone()

    assert edge["rating"] == expected_rating
    assert chart["rating"] == expected_rating
    assert table_row[0] == expected_rating
    assert round(expected_def_events, 1) == 15.4
    assert chart["role"] == "defender"
    assert chart["stats"]["sacks"] == 3
    assert chart["stats"]["tackles"] == 6
