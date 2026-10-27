"""Source-checked native passing replacement within the offline split transaction."""
import json

from pipeline.passing_down import COUNTS
from pipeline.receiving_core_inputs import _same_rows
from pipeline.snapshots import CandidateError


PREPARATION_TABLE = "passing_build_preparation"
_DDL = """CREATE TABLE IF NOT EXISTS passing_build_preparation (
    season INTEGER PRIMARY KEY, record JSON NOT NULL
);"""


def has_official_passing(conn):
    return PREPARATION_TABLE in {row[0] for row in conn.execute("SHOW TABLES").fetchall()}


def prepare_passing(conn, season, core_inputs, passing_inputs):
    """Replay exports only after proving the candidate uses those same sources."""
    plays, weekly = core_inputs.feeds([season])
    actual = conn.execute("SELECT * FROM plays WHERE season=?", [season]).df()
    if set(plays.data) - set(actual):
        raise CandidateError(f"passing[{season}]: candidate missing captured play fields")
    _same_rows(actual[list(plays.data)].copy(), plays.data.copy(), ["game_id", "play_id"], season)
    fields = ["player_id", "season", "season_type", "week", "game_id", *COUNTS,
              "passing_first_downs", "passing_epa"]
    expected = weekly.data.loc[weekly.data.season_type.eq("REG") & weekly.data.player_id.notna()]
    actual = conn.execute("""SELECT * FROM weekly_player_stats WHERE season=? AND season_type='REG'
                             AND player_id IS NOT NULL""", [season]).df()
    if set(fields) - set(actual) or set(fields) - set(expected):
        raise CandidateError(f"passing[{season}]: candidate weekly passing schema is incomplete")
    _same_rows(actual[fields].copy(), expected[fields].copy(),
               ["player_id", "season", "season_type", "week"], season)
    prepared = passing_inputs.load(season, core_inputs)
    prepared.report["passing_revision"] = passing_inputs.revision()
    return prepared


def store_passing(conn, season, prepared):
    """Caller owns season replacement, database write lock and transaction."""
    conn.execute(_DDL)
    for frame in prepared.rows.values():
        conn.register("official_passing_rows", frame)
        try:
            conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM official_passing_rows")
        finally:
            conn.unregister("official_passing_rows")
    conn.execute(f"DELETE FROM {PREPARATION_TABLE} WHERE season=?", [season])
    conn.execute(f"INSERT INTO {PREPARATION_TABLE} VALUES (?,?)",
                 [season, json.dumps(prepared.report, allow_nan=False)])
