"""Read-only passing HTTP checks against source-replayed preparation records."""
import json
from urllib.parse import quote

import httpx

from pipeline.validation import SnapshotValidationError
from schemas.players import PlayerSplit
from schemas.passing import PassingAggregation
from schemas.receiving import ReceivingGameCoverage


def _require(condition, detail):
    if not condition:
        raise SnapshotValidationError(f"Passing API: {detail}")


def _stats(row):
    return {field: row[field] for field in PlayerSplit.model_fields}


def _check_row(row, expected, player, metrics):
    _require(_stats(row) == _stats(expected), "response differs from prepared counts/rates")
    parts = [item for item in metrics["aggregation"] if item["player_id"] == player
             and item["split_value"] == row["split_value"]]
    _require(len(parts) == 1, "missing/duplicate prepared aggregation record")
    _require(row["aggregation"] == {field: parts[0][field] for field in PassingAggregation.model_fields},
             "aggregation components differ")
    reasons = [item["metrics"] for item in metrics["unavailable"] if item["player_id"] == player
               and item["split_value"] == row["split_value"]]
    _require(len(reasons) <= 1 and row["unavailable_metrics"] == (reasons[0] if reasons else {}),
             "field explanations differ")


async def check_passing_api(conn, seasons):
    from main import app
    paths = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://passing-candidate") as client:
        for year in seasons:
            stored = conn.execute("SELECT record FROM passing_build_preparation WHERE season=?", [year]).fetchone()
            _require(stored is not None, f"missing prepared season {year}")
            report = json.loads(stored[0])
            _require("summary" in report, f"summary components not prepared for {year}")
            whole = report["summary"]["rows"]
            players = {whole[0]["player_id"]} if whole else {"passing-validation-no-player"}
            for issue in report["summary"]["metric_availability"]["unavailable"]:
                if any("contributions disagree" in reason for reason in issue["metrics"].values()):
                    players.add(issue["player_id"])
            for player in sorted(players):
                path = f"/api/players/{quote(player, safe='')}/passing-splits"
                response = await client.get(path)
                _require(response.status_code == 200, f"{path}: HTTP {response.status_code}")
                payload = response.json()
                _require(payload["player_id"] == player, "response player differs")
                selected = [item for item in payload["seasons"] if item["season"] == year]
                expected = [row for row in whole if row["player_id"] == player]
                if not expected:
                    _require(not selected, "below-admission player acquired summary")
                else:
                    _require(len(selected) == len(expected) == 1, "missing/duplicate prepared season")
                    season = selected[0]
                    _require(season["status"] == "prepared", "prepared summary is unavailable")
                    _check_row(season["overall"], expected[0], player, report["summary"]["metric_availability"])
                    query = conn.execute("SELECT * FROM player_splits WHERE player_id=? AND season=? AND category='passing'", [player, year])
                    columns = [field[0] for field in query.description]
                    canonical = {(row["split_dim"], row["split_value"]): row for row in
                                 (dict(zip(columns, values)) for values in query.fetchall())}
                    _require(len(season["rows"]) == len(canonical), "split row count differs")
                    keys = set()
                    for row in season["rows"]:
                        key = (row["split_dim"], row["split_value"])
                        _require(key in canonical and key not in keys, "missing/duplicate passing row")
                        keys.add(key)
                        _check_row(row, canonical[key], player, report["dimensions"][key[0]]["metric_availability"])
                    _require(set(season["views"]) == set(report["dimensions"]), "view coverage differs")
                    names = dict(att="attempts", cmp="completions", yards="passing_yards", td="passing_tds",
                                 interceptions="passing_interceptions", first_downs="passing_first_downs", sacks="sacks_suffered")
                    for dimension, view in season["views"].items():
                        record = report["dimensions"][dimension]
                        excluded = {field: record["excluded_by_player"][player][name] for field, name in names.items()}
                        coverage = record["coverage"]
                        _require(view["excluded"] == excluded and view["status"] == coverage["status"]
                                 and view["definition"] == coverage["definition"], "view coverage/counts differ")
                        _require(view["status"] == "complete" or bool(view["reason"]), "missing coverage explanation")
                    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
                    if "receiving_build_preparation" in tables:
                        game_record = conn.execute("SELECT record FROM receiving_build_preparation WHERE season=?", [year]).fetchone()
                        expected_games = ReceivingGameCoverage.model_validate(json.loads(game_record[0])["game_coverage"]).model_dump()
                        _require(season["game_coverage"] == expected_games, "supplied-game coverage differs")
                paths.append(path)
    return paths
