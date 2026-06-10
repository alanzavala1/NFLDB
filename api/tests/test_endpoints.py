"""Integration tests: every endpoint returns the right shape on seeded data."""


def test_schedule_returns_grouped_by_week(client):
    r = client.get("/api/schedule?season=2024")
    assert r.status_code == 200
    weeks = r.json()
    # Seeded weeks 1, 2, 3
    assert [w["week"] for w in weeks] == [1, 2, 3]
    # Week 1 has two games (BUF@MIA, DEN@KC)
    assert len(weeks[0]["games"]) == 2


def test_schedule_attaches_pre_game_records(client):
    r = client.get("/api/schedule?season=2024")
    weeks = r.json()
    # First game of season: everyone is 0-0
    first = weeks[0]["games"][0]
    assert first["away_record"] == "0-0"
    assert first["home_record"] == "0-0"


def test_games_for_week(client):
    r = client.get("/api/games?week=1&season=2024")
    assert r.status_code == 200
    games = r.json()
    assert len(games) == 2


def test_games_unknown_week_404s(client):
    r = client.get("/api/games?week=10&season=2024")
    assert r.status_code == 404


def test_team_roster_returns_team_players(client):
    r = client.get("/api/teams/BUF/roster?season=2024")
    assert r.status_code == 200
    roster = r.json()
    # Seed has two BUF players (QB + WR)
    names = sorted(p["player_name"] for p in roster)
    assert names == ["Josh Allen", "Stefon Diggs"]
    # Pydantic response model enforces these fields exist
    for p in roster:
        assert "player_id" in p and "position" in p


def test_team_roster_unknown_team_404s(client):
    r = client.get("/api/teams/ZZZ/roster?season=2024")
    assert r.status_code == 404


def test_team_summary(client):
    r = client.get("/api/teams/BUF?season=2024")
    assert r.status_code == 200
    body = r.json()
    assert body["team"] == "BUF"
    assert body["season"] == 2024
    # BUF played in 3 games (W vs DEN, L vs MIA, T vs KC)
    assert len(body["games"]) == 3


def test_leaders_returns_qbs_and_wrs(client):
    r = client.get("/api/leaders?season=2024")
    assert r.status_code == 200
    rows = r.json()
    # All 6 seeded players appear (they all have stats)
    assert len(rows) == 6
    qbs = [r for r in rows if r["position"] == "QB"]
    assert len(qbs) == 4


def test_leaders_sums_across_games(client):
    r = client.get("/api/leaders?season=2024")
    rows = r.json()
    allen = next(r for r in rows if r["player_name"] == "Josh Allen")
    # Josh Allen seeded as 240 + 310 + 330 = 880 pass yards across 3 games
    assert allen["pass_yards"] == 880
    assert allen["games_played"] == 3


def test_team_analytics_endpoint(client):
    """Endpoint returns the typed shape even when the underlying plays table
    is absent — the materialized table is created (empty) and read."""
    r = client.get("/api/team-analytics?season=2024")
    assert r.status_code == 200
    body = r.json()
    assert body["season"] == 2024
    assert isinstance(body["league"], list)


def test_team_analytics_creates_materialized_table(client, seeded_conn):
    """First call lazily creates team_season_analytics.

    This is the key behavior of read_or_materialize: the table doesn't
    need to exist ahead of time. If it doesn't, we materialize on demand.
    """
    client.get("/api/team-analytics?season=2024")
    # Table now exists
    tables = {r[0] for r in seeded_conn.execute("SHOW TABLES").fetchall()}
    assert "team_season_analytics" in tables


def test_player_comparables_endpoint_returns_typed_shape(client):
    """The endpoint must return the right shape even when the seeded data
    has no players with >= 16 career games (so the materialized tables are
    empty and the read returns [])."""
    r = client.get("/api/players/00-BUF-QB1/comparables")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_player_comparables_creates_materialized_tables(client, seeded_conn):
    """First call lazily creates player_career_summary + player_comparables."""
    client.get("/api/players/00-BUF-QB1/comparables")
    tables = {r[0] for r in seeded_conn.execute("SHOW TABLES").fetchall()}
    assert "player_career_summary" in tables
    assert "player_comparables"   in tables


def test_player_splits_endpoint_returns_typed_shape(client):
    """The fixture has no `plays` table, so the splits builder can't produce
    rows — the endpoint must still return an empty list (not error), matching
    how every play-derived path degrades on a cold DB."""
    r = client.get("/api/players/00-BUF-QB1/splits")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_team_splits_endpoint_returns_typed_shape(client):
    """No `plays` table in the fixture, so team splits can't materialize — the
    endpoint must still return an empty list, not error."""
    r = client.get("/api/teams/BUF/splits?season=2023")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_search_finds_player_and_team(client):
    r = client.get("/api/search?q=mahomes")
    assert r.status_code == 200
    results = r.json()
    types = {x["type"] for x in results}
    assert "player" in types

    r2 = client.get("/api/search?q=buf")
    results = r2.json()
    types2 = {x["type"] for x in results}
    assert "team" in types2
