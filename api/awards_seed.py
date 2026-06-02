"""Seed data for major NFL awards (MVP, OPOY, DPOY, OROY, DROY, CPOY).

These are voting outcomes — there's no nfl_data_py function for them and
no clean public download. They don't change once awarded, so keeping
them as a versioned seed in code is acceptable. The downstream pipeline
(see `load_awards` in ingest.py) turns this dict into a real DuckDB
table with gsis_id joins so the API can serve it like any other data.

When the upcoming season's awards are announced (~Feb each year), add
the row here and re-run an ingest.

NOTE: the longer-term fix is to scrape this from Pro Football Reference
on each ingest. That's tracked but not done yet. The PR adding it should
delete this file.
"""

PAST_AWARDS: dict[int, list[dict]] = {
    2024: [
        {"award": "MVP",  "player": "Josh Allen",         "team": "BUF", "pos": "QB"},
        {"award": "OPOY", "player": "Saquon Barkley",     "team": "PHI", "pos": "RB"},
        {"award": "DPOY", "player": "Patrick Surtain II", "team": "DEN", "pos": "CB"},
        {"award": "OROY", "player": "Jayden Daniels",     "team": "WAS", "pos": "QB"},
        {"award": "DROY", "player": "Jared Verse",        "team": "LAR", "pos": "EDGE"},
        {"award": "CPOY", "player": "Joe Burrow",         "team": "CIN", "pos": "QB"},
    ],
    2023: [
        {"award": "MVP",  "player": "Lamar Jackson",        "team": "BAL", "pos": "QB"},
        {"award": "OPOY", "player": "Christian McCaffrey",  "team": "SF",  "pos": "RB"},
        {"award": "DPOY", "player": "Myles Garrett",        "team": "CLE", "pos": "DE"},
        {"award": "OROY", "player": "C.J. Stroud",          "team": "HOU", "pos": "QB"},
        {"award": "DROY", "player": "Will Anderson Jr.",    "team": "HOU", "pos": "EDGE"},
        {"award": "CPOY", "player": "Damar Hamlin",         "team": "BUF", "pos": "S"},
    ],
    2022: [
        {"award": "MVP",  "player": "Patrick Mahomes",   "team": "KC",  "pos": "QB"},
        {"award": "OPOY", "player": "Justin Jefferson",  "team": "MIN", "pos": "WR"},
        {"award": "DPOY", "player": "Nick Bosa",         "team": "SF",  "pos": "DE"},
        {"award": "OROY", "player": "Garrett Wilson",    "team": "NYJ", "pos": "WR"},
        {"award": "DROY", "player": "Sauce Gardner",     "team": "NYJ", "pos": "CB"},
        {"award": "CPOY", "player": "Geno Smith",        "team": "SEA", "pos": "QB"},
    ],
    2021: [
        {"award": "MVP",  "player": "Aaron Rodgers", "team": "GB",  "pos": "QB"},
        {"award": "OPOY", "player": "Cooper Kupp",   "team": "LAR", "pos": "WR"},
        {"award": "DPOY", "player": "T.J. Watt",     "team": "PIT", "pos": "LB"},
        {"award": "OROY", "player": "Ja'Marr Chase", "team": "CIN", "pos": "WR"},
        {"award": "DROY", "player": "Micah Parsons", "team": "DAL", "pos": "LB"},
        {"award": "CPOY", "player": "Joe Burrow",    "team": "CIN", "pos": "QB"},
    ],
    2020: [
        {"award": "MVP",  "player": "Aaron Rodgers",  "team": "GB",  "pos": "QB"},
        {"award": "OPOY", "player": "Derrick Henry",  "team": "TEN", "pos": "RB"},
        {"award": "DPOY", "player": "Aaron Donald",   "team": "LAR", "pos": "DT"},
        {"award": "OROY", "player": "Justin Herbert", "team": "LAC", "pos": "QB"},
        {"award": "DROY", "player": "Chase Young",    "team": "WAS", "pos": "DE"},
        {"award": "CPOY", "player": "Alex Smith",     "team": "WAS", "pos": "QB"},
    ],
    2019: [
        {"award": "MVP",  "player": "Lamar Jackson",   "team": "BAL", "pos": "QB"},
        {"award": "OPOY", "player": "Michael Thomas",  "team": "NO",  "pos": "WR"},
        {"award": "DPOY", "player": "Stephon Gilmore", "team": "NE",  "pos": "CB"},
        {"award": "OROY", "player": "Kyler Murray",    "team": "ARI", "pos": "QB"},
        {"award": "DROY", "player": "Nick Bosa",       "team": "SF",  "pos": "DE"},
        {"award": "CPOY", "player": "Ryan Tannehill",  "team": "TEN", "pos": "QB"},
    ],
    2018: [
        {"award": "MVP",  "player": "Patrick Mahomes",   "team": "KC",  "pos": "QB"},
        {"award": "OPOY", "player": "Patrick Mahomes",   "team": "KC",  "pos": "QB"},
        {"award": "DPOY", "player": "Aaron Donald",      "team": "LAR", "pos": "DT"},
        {"award": "OROY", "player": "Saquon Barkley",    "team": "NYG", "pos": "RB"},
        {"award": "DROY", "player": "Darius Leonard",    "team": "IND", "pos": "LB"},
        {"award": "CPOY", "player": "Andrew Luck",       "team": "IND", "pos": "QB"},
    ],
    2017: [
        {"award": "MVP",  "player": "Tom Brady",         "team": "NE",  "pos": "QB"},
        {"award": "OPOY", "player": "Todd Gurley",       "team": "LAR", "pos": "RB"},
        {"award": "DPOY", "player": "Aaron Donald",      "team": "LAR", "pos": "DT"},
        {"award": "OROY", "player": "Alvin Kamara",      "team": "NO",  "pos": "RB"},
        {"award": "DROY", "player": "Marshon Lattimore", "team": "NO",  "pos": "CB"},
        {"award": "CPOY", "player": "Keenan Allen",      "team": "LAC", "pos": "WR"},
    ],
    2016: [
        {"award": "MVP",  "player": "Matt Ryan",    "team": "ATL", "pos": "QB"},
        {"award": "OPOY", "player": "Matt Ryan",    "team": "ATL", "pos": "QB"},
        {"award": "DPOY", "player": "Khalil Mack",  "team": "OAK", "pos": "EDGE"},
        {"award": "OROY", "player": "Dak Prescott", "team": "DAL", "pos": "QB"},
        {"award": "DROY", "player": "Joey Bosa",    "team": "SD",  "pos": "EDGE"},
        {"award": "CPOY", "player": "Jordy Nelson", "team": "GB",  "pos": "WR"},
    ],
    2015: [
        {"award": "MVP",  "player": "Cam Newton",    "team": "CAR", "pos": "QB"},
        {"award": "OPOY", "player": "Cam Newton",    "team": "CAR", "pos": "QB"},
        {"award": "DPOY", "player": "J.J. Watt",     "team": "HOU", "pos": "DE"},
        {"award": "OROY", "player": "Todd Gurley",   "team": "STL", "pos": "RB"},
        {"award": "DROY", "player": "Marcus Peters", "team": "KC",  "pos": "CB"},
        {"award": "CPOY", "player": "Eric Berry",    "team": "KC",  "pos": "S"},
    ],
    2014: [
        {"award": "MVP",  "player": "Aaron Rodgers",  "team": "GB",  "pos": "QB"},
        {"award": "OPOY", "player": "DeMarco Murray", "team": "DAL", "pos": "RB"},
        {"award": "DPOY", "player": "J.J. Watt",      "team": "HOU", "pos": "DE"},
        {"award": "OROY", "player": "Odell Beckham",  "team": "NYG", "pos": "WR"},
        {"award": "DROY", "player": "Aaron Donald",   "team": "STL", "pos": "DT"},
        {"award": "CPOY", "player": "Rob Gronkowski", "team": "NE",  "pos": "TE"},
    ],
    2013: [
        {"award": "MVP",  "player": "Peyton Manning",     "team": "DEN", "pos": "QB"},
        {"award": "OPOY", "player": "Peyton Manning",     "team": "DEN", "pos": "QB"},
        {"award": "DPOY", "player": "Luke Kuechly",       "team": "CAR", "pos": "LB"},
        {"award": "OROY", "player": "Eddie Lacy",         "team": "GB",  "pos": "RB"},
        {"award": "DROY", "player": "Sheldon Richardson", "team": "NYJ", "pos": "DT"},
        {"award": "CPOY", "player": "Philip Rivers",      "team": "SD",  "pos": "QB"},
    ],
    2012: [
        {"award": "MVP",  "player": "Adrian Peterson",    "team": "MIN", "pos": "RB"},
        {"award": "OPOY", "player": "Adrian Peterson",    "team": "MIN", "pos": "RB"},
        {"award": "DPOY", "player": "J.J. Watt",          "team": "HOU", "pos": "DE"},
        {"award": "OROY", "player": "Robert Griffin III", "team": "WAS", "pos": "QB"},
        {"award": "DROY", "player": "Luke Kuechly",       "team": "CAR", "pos": "LB"},
        {"award": "CPOY", "player": "Peyton Manning",     "team": "DEN", "pos": "QB"},
    ],
    2011: [
        {"award": "MVP",  "player": "Aaron Rodgers",    "team": "GB",  "pos": "QB"},
        {"award": "OPOY", "player": "Drew Brees",       "team": "NO",  "pos": "QB"},
        {"award": "DPOY", "player": "Terrell Suggs",    "team": "BAL", "pos": "LB"},
        {"award": "OROY", "player": "Cam Newton",       "team": "CAR", "pos": "QB"},
        {"award": "DROY", "player": "Von Miller",       "team": "DEN", "pos": "LB"},
        {"award": "CPOY", "player": "Matthew Stafford", "team": "DET", "pos": "QB"},
    ],
    2010: [
        {"award": "MVP",  "player": "Tom Brady",      "team": "NE",  "pos": "QB"},
        {"award": "OPOY", "player": "Tom Brady",      "team": "NE",  "pos": "QB"},
        {"award": "DPOY", "player": "Troy Polamalu",  "team": "PIT", "pos": "S"},
        {"award": "OROY", "player": "Sam Bradford",   "team": "STL", "pos": "QB"},
        {"award": "DROY", "player": "Ndamukong Suh",  "team": "DET", "pos": "DT"},
        {"award": "CPOY", "player": "Michael Vick",   "team": "PHI", "pos": "QB"},
    ],
    2009: [
        {"award": "MVP",  "player": "Peyton Manning",   "team": "IND", "pos": "QB"},
        {"award": "OPOY", "player": "Chris Johnson",    "team": "TEN", "pos": "RB"},
        {"award": "DPOY", "player": "Charles Woodson",  "team": "GB",  "pos": "CB"},
        {"award": "OROY", "player": "Percy Harvin",     "team": "MIN", "pos": "WR"},
        {"award": "DROY", "player": "Brian Cushing",    "team": "HOU", "pos": "LB"},
        {"award": "CPOY", "player": "Tom Brady",        "team": "NE",  "pos": "QB"},
    ],
    2008: [
        {"award": "MVP",  "player": "Peyton Manning",  "team": "IND", "pos": "QB"},
        {"award": "OPOY", "player": "Drew Brees",      "team": "NO",  "pos": "QB"},
        {"award": "DPOY", "player": "James Harrison",  "team": "PIT", "pos": "LB"},
        {"award": "OROY", "player": "Matt Ryan",       "team": "ATL", "pos": "QB"},
        {"award": "DROY", "player": "Jerod Mayo",      "team": "NE",  "pos": "LB"},
        {"award": "CPOY", "player": "Chad Pennington", "team": "MIA", "pos": "QB"},
    ],
    2007: [
        {"award": "MVP",  "player": "Tom Brady",        "team": "NE",  "pos": "QB"},
        {"award": "OPOY", "player": "Tom Brady",        "team": "NE",  "pos": "QB"},
        {"award": "DPOY", "player": "Bob Sanders",      "team": "IND", "pos": "S"},
        {"award": "OROY", "player": "Adrian Peterson", "team": "MIN", "pos": "RB"},
        {"award": "DROY", "player": "Patrick Willis",   "team": "SF",  "pos": "LB"},
        {"award": "CPOY", "player": "Greg Ellis",       "team": "DAL", "pos": "DE"},
    ],
    2006: [
        {"award": "MVP",  "player": "LaDainian Tomlinson", "team": "SD",  "pos": "RB"},
        {"award": "OPOY", "player": "LaDainian Tomlinson", "team": "SD",  "pos": "RB"},
        {"award": "DPOY", "player": "Jason Taylor",        "team": "MIA", "pos": "DE"},
        {"award": "OROY", "player": "Vince Young",         "team": "TEN", "pos": "QB"},
        {"award": "DROY", "player": "DeMeco Ryans",        "team": "HOU", "pos": "LB"},
        {"award": "CPOY", "player": "Drew Brees",          "team": "NO",  "pos": "QB"},
    ],
    2005: [
        {"award": "MVP",  "player": "Shaun Alexander",   "team": "SEA", "pos": "RB"},
        {"award": "OPOY", "player": "Shaun Alexander",   "team": "SEA", "pos": "RB"},
        {"award": "DPOY", "player": "Brian Urlacher",    "team": "CHI", "pos": "LB"},
        {"award": "OROY", "player": "Cadillac Williams", "team": "TB",  "pos": "RB"},
        {"award": "DROY", "player": "Shawne Merriman",   "team": "SD",  "pos": "LB"},
        {"award": "CPOY", "player": "Steve Smith",       "team": "CAR", "pos": "WR"},
    ],
    2004: [
        {"award": "MVP",  "player": "Peyton Manning",     "team": "IND", "pos": "QB"},
        {"award": "OPOY", "player": "Peyton Manning",     "team": "IND", "pos": "QB"},
        {"award": "DPOY", "player": "Ed Reed",            "team": "BAL", "pos": "S"},
        {"award": "OROY", "player": "Ben Roethlisberger", "team": "PIT", "pos": "QB"},
        {"award": "DROY", "player": "Jonathan Vilma",     "team": "NYJ", "pos": "LB"},
        {"award": "CPOY", "player": "Drew Brees",         "team": "SD",  "pos": "QB"},
    ],
    2003: [
        # Co-MVPs
        {"award": "MVP",  "player": "Peyton Manning",  "team": "IND", "pos": "QB"},
        {"award": "MVP",  "player": "Steve McNair",    "team": "TEN", "pos": "QB"},
        {"award": "OPOY", "player": "Jamal Lewis",     "team": "BAL", "pos": "RB"},
        {"award": "DPOY", "player": "Ray Lewis",       "team": "BAL", "pos": "LB"},
        {"award": "OROY", "player": "Anquan Boldin",   "team": "ARI", "pos": "WR"},
        {"award": "DROY", "player": "Terence Newman",  "team": "DAL", "pos": "CB"},
        {"award": "CPOY", "player": "Jon Kitna",       "team": "CIN", "pos": "QB"},
    ],
    2002: [
        {"award": "MVP",  "player": "Rich Gannon",    "team": "OAK", "pos": "QB"},
        {"award": "OPOY", "player": "Priest Holmes",  "team": "KC",  "pos": "RB"},
        {"award": "DPOY", "player": "Derrick Brooks", "team": "TB",  "pos": "LB"},
        {"award": "OROY", "player": "Clinton Portis", "team": "DEN", "pos": "RB"},
        {"award": "DROY", "player": "Julius Peppers", "team": "CAR", "pos": "DE"},
        {"award": "CPOY", "player": "Tommy Maddox",   "team": "PIT", "pos": "QB"},
    ],
    2001: [
        {"award": "MVP",  "player": "Kurt Warner",      "team": "STL", "pos": "QB"},
        {"award": "OPOY", "player": "Marshall Faulk",   "team": "STL", "pos": "RB"},
        {"award": "DPOY", "player": "Michael Strahan",  "team": "NYG", "pos": "DE"},
        {"award": "OROY", "player": "Anthony Thomas",   "team": "CHI", "pos": "RB"},
        {"award": "DROY", "player": "Kendrell Bell",    "team": "PIT", "pos": "LB"},
        {"award": "CPOY", "player": "Garrison Hearst",  "team": "SF",  "pos": "RB"},
    ],
    2000: [
        {"award": "MVP",  "player": "Marshall Faulk", "team": "STL", "pos": "RB"},
        {"award": "OPOY", "player": "Marshall Faulk", "team": "STL", "pos": "RB"},
        {"award": "DPOY", "player": "Ray Lewis",      "team": "BAL", "pos": "LB"},
        {"award": "OROY", "player": "Mike Anderson",  "team": "DEN", "pos": "RB"},
        {"award": "DROY", "player": "Brian Urlacher", "team": "CHI", "pos": "LB"},
        {"award": "CPOY", "player": "Joe Johnson",    "team": "NO",  "pos": "DE"},
    ],
    1999: [
        {"award": "MVP",  "player": "Kurt Warner",     "team": "STL", "pos": "QB"},
        {"award": "OPOY", "player": "Marshall Faulk",  "team": "STL", "pos": "RB"},
        {"award": "DPOY", "player": "Warren Sapp",     "team": "TB",  "pos": "DT"},
        {"award": "OROY", "player": "Edgerrin James",  "team": "IND", "pos": "RB"},
        {"award": "DROY", "player": "Jevon Kearse",    "team": "TEN", "pos": "DE"},
        {"award": "CPOY", "player": "Bryant Young",    "team": "SF",  "pos": "DT"},
    ],
}


def all_rows() -> list[dict]:
    """Flatten the per-season dict into individual rows for INSERT."""
    out = []
    for season, awards in PAST_AWARDS.items():
        for a in awards:
            out.append({"season": season, **a})
    return out
