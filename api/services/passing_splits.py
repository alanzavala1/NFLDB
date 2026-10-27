"""Read prepared passing rows, components and coverage; never build statistics."""
import json
import math

import duckdb

from database import get_cursor
from schemas.passing import PlayerPassingSplits, PassingRow


class PassingDataError(RuntimeError):
    """Invalid/incomplete records must not become plausible summary numbers."""


def _index(records):
    result = {}
    for row in records:
        key = (row["player_id"], row["split_value"])
        if key in result:
            raise PassingDataError("Duplicate prepared passing component")
        result[key] = row
    return result


def _metric_index(metrics):
    return _index(metrics["unavailable"]), _index(metrics["aggregation"])


def _row(row, player, metrics):
    key = (player, row["split_value"])
    unavailable, aggregation = metrics
    reasons = unavailable.get(key, {}).get("metrics", {})
    components = aggregation[key]
    missing = {field for field in ("epa", "success_pct", "cpoe", "air_yards", "yac") if row[field] is None}
    if set(reasons) != missing or not all(isinstance(reason, str) and reason.strip() for reason in reasons.values()):
        raise PassingDataError("Missing or inconsistent passing field explanation")
    result = PassingRow.model_validate(dict(row, unavailable_metrics=reasons, aggregation=components))
    if any(result.model_dump()[field] is None for field in ("att", "cmp", "yards", "td", "interceptions", "first_downs")):
        raise PassingDataError("Missing verified passing count")
    parts = result.aggregation
    if (parts.cpoe_sum is None) != (parts.cpoe_count is None):
        raise PassingDataError("Incomplete CPOE components")
    if parts.cpoe_count == 0 and parts.cpoe_sum != 0:
        raise PassingDataError("CPOE sum without observations")
    if parts.successes is not None and parts.successes > result.att:
        raise PassingDataError("Impossible passing success count")
    # Canonical rates were rounded for storage (4, 1 and 2 decimal places).
    # Components retain the original sums; only this consistency check allows
    # display rounding. Source replay still compares every prepared record.
    for value, numerator, denominator, tolerance in (
        (result.epa, parts.epa_sum, result.att, .00011),
        (result.success_pct, None if parts.successes is None else 100 * parts.successes, result.att, .051),
        (result.cpoe, parts.cpoe_sum, parts.cpoe_count, .0051),
    ):
        if value is not None and (numerator is None or not denominator or
                not math.isclose(value, numerator / denominator, rel_tol=0, abs_tol=tolerance)):
            raise PassingDataError("Passing rate differs from prepared components")
    return result.model_dump()


_COUNTS = {"att": "attempts", "cmp": "completions", "yards": "passing_yards", "td": "passing_tds",
           "interceptions": "passing_interceptions", "first_downs": "passing_first_downs", "sacks": "sacks_suffered"}


def _season(year, player, rows, report, game_coverage):
    summary = report["summary"]
    if report["season"] != year or report["format_version"] != 1 or summary["format_version"] != 1:
        raise PassingDataError("Unsupported prepared passing season")
    whole = [row for row in summary["rows"] if row["player_id"] == player]
    if len(whole) != 1 or whole[0]["season"] != year:
        raise PassingDataError("Missing/duplicate independent passing total")
    overall = _row(whole[0], player, _metric_index(summary["metric_availability"]))
    explained, views = [], {}
    if set(row["split_dim"] for row in rows) - report["dimensions"].keys():
        raise PassingDataError("Unexpected passing view")
    for dimension, record in report["dimensions"].items():
        selected = [row for row in rows if row["split_dim"] == dimension]
        if len({row["split_value"] for row in selected}) != len(selected):
            raise PassingDataError("Duplicate passing bucket")
        metrics = _metric_index(record["metric_availability"])
        explained.extend(_row(row, player, metrics) for row in selected)
        raw = record["excluded_by_player"][player]
        excluded = {field: raw[name] for field, name in _COUNTS.items()}
        for field in _COUNTS.keys() - {"sacks"}:
            if overall[field] != excluded[field] + sum(row[field] for row in selected):
                raise PassingDataError("Passing view does not conserve verified counts")
        coverage = record["coverage"]
        reason = coverage["reason"]
        if coverage.get("charting_source", {}).get("status", "loaded") != "loaded":
            reason = "Play charting is unavailable for this season."
        views[dimension] = {"status": coverage["status"], "reason": reason,
                            "definition": coverage["definition"], "excluded": excluded}
    return {"season": year, "status": "prepared", "reason": None, "overall": overall,
            "rows": explained, "game_coverage": game_coverage, "views": views}


def _read(conn, player):
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    rows = []
    if "player_splits" in tables:
        query = conn.execute("""SELECT * FROM player_splits WHERE player_id=? AND category='passing'
            ORDER BY season,split_dim,sort_order,split_value""", [player])
        columns = [column[0] for column in query.description]
        rows = [dict(zip(columns, row)) for row in query.fetchall()]
    reports = {}
    if "passing_build_preparation" in tables:
        # Select seasons in which this player qualified. The response projection
        # below omits file paths, build diagnostics and every other player.
        records = conn.execute("""SELECT p.season,p.record FROM passing_build_preparation p
            WHERE EXISTS (SELECT 1 FROM json_each(p.record->'summary'->'rows') j
                WHERE json_extract_string(j.value,'$.player_id')=?) ORDER BY p.season""", [player]).fetchall()
        reports = {year: json.loads(record) for year, record in records}
    games = {}
    if "receiving_build_preparation" in tables:
        games = {year: json.loads(record).get("game_coverage") for year, record in conn.execute(
            "SELECT season,record FROM receiving_build_preparation").fetchall()}
    seasons = []
    for year in sorted({row["season"] for row in rows} | reports.keys()):
        if year not in reports:
            seasons.append({"season": year, "status": "unverified", "reason": "Passing summary components have not been prepared for this season.",
                            "overall": None, "rows": [], "game_coverage": None, "views": {}})
        else:
            seasons.append(_season(year, player, [row for row in rows if row["season"] == year], reports[year], games.get(year)))
    return {"player_id": player, "scope": "Qualified regular-season passing; observed production on supplied games", "seasons": seasons}


def read_player_passing(player_id):
    with get_cursor() as conn:
        conn.execute("BEGIN TRANSACTION")
        try:
            result = PlayerPassingSplits.model_validate(_read(conn, player_id))
            conn.execute("COMMIT")
            return result
        except (KeyError, TypeError, ValueError, duckdb.Error) as error:
            conn.execute("ROLLBACK")
            raise PassingDataError("Invalid prepared passing records") from error
        except BaseException:
            conn.execute("ROLLBACK")
            raise
