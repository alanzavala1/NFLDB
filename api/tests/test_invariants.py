"""Data-quality invariant tests.

These are the tests that should never fail unless the SQL is wrong. They
encode properties any NFL stats reader would assume hold — and serve as
regression guards for bugs already fixed:

  - "own_score / opp_score were swapped in /standings"      (commit d62afc1)
  - "spread_line sign was inverted in upset detection"      (commit 2308608)

If those bugs are ever reintroduced, these tests will catch them.
"""
import pytest


pytestmark = pytest.mark.invariant


# ── /standings invariants ────────────────────────────────────────────────────

def test_standings_w_plus_l_plus_t_equals_games_played(client):
    """w + l + t must equal the number of completed games for every team."""
    r = client.get("/api/standings?season=2024")
    standings = r.json()

    # Build expected games-played from the seed: each completed game contributes
    # one game to each participating team.
    expected = {
        "BUF": 3,  # weeks 1, 2, 3 all completed
        "MIA": 2,  # weeks 1, 2 completed; week 3 (KC@MIA) unfinished
        "KC":  2,  # weeks 1, 2 completed; week 3 unfinished
        "DEN": 3,  # weeks 1, 2, 3 all completed
    }

    for div in standings:
        for t in div["teams"]:
            assert t["w"] + t["l"] + t["t"] == expected[t["team"]], \
                f"{t['team']}: {t['w']}W-{t['l']}L-{t['t']}T != {expected[t['team']]} games"


def test_standings_home_plus_away_records_sum_to_total(client):
    """home wins + away wins == total wins (and same for L, T)."""
    r = client.get("/api/standings?season=2024")
    standings = r.json()

    def parse_record(rec: str) -> tuple[int, int, int]:
        parts = rec.split("-")
        return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) == 3 else 0)

    for div in standings:
        for t in div["teams"]:
            hw, hl, ht = parse_record(t["home"])
            aw, al, at = parse_record(t["away"])
            assert hw + aw == t["w"], f"{t['team']}: home_w + away_w mismatch"
            assert hl + al == t["l"], f"{t['team']}: home_l + away_l mismatch"
            assert ht + at == t["t"], f"{t['team']}: home_t + away_t mismatch"


def test_standings_pf_pa_balance_across_league(client):
    """Total points-for across all teams == total points-against across all teams.

    Every completed game contributes its away_score to one team's PF and the
    other team's PA, and vice versa. Sums must balance. This catches the
    own_score/opp_score swap that produced +0 for everyone.
    """
    r = client.get("/api/standings?season=2024")
    standings = r.json()

    total_pf = sum(t["pf"] for div in standings for t in div["teams"])
    total_pa = sum(t["pa"] for div in standings for t in div["teams"])

    assert total_pf == total_pa, \
        f"PF sum {total_pf} != PA sum {total_pa} (likely own/opp score swap)"


def test_standings_pf_not_universally_zero(client):
    """Catches the literal bug we shipped: pf was 0 for every team."""
    r = client.get("/api/standings?season=2024")
    standings = r.json()
    nonzero_pf = [t["pf"] for div in standings for t in div["teams"] if t["pf"] > 0]
    assert nonzero_pf, "every team has 0 points for — own/opp score bug regression"


def test_standings_division_record_consistent(client):
    """A team's div wins cannot exceed its total wins."""
    r = client.get("/api/standings?season=2024")
    standings = r.json()

    def parse(rec: str) -> tuple[int, int, int]:
        parts = rec.split("-")
        return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) == 3 else 0)

    for div in standings:
        for t in div["teams"]:
            dw, dl, dt = parse(t["div"])
            assert dw <= t["w"], f"{t['team']}: div wins > total wins"
            assert dl <= t["l"], f"{t['team']}: div losses > total losses"
            assert dt <= t["t"], f"{t['team']}: div ties > total ties"


def test_standings_division_first_team_is_leader(client):
    """Teams within a division are sorted by pct, then point differential."""
    r = client.get("/api/standings?season=2024")
    standings = r.json()
    for div in standings:
        if len(div["teams"]) < 2:
            continue
        # Each team's pct should be >= the next team's pct
        pcts = [t["pct"] for t in div["teams"]]
        assert pcts == sorted(pcts, reverse=True), \
            f"{div['division']} not sorted by pct: {pcts}"


# ── spread_line convention invariants ────────────────────────────────────────

def test_spread_line_convention_is_positive_home_favored(client):
    """nflfastR convention: spread_line > 0 means the home team is favored.

    Our seed week 1 has BUF@MIA with spread_line=-3.5 (away BUF favored)
    and DEN@KC with spread_line=+10.0 (home KC favored). Both winners are
    on the spread:

      - Week 1 BUF@MIA: BUF favored (-3.5), but MIA won → home-underdog upset
      - Week 1 DEN@KC:  KC favored (+10),  KC won by 28 → favorite wins big

    If we ever flip the spread sign convention, the upset detection on the
    home dashboard will mislabel games (the original bug: "BUF +15.5 upset
    over Saints" when BUF was the favorite that won).
    """
    r = client.get("/api/games?week=1&season=2024")
    games = {f"{g['away_team']}@{g['home_team']}": g for g in r.json()}

    buf_mia = games["BUF@MIA"]
    den_kc  = games["DEN@KC"]

    # The seed encodes the convention we want — these are the canonical values.
    assert buf_mia["spread_line"] == -3.5, "BUF should be away favored"
    assert den_kc["spread_line"]  == 10.0, "KC should be home favored"

    # Upset definition: home underdog wins, OR away underdog wins, by >3 over the spread.
    # Week 1 BUF@MIA: spread -3.5 (BUF favored by 3.5). MIA won by 7. MIA was 3.5-point dog
    # and won by 7 -> 10.5-point cover, clear upset. This is what the home page should label.
    assert (buf_mia["home_score"] > buf_mia["away_score"]) and (buf_mia["spread_line"] < 0), \
        "Home-underdog upset signature: home wins AND spread < 0"


# ── /leaders sanity invariants ───────────────────────────────────────────────

def test_leaders_no_negative_passing_yards(client):
    r = client.get("/api/leaders?season=2024")
    for row in r.json():
        assert (row.get("pass_yards") or 0) >= 0, \
            f"{row['player_name']} has negative pass_yards"


def test_leaders_games_played_at_least_one(client):
    r = client.get("/api/leaders?season=2024")
    for row in r.json():
        assert row["games_played"] >= 1


def test_leaders_qb_completion_rate_under_100pct(client):
    r = client.get("/api/leaders?season=2024")
    for row in r.json():
        att = row.get("attempts") or 0
        cmp = row.get("completions") or 0
        if att > 0:
            assert cmp <= att, f"{row['player_name']} has more completions than attempts"
