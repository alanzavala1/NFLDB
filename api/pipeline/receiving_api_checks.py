"""Representative receiving HTTP reads for every validated regular season."""
import json
from urllib.parse import quote

import httpx

from pipeline.validation import SnapshotValidationError
from schemas.players import PlayerSplit
from schemas.receiving import ReceivingGameCoverage


def _require(condition, path, detail):
    if not condition:
        raise SnapshotValidationError(f"{path}: {detail}")


def _stats(row):
    return {field: row[field] for field in PlayerSplit.model_fields}


def _reasons(row, path):
    missing = {field for field in ("att", "cmp", "yards", "td", "interceptions", "air_yards", "yac",
                                    "first_downs", "epa", "success_pct", "cpoe") if row[field] is None}
    reasons = row["unavailable_metrics"]
    _require(set(reasons) == missing and all(isinstance(value, str) and value.strip() for value in reasons.values()),
             path, "NULL fields must have individual nonempty explanations")


def _season(conn, payload, year, total, report, path):
    selected = [item for item in payload["seasons"] if item["season"] == year]
    _require(len(selected) == 1, path, f"missing/duplicate prepared season {year}")
    data = selected[0]
    _require(data["status"] == "prepared" and data["overall"] is not None, path, "prepared whole totals unavailable")
    _require(_stats(data["overall"]) == _stats(total), path, "whole response differs from prepared independent totals")
    _reasons(data["overall"], path)
    rows = conn.execute("SELECT * FROM player_splits WHERE season=? AND player_id=? AND category='receiving'",
                        [year, total["player_id"]]).df().astype(object)
    rows = rows.where(rows.notna(), None).to_dict(orient="records")
    expected = {(row["split_dim"], row["split_value"]): _stats(row) for row in rows}
    actual = {(row["split_dim"], row["split_value"]): _stats(row) for row in data["rows"]}
    _require(len(data["rows"]) == len(expected) and actual == expected, path, "split response differs from canonical rows")
    for row in data["rows"]:
        _reasons(row, path)
    expected_games = ReceivingGameCoverage.model_validate(report["game_coverage"]).model_dump()
    _require(data["game_coverage"] == expected_games, path, "missing/unconfirmed game coverage differs")
    _require(set(data["views"]) == set(report["dimensions"]), path, "missing/extra receiving views")
    for dimension, view in data["views"].items():
        coverage = report["dimensions"][dimension]["coverage"]
        _require(view["status"] == coverage["status"] and view["definition"] == coverage["definition"]
                 and view["excluded"] == total["excluded_counts"][dimension], path,
                 f"{dimension} coverage differs from this player's prepared exclusions")
        _require(coverage["status"] == "complete" or bool(view["reason"]), path, f"{dimension} missing coverage reason")


async def check_receiving_api(conn, seasons):
    """Check ordinary and excluded-production samples, plus empty admission.

    No lifespan/startup writes. This checks the serving contract against stored
    records after source-bound validation; it does not certify source freshness.
    """
    from main import app
    paths = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://receiving-candidate") as client:
        for year in seasons:
            record = conn.execute("SELECT record FROM receiving_season_totals WHERE season=?", [year]).fetchone()
            _require(record is not None, "receiving API", f"missing totals for {year}")
            totals = json.loads(record[0])["rows"]
            report = json.loads(conn.execute("SELECT record FROM receiving_build_preparation WHERE season=?", [year]).fetchone()[0])
            if totals:
                gap_sample = max(totals, key=lambda row: max(values["cmp"] for values in row["excluded_counts"].values()))
                samples = {row["player_id"]: row for row in (totals[0], gap_sample)}
            else:
                receiver = conn.execute("""SELECT receiver_player_id FROM plays WHERE season=?
                    AND season_type='REG' AND receiver_player_id IS NOT NULL LIMIT 1""", [year]).fetchone()
                samples = {receiver[0] if receiver else "receiving-validation-no-player": None}
            for player, total in samples.items():
                path = f"/api/players/{quote(player, safe='')}/receiving-splits"
                response = await client.get(path)
                _require(response.status_code == 200, path, f"HTTP {response.status_code}")
                payload = response.json()
                _require(payload["player_id"] == player, path, "response player differs from request")
                if total is None:
                    _require(not any(item["season"] == year for item in payload["seasons"]), path,
                             "below-threshold player acquired a receiving season")
                else:
                    _season(conn, payload, year, total, report, path)
                paths.append(path)
    return paths
