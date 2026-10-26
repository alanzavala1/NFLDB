"""Read prepared receiving rows and coverage; never build or open export files."""
import json

import duckdb

from database import get_cursor
from schemas.receiving import PlayerReceivingSplits, ReceivingRow
from services.receiving_coverage import air_yards_unavailable, targets_unavailable, yac_unavailable


class ReceivingDataError(RuntimeError):
    """Incomplete/corrupt prepared records must not become plausible statistics."""


def _row(row: dict) -> dict:
    """Explain each NULL independently; do not replace it with zero."""
    season = row["season"]
    unsupported = ["interceptions", "cpoe"]
    if targets_unavailable([season]):
        unsupported.extend(["att", "epa", "success_pct"])
    if yac_unavailable([season]):
        unsupported.append("yac")
    if air_yards_unavailable([season]):
        unsupported.append("air_yards")
    if any(row[field] is not None for field in unsupported):
        raise ReceivingDataError("Unsupported receiving field was not masked")
    reasons = {}
    for field in ("att", "cmp", "yards", "td", "yac", "first_downs", "air_yards", "epa", "success_pct"):
        if row[field] is not None:
            continue
        if field in ("att", "epa", "success_pct") and targets_unavailable([season]):
            reason = "Target records are incomplete for 2003–2008."
        elif field == "yac" and yac_unavailable([season]):
            reason = "Yards after catch are unavailable before 2006."
        elif field == "air_yards" and air_yards_unavailable([season]):
            reason = "Supported air-yard and target records are unavailable for this season."
        elif field in ("epa", "success_pct"):
            reason = ("No recorded targets in this row." if row["att"] == 0 else
                      "The target population or required EPA inputs could not be verified.")
        elif field == "air_yards":
            reason = "The target population or required air-yard inputs could not be verified."
        else:
            raise ReceivingDataError(f"Missing prepared count: {field}")
        reasons[field] = reason
    # These fields apply to other categories in the shared split schema.
    reasons.update(interceptions="Not a receiving metric.", cpoe="Not a receiving metric.")
    return ReceivingRow.model_validate(dict(row, unavailable_metrics=reasons)).model_dump()


def _view(coverage: dict, overall: dict, rows: list[dict], excluded: dict) -> dict:
    """Conservation of prepared counts, never a target-based rate calculation."""
    for field in ("att", "cmp", "yards", "td", "yac", "first_downs"):
        if overall[field] is None:
            if excluded[field] is not None:
                raise ReceivingDataError(f"Unmasked excluded count: {field}")
        else:
            if any(row[field] is None for row in rows):
                raise ReceivingDataError(f"Missing classified count: {field}")
            if overall[field] != excluded[field] + sum(row[field] for row in rows):
                raise ReceivingDataError(f"Prepared view does not conserve {field}")
    reason = coverage["reason"]
    if coverage.get("charting_source", {}).get("status", "loaded") != "loaded":
        # Build diagnostics may include a provider URL or local path. Keep
        # those in the preparation record, not the public explanation.
        reason = "Play charting is unavailable for this season."
    return {"status": coverage["status"], "reason": reason,
            "definition": coverage["definition"], "excluded": excluded}


def read_player_receiving(player_id: str) -> PlayerReceivingSplits:
    """Use a single independent cursor/transaction for a consistent read."""
    with get_cursor() as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            result = PlayerReceivingSplits.model_validate(_read(conn, player_id))
            conn.execute("COMMIT")
            return result
        except (KeyError, TypeError, ValueError, duckdb.Error) as error:
            conn.execute("ROLLBACK")
            raise ReceivingDataError("Invalid prepared receiving records") from error
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def _read(conn, player_id: str) -> dict:
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    rows = []
    if "player_splits" in tables:
        query = conn.execute("""SELECT * FROM player_splits WHERE player_id=? AND category='receiving'
                                ORDER BY season,split_dim,sort_order,split_value""", [player_id])
        columns = [item[0] for item in query.description]
        rows = [dict(zip(columns, row)) for row in query.fetchall()]
    totals, reports, exclusions = {}, {}, {}
    if {"receiving_season_totals", "receiving_build_preparation"} <= tables:
        # Filter in SQL: don't send every qualified player's rows or build
        # internals to the API consumer. Raw receiving_whole_reference is never read.
        records = conn.execute("""SELECT t.season,t.record->>'format_version',
                t.record->>'metric_policy_applied',j.value,p.record
            FROM receiving_season_totals t, json_each(t.record->'rows') j,
                 receiving_build_preparation p
            WHERE p.season=t.season AND json_extract_string(j.value,'$.player_id')=?
            ORDER BY t.season""", [player_id]).fetchall()
        for season, version, applied, total, report in records:
            if version != "1" or applied != "true" or season in totals:
                raise ReceivingDataError("Unsupported/duplicate prepared receiving totals")
            totals[season], reports[season] = json.loads(total), json.loads(report)
            exclusions[season] = totals[season]["excluded_counts"]
    seasons = []
    for season in sorted({row["season"] for row in rows} | totals.keys()):
        if season not in totals:
            seasons.append({"season": season, "status": "unverified",
                "reason": "Coverage-aware receiving totals have not been prepared for this season.",
                "overall": None, "rows": [], "game_coverage": None, "views": {}})
            continue
        total, report = totals[season], reports[season]
        if total["season"] != season or report["season"] != season or report["format_version"] != 1:
            raise ReceivingDataError("Inconsistent prepared receiving season")
        selected = [row for row in rows if row["season"] == season]
        views = {dimension: _view(data["coverage"], total,
                                  [row for row in selected if row["split_dim"] == dimension],
                                  exclusions[season][dimension])
                 for dimension, data in report["dimensions"].items()}
        seasons.append({"season": season, "status": "prepared", "reason": None,
                        "overall": _row(total), "rows": [_row(row) for row in selected],
                        "game_coverage": report["game_coverage"], "views": views})
    return {"player_id": player_id,
            "scope": "Qualified regular-season receiving; observed production on supplied games",
            "seasons": seasons}
