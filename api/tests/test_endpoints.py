"""Integration tests: every endpoint returns the right shape on seeded data."""


def test_schedule_returns_grouped_by_week(client):
    r = client.get("/schedule?season=2024")
    assert r.status_code == 200
    weeks = r.json()
    # Seeded weeks 1, 2, 3
    assert [w["week"] for w in weeks] == [1, 2, 3]
    # Week 1 has two games (BUF@MIA, DEN@KC)
    assert len(weeks[0]["games"]) == 2


def test_schedule_attaches_pre_game_records(client):
    r = client.get("/schedule?season=2024")
    weeks = r.json()
    # First game of season: everyone is 0-0
    first = weeks[0]["games"][0]
    assert first["away_record"] == "0-0"
    assert first["home_record"] == "0-0"


def test_games_for_week(client):
    r = client.get("/games?week=1&season=2024")
    assert r.status_code == 200
    games = r.json()
    assert len(games) == 2


def test_games_unknown_week_404s(client):
    r = client.get("/games?week=10&season=2024")
    assert r.status_code == 404


def test_team_roster_returns_team_players(client):
    r = client.get("/teams/BUF/roster?season=2024")
    assert r.status_code == 200
    roster = r.json()
    # Seed has two BUF players (QB + WR)
    names = sorted(p["player_name"] for p in roster)
    assert names == ["Josh Allen", "Stefon Diggs"]
    # Pydantic response model enforces these fields exist
    for p in roster:
        assert "player_id" in p and "position" in p


def test_team_roster_unknown_team_404s(client):
    r = client.get("/teams/ZZZ/roster?season=2024")
    assert r.status_code == 404


def test_team_summary(client):
    r = client.get("/teams/BUF?season=2024")
    assert r.status_code == 200
    body = r.json()
    assert body["team"] == "BUF"
    assert body["season"] == 2024
    # BUF played in 3 games (W vs DEN, L vs MIA, T vs KC)
    assert len(body["games"]) == 3


def test_leaders_returns_qbs_and_wrs(client):
    r = client.get("/leaders?season=2024")
    assert r.status_code == 200
    rows = r.json()
    # All 6 seeded players appear (they all have stats)
    assert len(rows) == 6
    qbs = [r for r in rows if r["position"] == "QB"]
    assert len(qbs) == 4


def test_leaders_sums_across_games(client):
    r = client.get("/leaders?season=2024")
    rows = r.json()
    allen = next(r for r in rows if r["player_name"] == "Josh Allen")
    # Josh Allen seeded as 240 + 310 + 330 = 880 pass yards across 3 games
    assert allen["pass_yards"] == 880
    assert allen["games_played"] == 3


def test_search_finds_player_and_team(client):
    r = client.get("/search?q=mahomes")
    assert r.status_code == 200
    results = r.json()
    types = {x["type"] for x in results}
    assert "player" in types

    r2 = client.get("/search?q=buf")
    results = r2.json()
    types2 = {x["type"] for x in results}
    assert "team" in types2
