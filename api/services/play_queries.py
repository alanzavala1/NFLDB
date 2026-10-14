"""Validated play filters and fixed SQL measures, independent of model execution."""
from dataclasses import dataclass
from typing import Any
import re
import threading
from config import TEAM_NAMES
from database import query_to_dict


@dataclass
class PlayQueryResult:
    arguments: dict
    rows: list[dict]
    result: dict | str


_QUERY_PLAY_FILTER_COLUMNS = {
    "season": "season",
    "season_type": "season_type",
    "offense": "posteam",
    "defense": "defteam",
    "play": "play_type",
    "down": "down",
    "qtr": "qtr",
    "red_zone": "yardline_100",
    "pass_length": "pass_length",
    "pass_location": "pass_location",
    "run_location": "run_location",
    "run_gap": "run_gap",
    "shotgun": "shotgun",
    "passer_id": "passer_player_id",
    "rusher_id": "rusher_player_id",
    "receiver_id": "receiver_player_id",
    "ydstogo_max": "ydstogo",
}

_QUERY_PLAY_GROUP_COLUMNS = {
    "down": ("down", "down"),
    "qtr": ("qtr", "qtr"),
    "week": ("week", "week"),
    "pass_location": ("pass_location", "pass_location"),
    "pass_length": ("pass_length", "pass_length"),
    "run_gap": ("run_gap", "run_gap"),
    "offense": ("posteam", "offense"),
    "defense": ("defteam", "defense"),
}

_QUERY_PLAY_GROUP_LIMIT = 32

_QUERY_PLAY_ENUMS = {
    "season_type": ("REG", "POST", "ALL"),
    "play": ("pass", "run"),
    "pass_length": ("short", "deep"),
    "pass_location": ("left", "middle", "right"),
    "run_location": ("left", "middle", "right"),
    "run_gap": ("guard", "tackle", "end"),
}

_QUERY_PLAY_TEAM_ALIASES = {"OAK": "LV", "SD": "LAC", "STL": "LA", "JAC": "JAX"}

_QUERY_PLAY_MEASURES = """
    COUNT(*) AS plays,
    COALESCE(SUM(yards_gained), 0) AS yards,
    ROUND(AVG(yards_gained), 2) AS yards_per_play,
    COALESCE(SUM(touchdown), 0) AS touchdowns,
    COALESCE(SUM(first_down), 0) AS first_downs,
    ROUND(AVG(epa), 3) AS epa_per_play,
    ROUND(AVG(success), 3) AS success_rate"""

_QUERY_PLAY_PASS_MEASURES = """,
    COALESCE(SUM(pass_attempt), 0) AS attempts,
    COALESCE(SUM(complete_pass), 0) AS completions,
    COALESCE(SUM(sack), 0) AS sacks,
    COALESCE(SUM(interception), 0) AS interceptions"""

_QUERY_PLAY_COVERAGE = {
    "dataset_seasons": "1999-2025",
    "pass_length": "Reliable 2006-2025; sparse in 1999; absent 2000-2005.",
    "pass_location": "Reliable 2006-2025; extremely sparse 1999-2005.",
    "run_location": "Populated 1999-2025 for nearly all non-kneel rushes.",
    "run_gap": "Populated 1999-2025, but naturally null on some run concepts.",
    "shotgun": "Populated on every play row, 1999-2025.",
    "epa_success": "1999-2025; 14 of 909,271 pass/run rows are null.",
    "ydstogo": "Available after the next play-by-play data refresh.",
}

_PLAYER_ID_RE = re.compile(r"^\d{2}-\d{7}$")

_PLAYER_ID_MSG = ("That is not a player id — call resolve_entity first and use "
                  "the returned id.")

_plays_metadata_lock = threading.Lock()

_plays_columns_cache: frozenset[str] | None = None

_plays_seasons_cache: frozenset[int] | None = None

def _valid_player_id(player_id: str) -> bool:
    return isinstance(player_id, str) and _PLAYER_ID_RE.fullmatch(player_id) is not None

def _plays_metadata() -> tuple[frozenset[str], frozenset[int]]:
    """Cache the raw-play schema and available seasons for query validation."""
    global _plays_columns_cache, _plays_seasons_cache
    if _plays_columns_cache is not None and _plays_seasons_cache is not None:
        return _plays_columns_cache, _plays_seasons_cache
    with _plays_metadata_lock:
        if _plays_columns_cache is None or _plays_seasons_cache is None:
            try:
                columns = query_to_dict("DESCRIBE plays")
                seasons = query_to_dict(
                    "SELECT DISTINCT season FROM plays WHERE season IS NOT NULL ORDER BY season"
                )
                _plays_columns_cache = frozenset(row["column_name"] for row in columns)
                _plays_seasons_cache = frozenset(int(row["season"]) for row in seasons)
            except Exception:
                _plays_columns_cache = frozenset()
                _plays_seasons_cache = frozenset()
    return _plays_columns_cache, _plays_seasons_cache


