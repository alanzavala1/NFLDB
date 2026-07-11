def test_game_lineup_endpoint_returns_snap_starters_and_scoring(client):
    r = client.get("/api/games/2024_01_DEN_KC/lineup")
    assert r.status_code == 200
    data = r.json()

    assert data["game_id"] == "2024_01_DEN_KC"
    assert data["join_match_rate"] == 1.0
    assert any(s["kind"] == "TD" and s["player_id"] == "00-KC-OFF3" for s in data["scoring"])
    assert any(s["kind"] == "FG" and s["player_id"] == "00-KC-K1" for s in data["scoring"])

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
