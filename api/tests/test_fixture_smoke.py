"""Smoke tests: the fixture builds and the client routes work."""


def test_seeded_conn_has_schedules(seeded_conn):
    rows = seeded_conn.execute("SELECT COUNT(*) FROM schedules").fetchone()
    assert rows[0] == 6


def test_seeded_conn_has_roster(seeded_conn):
    rows = seeded_conn.execute("SELECT COUNT(*) FROM rosters").fetchone()
    assert rows[0] == 6


def test_client_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_client_seasons_lists_test_season(client):
    r = client.get("/api/seasons")
    assert r.status_code == 200
    seasons = r.json()
    # Test data has season=2024 loaded
    by_year = {s["season"]: s["status"] for s in seasons}
    assert by_year[2024] == "loaded"
