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


def _insert_ol_play(conn, game_id, posteam, *, rush=False, sack=0, qb_hit=0, yards=5.0):
    conn.execute(
        """INSERT INTO plays (
            play_id, game_id, season, season_type, week, posteam, defteam,
            pass_attempt, rush_attempt, sack, qb_kneel, qb_spike, yards_gained
        ) VALUES (nextval('ol_play_seq'), ?, 1998, 'REG', 1, ?, 'OPP', ?, ?, ?, 0, 0, ?)""",
        [game_id, posteam, 0 if (rush or sack) else 1, 1 if rush else 0, sack, yards],
    )


def test_ol_unit_grades_builder_and_endpoint(client, seeded_conn):
    import ol_grades_builder

    # Isolated 1998 game so session-scoped 2024 seed data is untouched.
    game_id = "1998_01_KC_DEN"
    seeded_conn.execute("CREATE SEQUENCE IF NOT EXISTS ol_play_seq START 900000")
    seeded_conn.execute(
        """INSERT INTO schedules (game_id, season, game_type, week, away_team, home_team,
                                  away_score, home_score)
           VALUES (?, 1998, 'REG', 1, 'KC', 'DEN', 20, 17)""",
        [game_id],
    )
    # DEN: clean pocket, no stuffs -> raw 0. KC: 4 sacks + 3 stuffs -> clearly worse.
    for _ in range(10):
        _insert_ol_play(seeded_conn, game_id, "DEN")
    for _ in range(6):
        _insert_ol_play(seeded_conn, game_id, "DEN", rush=True, yards=4.0)
    for _ in range(8):
        _insert_ol_play(seeded_conn, game_id, "KC")
    for _ in range(4):
        _insert_ol_play(seeded_conn, game_id, "KC", sack=1)
    for _ in range(3):
        _insert_ol_play(seeded_conn, game_id, "KC", rush=True, yards=4.0)
    for _ in range(3):
        _insert_ol_play(seeded_conn, game_id, "KC", rush=True, yards=-1.0)

    ol_grades_builder.materialize()
    rows = {
        r[0]: r
        for r in seeded_conn.execute(
            """SELECT team, grade, raw_score, dropbacks, sacks_allowed, rushes, stuffed_rushes
               FROM team_game_ol_grades WHERE game_id = ?""",
            [game_id],
        ).fetchall()
    }
    den, kc = rows["DEN"], rows["KC"]
    assert den[3] == 10 and den[4] == 0 and den[5] == 6 and den[6] == 0
    assert kc[3] == 12 and kc[4] == 4 and kc[5] == 6 and kc[6] == 3
    assert den[2] == 0.0
    assert kc[2] == -(4 / 12 + 3 / 6)
    assert den[1] is not None and kc[1] is not None
    assert den[1] > kc[1]

    # Endpoint surfaces the same value the table holds (None-safe equality).
    lineup = client.get("/api/games/2024_01_DEN_KC/lineup").json()
    for team in lineup["teams"]:
        expected = seeded_conn.execute(
            "SELECT grade FROM team_game_ol_grades WHERE game_id = '2024_01_DEN_KC' AND team = ?",
            [team["team"]],
        ).fetchone()
        assert team["ol_grade"] == (expected[0] if expected else None)
        assert "offense_avg" in team and "defense_avg" in team