def query_plays(season: int, season_type: str = "REG", offense: str = "",
                defense: str = "", play: str = "", down: int = 0,
                qtr: int = 0, red_zone: bool = False,
                pass_length: str = "", pass_location: str = "",
                run_location: str = "", run_gap: str = "",
                shotgun: int = -1, passer_id: str = "",
                rusher_id: str = "", receiver_id: str = "",
                group_by: str = "", ydstogo_max: int = 0) -> PlayQueryResult:
    """Structured play-by-play aggregation for granular situations that
    the season, career, and shaped split tools cannot express. Metrics are
    fixed server-side: plays, yards, yards/play, touchdowns, first downs,
    EPA/play, and success rate; pass queries also include attempts,
    completions, sacks, and interceptions.

    Coverage in the current dataset: shotgun, run location/gap, EPA, and
    success cover 1999-2025 (run gap is naturally null on some runs; 14
    pass/run rows lack EPA/success). Pass length/location are reliable from
    2006-2025; 1999 is sparse and 2000-2005 is absent or extremely sparse.
    ydstogo is supported after the next play-by-play refresh.

    Args:
        season: Available season year.
        season_type: REG | POST | ALL.
        offense: Optional offense team abbreviation from resolve_entity.
        defense: Optional defense team abbreviation from resolve_entity.
        play: pass | run.
        down: 1-4, or 0 for all downs.
        qtr: 1-5, or 0 for all quarters.
        red_zone: True limits plays to the opponent 20-yard line or closer.
        pass_length: short | deep.
        pass_location: left | middle | right.
        run_location: left | middle | right.
        run_gap: guard | tackle | end.
        shotgun: 0 | 1, or -1 for either.
        passer_id: Optional player id from resolve_entity.
        rusher_id: Optional player id from resolve_entity.
        receiver_id: Optional player id from resolve_entity.
        group_by: down | qtr | week | pass_location | pass_length | run_gap |
            offense | defense, or empty for one aggregate row.
        ydstogo_max: Maximum yards to go, or 0 to omit the filter.
    """
    record_args: dict[str, Any] = {"season": season}

    def reject(message: str) -> PlayQueryResult:
        return PlayQueryResult(record_args.copy(), [], message)

    try:
        s = int(season)
    except (TypeError, ValueError):
        return reject(f"Invalid season '{season}'. Use an available season year.")

    st = str(season_type).upper().strip()
    record_args["season"] = s
    record_args["season_type"] = st
    if st not in _QUERY_PLAY_ENUMS["season_type"]:
        valid = ", ".join(_QUERY_PLAY_ENUMS["season_type"])
        return reject(f"Invalid season_type '{season_type}'. Use one of: {valid}.")

    enum_values = {}
    for name, raw in (
        ("play", play), ("pass_length", pass_length),
        ("pass_location", pass_location), ("run_location", run_location),
        ("run_gap", run_gap),
    ):
        value = str(raw).lower().strip()
        enum_values[name] = value
        if value:
            record_args[name] = value
            if value not in _QUERY_PLAY_ENUMS[name]:
                valid = ", ".join(_QUERY_PLAY_ENUMS[name])
                return reject(f"Invalid {name} '{raw}'. Use one of: {valid}.")

    teams = {}
    valid_teams = ", ".join(sorted(TEAM_NAMES))
    for name, raw in (("offense", offense), ("defense", defense)):
        value = str(raw).upper().strip()
        teams[name] = value
        if value:
            record_args[name] = value
            if value not in TEAM_NAMES:
                return reject(f"Invalid {name} '{raw}'. Use one of: {valid_teams}.")

    try:
        dn = int(down)
    except (TypeError, ValueError):
        return reject(f"Invalid down '{down}'. Use one of: 0, 1, 2, 3, 4.")
    if dn not in range(5):
        record_args["down"] = dn
        return reject(f"Invalid down '{down}'. Use one of: 0, 1, 2, 3, 4.")
    if dn:
        record_args["down"] = dn

    try:
        quarter = int(qtr)
    except (TypeError, ValueError):
        return reject(f"Invalid qtr '{qtr}'. Use one of: 0, 1, 2, 3, 4, 5.")
    if quarter not in range(6):
        record_args["qtr"] = quarter
        return reject(f"Invalid qtr '{qtr}'. Use one of: 0, 1, 2, 3, 4, 5.")
    if quarter:
        record_args["qtr"] = quarter

    try:
        sg = int(shotgun)
    except (TypeError, ValueError):
        return reject(f"Invalid shotgun '{shotgun}'. Use one of: -1, 0, 1.")
    if sg not in (-1, 0, 1):
        record_args["shotgun"] = sg
        return reject(f"Invalid shotgun '{shotgun}'. Use one of: -1, 0, 1.")
    if sg != -1:
        record_args["shotgun"] = sg

    player_ids = {}
    for name, raw in (
        ("passer_id", passer_id), ("rusher_id", rusher_id),
        ("receiver_id", receiver_id),
    ):
        value = raw.strip() if isinstance(raw, str) else raw
        player_ids[name] = value
        if value:
            record_args[name] = value
            if not _valid_player_id(value):
                return reject(_PLAYER_ID_MSG)

    grouping = str(group_by).lower().strip()
    if grouping:
        record_args["group_by"] = grouping
        if grouping not in _QUERY_PLAY_GROUP_COLUMNS:
            valid = ", ".join(_QUERY_PLAY_GROUP_COLUMNS)
            return reject(f"Invalid group_by '{group_by}'. Use one of: {valid}.")

    try:
        distance = int(ydstogo_max)
    except (TypeError, ValueError):
        return reject(f"Invalid ydstogo_max '{ydstogo_max}'. Use 0 or 1-99.")
    if distance < 0 or distance > 99:
        record_args["ydstogo_max"] = distance
        return reject(f"Invalid ydstogo_max '{ydstogo_max}'. Use 0 or 1-99.")
    if distance:
        record_args["ydstogo_max"] = distance

    if red_zone:
        record_args["red_zone"] = True

    columns, available_seasons = _plays_metadata()
    if not available_seasons:
        return reject("No play-by-play seasons are available.")
    if s not in available_seasons:
        valid = ", ".join(str(value) for value in sorted(available_seasons))
        return reject(f"Invalid season '{season}'. Available seasons: {valid}.")
    if distance and _QUERY_PLAY_FILTER_COLUMNS["ydstogo_max"] not in columns:
        return reject("not ingested yet — down-and-distance filters arrive after the next data refresh.")

    conditions = [f"{_QUERY_PLAY_FILTER_COLUMNS['season']} = ?"]
    params: list[Any] = [s]
    if st != "ALL":
        conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS['season_type']} = ?")
        params.append(st)

    if teams["offense"]:
        conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS['offense']} = ?")
        params.append(_QUERY_PLAY_TEAM_ALIASES.get(teams["offense"], teams["offense"]))
    if teams["defense"]:
        conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS['defense']} = ?")
        params.append(_QUERY_PLAY_TEAM_ALIASES.get(teams["defense"], teams["defense"]))
    if enum_values["play"]:
        conditions.extend([
            f"{_QUERY_PLAY_FILTER_COLUMNS['play']} = ?",
            "qb_kneel = 0", "qb_spike = 0",
        ])
        params.append(enum_values["play"])
    if dn:
        conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS['down']} = ?")
        params.append(dn)
    if quarter:
        conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS['qtr']} = ?")
        params.append(quarter)
    if red_zone:
        conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS['red_zone']} <= ?")
        params.append(20)
    for name in ("pass_length", "pass_location", "run_location", "run_gap"):
        if enum_values[name]:
            conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS[name]} = ?")
            params.append(enum_values[name])
    if sg != -1:
        conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS['shotgun']} = ?")
        params.append(sg)
    for name in ("passer_id", "rusher_id", "receiver_id"):
        if player_ids[name]:
            conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS[name]} = ?")
            params.append(player_ids[name])
    if distance:
        conditions.append(f"{_QUERY_PLAY_FILTER_COLUMNS['ydstogo_max']} <= ?")
        params.append(distance)

    select_group = ""
    group_sql = ""
    if grouping:
        group_column, group_alias = _QUERY_PLAY_GROUP_COLUMNS[grouping]
        conditions.append(f"{group_column} IS NOT NULL")
        select_group = f"{group_column} AS {group_alias}, "
        group_sql = (f" GROUP BY {group_column} ORDER BY {group_column} "
                     f"LIMIT {_QUERY_PLAY_GROUP_LIMIT}")
    measures = _QUERY_PLAY_MEASURES
    if enum_values["play"] == "pass":
        measures += _QUERY_PLAY_PASS_MEASURES
    sql = (f"SELECT {select_group}{measures} FROM plays WHERE "
           f"{' AND '.join(conditions)}{group_sql}")
    rows = query_to_dict(sql, params)
    if not rows or not any(int(row.get("plays") or 0) for row in rows):
        return PlayQueryResult(record_args, [], "No plays matched those filters.")

    payload: dict[str, Any] = {"filters": record_args.copy(), "rows": rows}
    payload["filters"].pop("group_by", None)
    if any(int(row.get("plays") or 0) < 20 for row in rows):
        payload["note"] = "small sample — caveat rates"
    return PlayQueryResult(record_args, rows, payload)
