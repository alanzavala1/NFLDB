"""Pregame-record behavior with supplied data and no database access."""
from services.schedule_records import attach_records


def _game(week, away, home, a_sc, h_sc):
    return {"week": week, "away_team": away, "home_team": home,
            "away_score": a_sc, "home_score": h_sc}


def test_attach_records_empty():
    assert attach_records([]) == []


def test_attach_records_first_week_all_zero():
    games = [_game(1, "BUF", "MIA", 17, 24)]
    attach_records(games)
    # Before week 1 every team is 0-0; T omitted for 0
    assert games[0]["away_record"] == "0-0"
    assert games[0]["home_record"] == "0-0"


def test_attach_records_walks_weeks_in_order():
    games = [
        _game(1, "BUF", "MIA", 17, 24),   # MIA wins
        _game(2, "BUF", "MIA", 30, 14),   # BUF wins; entering, BUF 0-1 MIA 1-0
    ]
    attach_records(games)
    assert games[1]["away_record"] == "0-1"
    assert games[1]["home_record"] == "1-0"


def test_attach_records_counts_ties():
    games = [
        _game(1, "BUF", "MIA", 21, 21),   # tie
        _game(2, "BUF", "KC",  20, 10),   # entering: BUF 0-0-1
    ]
    attach_records(games)
    assert games[1]["away_record"] == "0-0-1"


def test_attach_records_handles_unfinished_games():
    games = [
        _game(1, "BUF", "MIA", 17, 24),
        _game(2, "BUF", "MIA", None, None),   # unfinished must not change records
        _game(3, "BUF", "MIA", 14, 7),
    ]
    attach_records(games)
    # Entering week 3, only week 1 has counted: BUF 0-1, MIA 1-0
    assert games[2]["away_record"] == "0-1"
    assert games[2]["home_record"] == "1-0"


def test_unsorted_input_keeps_list_and_row_identity_and_skips_partial_scores():
    third = _game(3, "BUF", "MIA", None, None)
    first = _game(1, "BUF", "MIA", 7, 0)
    partial = _game(2, "BUF", "KC", 14, None)
    games = [third, first, partial]
    returned = attach_records(games)
    assert returned is games
    assert returned[0] is third and returned[1] is first and returned[2] is partial
    assert (third["away_record"], third["home_record"]) == ("1-0", "0-1")
    assert (partial["away_record"], partial["home_record"]) == ("1-0", "0-0")
    assert (first["away_record"], first["home_record"]) == ("0-0", "0-0")


def test_same_week_rows_use_records_before_any_results_from_that_week():
    games = [
        _game(2, "BUF", "KC", None, None),
        _game(1, "BUF", "MIA", 7, 0),
        _game(1, "BUF", "DEN", 14, 0),
    ]
    attach_records(games)
    assert games[1]["away_record"] == games[2]["away_record"] == "0-0"
    assert games[0]["away_record"] == "2-0"
