"""Official receiving replacement and coverage records for offline candidates.

These records deliberately block publication until API/UI scope handling and
the complete receiving-aware release gate are implemented.
"""
from dataclasses import dataclass
import hashlib
import json

import pandas as pd

from pipeline.receiving_core_inputs import _same_rows
from pipeline.receiving_exports import ReceivingSeason, load_receiving_season
from pipeline.snapshots import CandidateError


PREPARATION_TABLE = "receiving_build_preparation"
REFERENCE_TABLE = "receiving_whole_reference"
TOTALS_TABLE = "receiving_season_totals"
_DDL = """
CREATE TABLE IF NOT EXISTS receiving_build_preparation (
    season INTEGER PRIMARY KEY, record JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS receiving_whole_reference (
    season INTEGER PRIMARY KEY, record JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS receiving_season_totals (
    season INTEGER PRIMARY KEY, record JSON NOT NULL
);
"""


@dataclass
class PreparedReceiving:
    exports: ReceivingSeason
    report: dict


def has_official_receiving(conn) -> bool:
    return PREPARATION_TABLE in {row[0] for row in conn.execute("SHOW TABLES").fetchall()}


def _game_coverage(conn, season: int, plays: pd.DataFrame) -> dict:
    schedules = conn.execute("""SELECT game_id, home_score, away_score FROM schedules
                                WHERE season=? AND game_type='REG' ORDER BY game_id""", [season]).df()
    if schedules.empty or schedules.game_id.isna().any() or schedules.game_id.duplicated().any():
        raise CandidateError(f"receiving[{season}]: missing/duplicate regular-season schedule")
    supplied = set(plays.loc[plays.season_type.eq("REG"), "game_id"])
    scheduled = set(schedules.game_id)
    if supplied - scheduled:
        raise CandidateError(f"receiving[{season}]: supplied games absent from candidate schedule")
    completed = set(schedules.loc[schedules.home_score.notna() & schedules.away_score.notna(), "game_id"])
    missing, unconfirmed = sorted(completed - supplied), sorted(supplied - completed)
    values = schedules.astype(object).where(schedules.notna(), None).to_dict(orient="records")
    return {"status": "partial" if missing or unconfirmed else "complete",
            "scope": "supplied REG games versus candidate's recorded completed REG games",
            "supplied_games": len(supplied), "recorded_completed_games": len(completed),
            "missing_game_ids": missing, "unconfirmed_game_ids": unconfirmed,
            "candidate_schedule_sha256": hashlib.sha256(json.dumps(values, sort_keys=True, allow_nan=False).encode()).hexdigest(),
            "reason": ("Completed games lack supplied plays, or supplied games lack recorded final scores"
                       if missing or unconfirmed else None),
            "count_scope": "observed production on supplied games; not a source freshness certificate"}


def prepare_receiving(conn, season: int, inputs) -> PreparedReceiving:
    """Prove source/qualification coherence and validate every view before writes."""
    plays, weekly = inputs.load_feeds([season], [season])
    actual = conn.execute("SELECT * FROM plays WHERE season=?", [season]).df()
    if set(plays.data.columns) - set(actual):
        raise CandidateError(f"receiving[{season}]: candidate missing captured play columns")
    _same_rows(actual[list(plays.data)].copy(), plays.data.copy(), ["game_id", "play_id"], season)
    stats = weekly.data.loc[weekly.data.player_id.notna() & weekly.data.season_type.eq("REG")].copy()
    # The receiving reference columns are the stable cross-year subset. Other
    # categories keep their existing player-game/analytics validation contracts.
    fields = ["player_id", "season", "season_type", "week", "targets", "receptions", "receiving_yards",
              "receiving_tds", "receiving_yards_after_catch", "receiving_first_downs", "receiving_air_yards"]
    stored = conn.execute("SELECT * FROM weekly_player_stats WHERE season=? AND season_type='REG' AND player_id IS NOT NULL",
                          [season]).df()
    if set(fields) - set(stored) or set(fields) - set(stats):
        raise CandidateError(f"receiving[{season}]: candidate weekly receiving schema is incomplete")
    _same_rows(stored[fields].copy(), stats[fields].copy(), ["player_id", "season", "season_type", "week"], season)
    directory, manifest, manifest_sha = inputs.receiving_run(season)
    prepared = load_receiving_season(directory, manifest, season)
    from splits_builder import qualification_ctes
    sql = qualification_ctes("receiving", season, set(actual), minimal=True)
    admitted = conn.execute(sql + """ SELECT player_id,COUNT(*) FROM base JOIN qualified USING(player_id)
                                      GROUP BY player_id ORDER BY player_id""").fetchall()
    if dict(admitted) != prepared.qualification["qualifying_plays"]:
        raise CandidateError(f"receiving[{season}]: candidate qualification differs from captured receiving context")
    report = {"format_version": 1, "status": "offline_integration_only", "publication_ready": False,
              "season": season, "source": "nflfastR official receiving calculator",
              "core_revision": inputs.revision(),
              "export_manifest_sha256": hashlib.sha256((directory / "run.json").read_bytes()).hexdigest(),
              "runtime": manifest["runtime"], "qualification": prepared.qualification,
              "whole_reference": prepared.whole, "dimensions": prepared.dimensions,
              "game_coverage": _game_coverage(conn, season, plays.data),
              "metric_policy": {"counts": "Preserve observed catches, yards and touchdowns on covered games",
                                "targets": "Unavailable in 2003-2008; observed counts elsewhere are not independent completeness certification",
                                "yac": "Unavailable before 2006",
                                "air_yards": "Unavailable before 2009 or when target/air population is incomplete",
                                "rates": "Original target role; require matching known target/EPA population",
                                "interceptions_cpoe": "Not applicable to receiving"}}
    # Keep the exact completion marker used by this build bound to the input
    # object, rather than accepting a replaced source run at the final read.
    if report["export_manifest_sha256"] != manifest_sha:
        raise CandidateError(f"receiving[{season}]: receiving completion marker changed")
    return PreparedReceiving(prepared, report)


def store_receiving(conn, season: int, prepared: PreparedReceiving) -> None:
    """Caller owns the season replacement transaction and database write lock."""
    conn.execute(_DDL)
    for rows in prepared.exports.rows.values():
        conn.register("official_receiving_rows", rows)
        try:
            conn.execute("INSERT INTO player_splits BY NAME SELECT * FROM official_receiving_rows")
        finally:
            conn.unregister("official_receiving_rows")
    reference = prepared.exports.reference.astype(object)
    reference = reference.where(reference.notna(), None).to_dict(orient="records")
    totals = prepared.exports.totals.astype(object)
    totals = totals.where(totals.notna(), None).to_dict(orient="records")
    for row in totals:
        row["excluded_counts"] = prepared.exports.exclusions[row["player_id"]]
    for table, record in ((PREPARATION_TABLE, prepared.report),
                          (TOTALS_TABLE, {"format_version": 1, "metric_policy_applied": True,
                                          "scope": "observed whole REG nonconversion receiving on supplied games",
                                          "rows": totals}),
                          (REFERENCE_TABLE, {"format_version": 1, "scope": "qualified-player whole REG nonconversion reference",
                                             "serving_ready": False, "rows": reference,
                                             "source_revisions": prepared.report["whole_reference"]["source_revisions"]})):
        conn.execute(f"DELETE FROM {table} WHERE season=?", [season])
        conn.execute(f"INSERT INTO {table} VALUES (?,?)", [season, json.dumps(record, allow_nan=False)])
