"""Natural-language "ask" agent over the NFL platform.

Design decision that defines this feature: the model answers questions by
calling a small set of **typed tools that wrap the platform's already-reconciled
query layer** — it never sees SQL or the database. Every number it reports
routes through the same code the Players / Leaders / Splits pages use, which is
tested to reconcile exactly with official NFL weekly stats. Text-to-SQL would
let the model re-derive stat definitions (nflfastR counts sacks as pass
attempts, QB kneels as carries, passing EPA = SUM(qb_epa) over dropbacks, ...)
and silently contradict that reconciliation work. Typed tools make that
impossible: the model can only ask questions we've already verified are correct.

The Anthropic client is built lazily and resolves credentials from the
environment (an `ant auth login` subscription profile for local dev, or
ANTHROPIC_API_KEY in deploy) — so importing this module needs no credentials
and the test suite stays green.
"""
import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any, Callable

import anthropic
from anthropic import beta_tool
from dotenv import load_dotenv
from fastapi import HTTPException

# Load api/.env (if present) so ANTHROPIC_API_KEY / ANTHROPIC_MODEL can live in a
# gitignored file for local dev. Resolved relative to this file so it works no
# matter the working directory (server runs from api/, eval imports llm directly).
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import comparables_builder
import def_splits_builder
import splits_builder
import team_splits_builder
from config import CURRENT_SEASON, FIRST_SEASON, TEAM_NAMES
from database import query_to_dict
from routers.leaders import get_leaders as _leaders_query
from routers.leaders import get_standings as _standings_query
from routers.leaders import search as _search_query
from routers.players import get_player as _player_profile
from routers.power_rankings import get_power_rankings as _power_rankings_query
from routers.schedule import get_game as _game_query
from routers.schedule import get_schedule as _schedule_query
from routers.teams import get_team as _team_query
from routers.teams import get_team_depth_chart as _team_depth_query
from routers.teams import get_team_injuries as _team_injuries_query

# ── Model + client ────────────────────────────────────────────────────────────

# Haiku is the default cost lever (cheap, fast, strong enough for this routing).
# Set ANTHROPIC_MODEL=claude-opus-4-8 for the best tool-routing when you want it.
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

# Hard ceiling on tool executions per question, so one prompt can't loop
# expensively. When exceeded, tools tell the model to finalize.
_MAX_TOOL_CALLS = 10

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Build the client on first use and log which auth mode is active, so it's
    never a mystery whether calls are billing to a subscription or an API key."""
    global _client
    if _client is None:
        mode = "API key (metered)" if os.environ.get("ANTHROPIC_API_KEY") else "logged-in profile / subscription"
        print(f"[ask] Anthropic auth: {mode}; model: {MODEL}")
        _client = anthropic.Anthropic()  # resolves key OR `ant auth login` profile
    return _client


# ── Data vocabulary (kept in sync with the splits builders) ───────────────────
# These are the dimension names the splits tables actually use. They're stated
# explicitly here (rather than queried) because they ARE the contract — the
# system prompt and get_metadata both surface them so the model picks valid
# arguments instead of guessing.

_COMMON_OFF_DIMS = ["down", "game_script", "quarter", "shotgun", "field_zone",
                    "home_away", "roof", "surface", "no_huddle", "game_state",
                    "opponent", "opp_division"]

_DIMENSIONS: dict[str, list[str]] = {
    "passing":   ["pass_depth", "pass_location", "pressure", "play_action", "blitz"] + _COMMON_OFF_DIMS,
    "rushing":   ["run_gap", "run_direction", "box_count"] + _COMMON_OFF_DIMS,
    "receiving": ["target_depth", "target_direction", "pressure", "play_action", "blitz"] + _COMMON_OFF_DIMS,
    "defense":   ["vs_play", "down", "game_script", "quarter", "field_zone",
                  "home_away", "roof", "surface", "no_huddle", "game_state",
                  "opponent", "opp_division"],
}

_TEAM_DIMS = ["down", "quarter", "game_script", "field_zone", "home_away",
              "roof", "surface", "no_huddle", "game_state", "opponent", "opp_division"]

# Exact split_value labels from splits_core.py and the three split builders.
# Synonyms are routing hints only; tools must still receive the exact labels.
_OPPONENT_VALUES = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
    "OAK", "SD", "STL",
]
_DIVISION_VALUES = [
    "AFC East", "AFC North", "AFC South", "AFC West",
    "NFC East", "NFC North", "NFC South", "NFC West",
]

_SPLIT_VOCABULARY: dict[str, dict[str, Any]] = {
    "pass_depth": {
        "values": ["short", "deep"],
        "synonyms": {"short": ["short pass", "underneath"],
                     "deep": ["deep ball", "shot downfield"]},
    },
    "pass_location": {
        "values": ["left", "middle", "right"],
        "synonyms": {"middle": ["over the middle"]},
    },
    "pressure": {
        "values": ["clean", "pressured"],
        "synonyms": {"clean": ["clean pocket"],
                     "pressured": ["under pressure", "QB hit"]},
        "note": "Pressure is the nflfastR qb_hit proxy, not a charted pressure rate.",
    },
    "play_action": {
        "values": ["play_action", "no_pa"],
        "synonyms": {"play_action": ["play fake", "play-action"],
                     "no_pa": ["no play action", "straight dropback"]},
    },
    "blitz": {
        "values": ["standard_rush", "blitz"],
        "synonyms": {"standard_rush": ["not blitzed"],
                     "blitz": ["when blitzed", "5+ rushers"]},
    },
    "target_depth": {
        "values": ["short", "deep"],
        "synonyms": {"short": ["short target", "underneath"],
                     "deep": ["deep target", "deep ball"]},
    },
    "target_direction": {
        "values": ["left", "middle", "right"],
        "synonyms": {"middle": ["over the middle"]},
    },
    "run_gap": {
        "values": ["guard", "tackle", "end"],
        "synonyms": {"guard": ["guard gap"], "tackle": ["tackle gap"],
                     "end": ["edge", "end run"]},
    },
    "run_direction": {
        "values": ["left", "middle", "right"],
        "synonyms": {"middle": ["up the middle"]},
    },
    "box_count": {
        "values": ["light_box", "neutral_box", "stacked_box"],
        "synonyms": {"light_box": ["light box", "6 or fewer defenders"],
                     "neutral_box": ["7-man box"],
                     "stacked_box": ["stacked box", "loaded box", "8+ defenders"]},
    },
    "vs_play": {
        "values": ["vs_pass", "vs_run"],
        "synonyms": {"vs_pass": ["against passes", "on pass plays"],
                     "vs_run": ["against runs", "on run plays"]},
    },
    "down": {
        "values": ["1", "2", "3", "4"],
        "synonyms": {"1": ["first down", "1st down"],
                     "2": ["second down", "2nd down"],
                     "3": ["third down", "3rd down"],
                     "4": ["fourth down", "4th down"]},
    },
    "game_script": {
        "values": ["leading", "tied", "trailing"],
        "synonyms": {"leading": ["ahead", "playing with a lead"],
                     "tied": ["score tied"],
                     "trailing": ["behind", "playing from behind", "down big"]},
        "note": "These labels do not encode lead size; defense uses its own perspective.",
    },
    "quarter": {
        "values": ["1", "2", "3", "4", "OT"],
        "synonyms": {"1": ["first quarter"], "2": ["second quarter"],
                     "3": ["third quarter"], "4": ["fourth quarter"],
                     "OT": ["overtime"]},
    },
    "shotgun": {
        "values": ["shotgun", "under_center"],
        "synonyms": {"under_center": ["under center"]},
    },
    "field_zone": {
        "values": ["own_territory", "opp_territory", "red_zone"],
        "synonyms": {"own_territory": ["own side of the field"],
                     "opp_territory": ["opponent territory", "plus territory"],
                     "red_zone": ["red zone", "inside the 20"]},
    },
    "home_away": {
        "values": ["home", "away"],
        "synonyms": {"home": ["at home"], "away": ["on the road", "road game"]},
    },
    "roof": {
        "values": ["dome", "outdoors"],
        "synonyms": {"dome": ["indoors", "closed roof"],
                     "outdoors": ["outside", "open roof"]},
        "note": "Source roof values dome/closed map to dome; outdoors/open map to outdoors.",
    },
    "surface": {
        "values": ["grass", "turf"],
        "synonyms": {"turf": ["artificial turf", "synthetic surface"]},
        "note": "Every non-empty source surface other than grass maps to turf.",
    },
    "no_huddle": {
        "values": ["huddle", "no_huddle"],
        "synonyms": {"huddle": ["with a huddle"],
                     "no_huddle": ["no huddle", "hurry-up"]},
    },
    "game_state": {
        "values": ["competitive", "garbage"],
        "synonyms": {"competitive": ["meaningful snaps", "close game"],
                     "garbage": ["garbage time", "blowout", "game already decided"]},
        "note": "Competitive means win probability 5%-95%; garbage is outside that band.",
    },
    "opponent": {
        "values": _OPPONENT_VALUES,
        "synonyms": {},
        "note": "Use the team abbreviation from resolve_entity; OAK/SD/STL are historical labels.",
        "prompt": "team abbreviation from resolve_entity; historical OAK/SD/STL",
    },
    "opp_division": {
        "values": _DIVISION_VALUES,
        "synonyms": {},
        "note": "The opponent's division.",
        "prompt": "AFC/NFC East, North, South, or West",
    },
}

# Numeric columns the leaders table exposes (the season totals you can rank by).
_LEADER_STATS = [
    "attempts", "completions", "pass_yards", "pass_tds", "interceptions_thrown",
    "sacks_taken", "carries", "rush_yards", "rush_tds", "targets", "receptions",
    "rec_yards", "rec_tds", "yac", "air_yards", "pass_epa", "rush_epa", "rec_epa",
    "solo_tackles", "assist_tackles", "tackles_for_loss", "sacks", "qb_hits",
    "def_interceptions", "pass_breakups", "forced_fumbles", "fumble_recoveries",
    "fg_att", "fg_made", "xp_att", "xp_made", "punts", "punt_yards",
]

_DERIVED_METRICS = {
    "completion_pct": {"formula": "100 * completions / attempts",
                       "inputs": ["completions", "attempts"]},
    "yards_per_attempt": {"formula": "pass_yards / attempts",
                          "inputs": ["pass_yards", "attempts"]},
    "yards_per_carry": {"formula": "rush_yards / carries",
                        "inputs": ["rush_yards", "carries"]},
    "catch_rate": {"formula": "100 * receptions / targets",
                   "inputs": ["receptions", "targets"]},
    "td_rate": {"formula": "100 * touchdowns / matching attempts or opportunities",
                "inputs": ["touchdowns", "matching attempts or opportunities"]},
    "passer_rating": {
        "formula": "standard NFL passer-rating formula",
        "inputs": ["completions", "attempts", "pass_yards", "pass_tds",
                   "interceptions_thrown"],
        "requirement": "Fetch every input (all four formula components) or decline.",
    },
}

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

_COVERAGE = {
    "seasons": f"{FIRST_SEASON}-{CURRENT_SEASON}",
    "game_results": "Regular season and playoffs (WC, DIV, CON, SB).",
    "player_team_stats": "Regular season only.",
    "ngs_tracking_stats_from": 2016,      # CPOE, time-to-throw, separation, ...
    "ftn_charting_dims_from": 2022,       # play_action, blitz, box_count
    "snap_counts_from": 2012,
    "query_plays": _QUERY_PLAY_COVERAGE,
    "note": "Defensive splits are counting stats only. Awards reflect a curated "
            "set of real voted postseason awards — never infer an award from stats.",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dumps(obj: Any) -> str:
    """Compact JSON for tool results (keeps token cost down)."""
    return json.dumps(obj, separators=(",", ":"), default=str)


def _nonzero(d: dict) -> dict:
    """Drop null/zero fields — used only for the overview's counting line, to
    keep it compact (a stat of 0 isn't interesting context for the model)."""
    return {k: v for k, v in d.items() if v not in (None, 0, 0.0)}


_RESULT_LIMIT = 25
_PLAYER_ID_RE = re.compile(r"^\d{2}-\d{7}$")
_PLAYER_ID_MSG = ("That is not a player id — call resolve_entity first and use "
                  "the returned id.")
_plays_metadata_lock = threading.Lock()
_plays_columns_cache: frozenset[str] | None = None
_plays_seasons_cache: frozenset[int] | None = None
_GAME_LINE_STATS = [
    "attempts", "completions", "pass_yards", "pass_tds", "interceptions_thrown",
    "sacks_taken", "carries", "rush_yards", "rush_tds", "targets", "receptions",
    "rec_yards", "rec_tds",
]


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


def _season_stat_line(games: list[dict]) -> dict:
    """Sum the profile page's reconciled per-game columns into one compact line."""
    totals = {col: round(sum(g.get(col) or 0 for g in games), 2) for col in STAT_COLS}
    return _nonzero(totals)


def _regular_record(games: list[dict], team: str) -> str:
    """Fallback record from the team router's completed regular-season games."""
    wins = losses = ties = 0
    for game in games:
        if game.get("game_type") != "REG":
            continue
        away_score, home_score = game.get("away_score"), game.get("home_score")
        if away_score is None or home_score is None:
            continue
        team_score = home_score if game.get("home_team") == team else away_score
        opp_score = away_score if game.get("home_team") == team else home_score
        if team_score > opp_score:
            wins += 1
        elif team_score < opp_score:
            losses += 1
        else:
            ties += 1
    return f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}"


def _conversation_messages(question: str, history: list[dict] | None = None) -> list[dict]:
    """Build an Anthropic-safe text transcript ending with the new question.

    Routes already cap history; this defensive pass drops malformed entries,
    removes an assistant-only prefix, and merges consecutive equal roles.
    """
    raw = [*(history or []), {"role": "user", "content": question}]
    messages: list[dict] = []
    for message in raw:
        if isinstance(message, dict):
            role = message.get("role")
            content = message.get("content")
        else:
            role = getattr(message, "role", None)
            content = getattr(message, "content", None)
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content or (not messages and role == "assistant"):
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + content
        else:
            messages.append({"role": role, "content": content})
    return messages


# Stat columns to sum for a player's season line, reusing the platform's single
# source of truth for what "a stat" is.
from sql_helpers import STAT_COLS  # noqa: E402


# ── Per-request collector ─────────────────────────────────────────────────────

class _Ctx:
    """Accumulates what happened during one /ask request: the tool calls made
    (for the transparency line) and the rows from the last data-bearing tool
    (for the frontend table)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.data: list[dict] = []
        self.n_calls = 0
        self.question = ""

    def over_budget(self) -> bool:
        self.n_calls += 1
        return self.n_calls > _MAX_TOOL_CALLS

    def record(self, tool: str, args: dict, rows: list[dict] | None = None) -> None:
        self.calls.append({"tool": tool, "args": args})
        if rows is not None:
            self.data = rows


_BUDGET_MSG = ("Tool-call budget reached. Answer the user now using the data you "
               "already have; do not call more tools.")


# ── Data-gap log ──────────────────────────────────────────────────────────────
# When the model hits a question the platform can't fully answer, it logs the gap
# here (one JSON line each) so we can review what's worth adding. Lives in the
# gitignored data dir; review via GET /api/gaps or by opening the file.
_GAP_LOG = os.path.join(os.path.dirname(__file__), "data", "data_gaps.jsonl")
_gap_lock = threading.Lock()


def _log_gap(question: str, topic: str, detail: str) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "question": question, "topic": topic, "detail": detail}
    try:
        os.makedirs(os.path.dirname(_GAP_LOG), exist_ok=True)
        with _gap_lock, open(_GAP_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        print(f"[ask] could not write gap log: {e}")


def read_gaps(limit: int = 50) -> list[dict]:
    """Most-recent-first list of logged data gaps (for review)."""
    if not os.path.exists(_GAP_LOG):
        return []
    out: list[dict] = []
    try:
        with open(_GAP_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        return []
    return list(reversed(out))[:limit]


# ── Tool factory ──────────────────────────────────────────────────────────────
# Tools are built per request as closures over `ctx`, so concurrent requests
# never share state. The generated tool *schemas* are identical across requests
# (same signatures + docstrings), so prompt caching of the tool definitions
# still works.

def _build_tools(ctx: _Ctx) -> list[Callable]:

    @beta_tool
    def resolve_entity(name: str) -> str:
        """Resolve a player or team name to its id. ALWAYS call this first for
        any player or team mentioned in a question. Returns candidates with
        id, name, position and team so you can disambiguate (e.g. two players
        with the same name). For a player, use the returned id as `player_id`
        in other tools; for a team, use the abbreviation id (e.g. "KC") as
        `team`.

        Args:
            name: The player or team name to look up, e.g. "Josh Allen" or "49ers".
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        rows = _search_query(q=name)
        out = [{"type": r["type"], "id": r["id"], "name": r["name"],
                "position": r.get("position"), "team": r.get("team")} for r in rows]
        ctx.record("resolve_entity", {"name": name})
        return _dumps(out) if out else "No player or team matched that name."

    @beta_tool
    def query_plays(season: int, season_type: str = "REG", offense: str = "",
                    defense: str = "", play: str = "", down: int = 0,
                    qtr: int = 0, red_zone: bool = False,
                    pass_length: str = "", pass_location: str = "",
                    run_location: str = "", run_gap: str = "",
                    shotgun: int = -1, passer_id: str = "",
                    rusher_id: str = "", receiver_id: str = "",
                    group_by: str = "", ydstogo_max: int = 0) -> str:
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
        if ctx.over_budget():
            return _BUDGET_MSG

        record_args: dict[str, Any] = {"season": season}

        def reject(message: str) -> str:
            ctx.record("query_plays", record_args.copy())
            return message

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
            ctx.record("query_plays", record_args, [])
            return "No plays matched those filters."

        payload: dict[str, Any] = {"filters": record_args.copy(), "rows": rows}
        payload["filters"].pop("group_by", None)
        if any(int(row.get("plays") or 0) < 20 for row in rows):
            payload["note"] = "small sample — caveat rates"
        ctx.record("query_plays", record_args, rows)
        return _dumps(payload)

    @beta_tool
    def find_games(season: int, team: str = "", week: int = 0) -> str:
        """Find regular-season or playoff game results and game_ids. Use the
        game_id from a filtered result with get_game_detail when box-score
        context is needed.

        Args:
            season: The season year, e.g. 2023.
            team: Optional team abbreviation from resolve_entity, e.g. "KC".
            week: Optional NFL week; 0 searches the whole season.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        s = int(season)
        tm = team.upper().strip()
        wk = max(0, int(week))
        args = {"season": s, "team": tm, "week": wk}
        schedule = _schedule_query(season=s)
        matches = [
            game
            for group in schedule
            for game in group.get("games", [])
            if (not tm or tm in (game.get("away_team"), game.get("home_team")))
            and (not wk or int(game.get("week", -1)) == wk)
        ]
        truncated = len(matches) > _RESULT_LIMIT
        if truncated:
            # Preserve postseason discoverability in a whole-season preview so
            # Super Bowl questions do not require the caller to know its week.
            preview = sorted(
                matches,
                key=lambda game: (game.get("game_type") == "REG", int(game.get("week", 0))),
            )
            keys = ("game_id", "week", "game_type", "away_team", "home_team",
                    "away_score", "home_score")
        else:
            preview = matches
            keys = ("game_id", "week", "game_type", "gameday", "away_team",
                    "home_team", "away_score", "home_score", "overtime")
        rows = [
            {key: (bool(game[key]) if key == "overtime" else game[key])
             for key in keys if game.get(key) is not None}
            for game in preview[:_RESULT_LIMIT]
        ]
        payload = {
            "season": s,
            "matched": len(matches),
            "truncated": truncated,
            "games": rows,
        }
        if truncated:
            payload["note"] = ("Showing 25 compact results; narrow by team and/or "
                               "week for a complete result set.")
        ctx.record("find_games", args, rows)
        return _dumps(payload) if matches else f"No games found for those filters in {s}."

    @beta_tool
    def get_game_detail(game_id: str) -> str:
        """One trimmed game result: game metadata, quarter scoring, and each
        team's top five pass/rush/receiving performers. Get game_id from
        find_games first; the full play chart and full box score are omitted.

        Args:
            game_id: Exact game_id returned by find_games.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        args = {"game_id": game_id}
        try:
            game = _game_query(game_id)
        except HTTPException:
            ctx.record("get_game_detail", args)
            return "No game found for that game_id."

        meta_keys = (
            "game_id", "season", "game_type", "week", "gameday", "away_team",
            "home_team", "away_score", "home_score", "away_record", "home_record",
            "overtime", "roof", "surface", "away_coach", "home_coach",
        )
        meta = {
            key: (bool(game[key]) if key == "overtime" else game[key])
            for key in meta_keys if game.get(key) is not None
        }

        performers = {}
        for side in ("away", "home"):
            team = game.get(f"{side}_team")
            players = [
                player for player in game.get(side, [])
                if any(player.get(stat) not in (None, 0, 0.0)
                       for stat in ("pass_yards", "rush_yards", "rec_yards"))
            ]
            players.sort(
                key=lambda player: (
                    sum(float(player.get(stat) or 0)
                        for stat in ("pass_yards", "rush_yards", "rec_yards")),
                    player.get("player_name") or "",
                ),
                reverse=True,
            )
            performers[team] = [
                {
                    "player_id": player.get("player_id"),
                    "player": player.get("player_name"),
                    "position": player.get("position"),
                    **_nonzero({stat: player.get(stat) for stat in _GAME_LINE_STATS}),
                }
                for player in players[:5]
            ]

        payload = {
            "game": meta,
            "quarter_scores": game.get("quarter_scores", [])[:5],
            "top_performers": performers,
        }
        ctx.record("get_game_detail", args, [meta])
        return _dumps(payload)

    @beta_tool
    def get_player_game_log(player_id: str, season: int) -> str:
        """A player's compact regular-season game log for one season. Use for
        a specific week or best/worst-game question; each row retains game
        context and only nonzero verified stat columns.

        Args:
            player_id: The player's id from resolve_entity.
            season: The season year, e.g. 2020.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        if not _valid_player_id(player_id):
            ctx.record("get_player_game_log", {"player_id": player_id, "season": season})
            return _PLAYER_ID_MSG
        s = int(season)
        args = {"player_id": player_id, "season": s}
        try:
            profile = _player_profile(player_id)
        except HTTPException:
            ctx.record("get_player_game_log", args)
            return "No player found for that id."
        games = [
            game for game in profile.get("games", [])
            if int(game.get("season", -1)) == s and game.get("game_type") == "REG"
        ][:_RESULT_LIMIT]
        rows = []
        for game in games:
            context = {
                key: game.get(key)
                for key in ("game_id", "week", "game_type", "gameday", "team",
                            "opponent", "location", "result")
                if game.get(key) is not None
            }
            rows.append({**context, **_nonzero({col: game.get(col) for col in STAT_COLS})})
        payload = {
            "player": {"id": player_id, "name": profile.get("player_name"),
                       "position": profile.get("position")},
            "season": s,
            "games": rows,
        }
        ctx.record("get_player_game_log", args, rows)
        return _dumps(payload) if rows else f"No regular-season games for that player in {s}."

    @beta_tool
    def get_player_career(player_id: str) -> str:
        """Regular-season totals for every season in a player's profile plus
        one career-total line. Use for career totals, number of seasons, and
        best-season questions; all sums reconcile with the profile game rows.

        Args:
            player_id: The player's id from resolve_entity.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        if not _valid_player_id(player_id):
            ctx.record("get_player_career", {"player_id": player_id})
            return _PLAYER_ID_MSG
        args = {"player_id": player_id}
        try:
            profile = _player_profile(player_id)
        except HTTPException:
            ctx.record("get_player_career", args)
            return "No player found for that id."
        regular = [game for game in profile.get("games", []) if game.get("game_type") == "REG"]
        seasons = []
        for season in sorted({int(game["season"]) for game in regular}):
            games = [game for game in regular if int(game["season"]) == season]
            seasons.append({"season": season, "games_played": len(games),
                            **_season_stat_line(games)})
        all_seasons = seasons
        seasons = all_seasons[-_RESULT_LIMIT:]
        career_total = {
            "seasons": len(all_seasons),
            "first_season": all_seasons[0]["season"] if all_seasons else None,
            "last_season": all_seasons[-1]["season"] if all_seasons else None,
            "games_played": len(regular),
            **_season_stat_line(regular),
        }
        career_total = {key: value for key, value in career_total.items() if value is not None}
        payload = {
            "player": {"id": player_id, "name": profile.get("player_name"),
                       "position": profile.get("position")},
            "seasons": seasons,
            "career_total": career_total,
        }
        if len(all_seasons) > _RESULT_LIMIT:
            payload["note"] = (f"Showing the most recent {_RESULT_LIMIT} of "
                               f"{len(all_seasons)} seasons.")
        ctx.record("get_player_career", args, seasons)
        return _dumps(payload) if seasons else "No regular-season career games for that player."

    @beta_tool
    def get_team_overview(team: str, season: int) -> str:
        """A compact regular-season team record/standing summary. For the
        current season it also includes the latest injury report and current
        offensive depth-chart starters at QB/RB/WR/TE.

        Args:
            team: Team abbreviation from resolve_entity, e.g. "BAL".
            season: The season year, e.g. 2023.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        tm = team.upper().strip()
        s = int(season)
        args = {"team": tm, "season": s}
        try:
            profile = _team_query(tm, s)
        except HTTPException:
            ctx.record("get_team_overview", args)
            return f"No team profile found for {tm} in {s}."

        standing = None
        standing_division = None
        for division in _standings_query(season=s):
            standing = next(
                (row for row in division.get("teams", []) if row.get("team") == tm),
                None,
            )
            if standing:
                standing_division = division.get("division")
                break
        if standing:
            record = f'{standing["w"]}-{standing["l"]}'
            if standing.get("t"):
                record += f'-{standing["t"]}'
            standing_line = {
                "division": standing_division,
                "pct": standing.get("pct"),
                "points_for": standing.get("pf"),
                "points_against": standing.get("pa"),
                "division_record": standing.get("div"),
                "streak": standing.get("strk"),
            }
            regular_games = int(standing["w"] + standing["l"] + standing.get("t", 0))
        else:
            game_types = {
                game.get("game_id"): game.get("game_type")
                for group in _schedule_query(season=s)
                for game in group.get("games", [])
            }
            games = [
                {**game, "game_type": game_types.get(game.get("game_id"))}
                for game in profile.get("games", [])
            ]
            record = _regular_record(games, tm)
            standing_line = {}
            regular_games = None
        payload = {"team": tm, "season": s, "record": record}
        if regular_games is not None:
            payload["regular_season_games"] = regular_games
        if standing_line:
            payload["standing"] = standing_line

        if s == CURRENT_SEASON:
            injuries = _team_injuries_query(tm, s, None)
            payload["current_injuries"] = [
                {key: row.get(source) for key, source in (
                    ("name", "full_name"), ("position", "position"),
                    ("injury", "report_primary_injury"),
                    ("status", "report_status"), ("practice_status", "practice_status"),
                    ("week", "week"),
                ) if row.get(source) is not None}
                for row in injuries[:20]
            ]
            depth = _team_depth_query(tm, s, None)
            payload["offensive_starters"] = [
                {"name": row.get("full_name"), "position": row.get("depth_position")}
                for row in depth
                if row.get("formation") == "Offense"
                and row.get("depth_position") in {"QB", "RB", "WR", "TE"}
                and str(row.get("depth_team")) == "1"
            ][:5]
        payload = {key: value for key, value in payload.items() if value not in (None, [], {})}
        ctx.record("get_team_overview", args, [payload])
        return _dumps(payload)

    @beta_tool
    def get_power_rankings(season: int, week: int = 0) -> str:
        """This platform's EPA-based power rankings, not a media poll. week 0
        returns the latest available model run for the season.

        Args:
            season: The season year, e.g. 2023.
            week: Ranking week, or 0 for the latest available.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        s = int(season)
        wk = max(0, int(week))
        args = {"season": s, "week": wk}
        rows = _power_rankings_query(season=s, week=wk or None)
        out = [
            {key: row.get(key) for key in
             ("rank", "team", "record", "net_epa_play", "movement")
             if row.get(key) is not None}
            for row in rows[:_RESULT_LIMIT]
        ]
        payload = {"season": s, "week": wk or "latest", "rankings": out}
        if len(rows) > _RESULT_LIMIT:
            payload["note"] = f"Showing the top {_RESULT_LIMIT} of {len(rows)} teams."
        ctx.record("get_power_rankings", args, out)
        return _dumps(payload) if out else f"No power rankings available for {s}."

    @beta_tool
    def get_player_overview(player_id: str, season: int) -> str:
        """A player's regular-season stat line for one season PLUS advanced
        context: Next Gen Stats (CPOE, time-to-throw, separation — 2016+),
        red-zone and 3rd-down splits, snap counts, awards, and draft/combine.
        Use this for "how did X do in YEAR" or any question about a player's
        overall season, efficiency, usage, or accolades.

        Args:
            player_id: The player's id from resolve_entity.
            season: The season year, e.g. 2023.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        if not _valid_player_id(player_id):
            ctx.record("get_player_overview", {"player_id": player_id, "season": season})
            return _PLAYER_ID_MSG
        try:
            prof = _player_profile(player_id)
        except HTTPException:
            ctx.record("get_player_overview", {"player_id": player_id, "season": season})
            return "No player found for that id."

        s = int(season)
        games = [g for g in prof.get("games", [])
                 if int(g.get("season", -1)) == s and g.get("game_type") == "REG"]
        totals = {c: round(sum(g.get(c) or 0 for g in games), 2) for c in STAT_COLS}

        overview = {
            "player": {"id": player_id, "name": prof.get("player_name"),
                       "position": prof.get("position"), "team": prof.get("team")},
            "season": s,
            "games_played": len(games),
            "season_totals": _nonzero(totals),
            "ngs": prof.get("ngs", {}).get(s),
            "situational": prof.get("situational", {}).get(s),
            "snaps": prof.get("snap_totals", {}).get(s),
            "advanced": prof.get("adv_stats", {}).get(s),
            "kicking": prof.get("kicking", {}).get(s),
            "awards": prof.get("awards", []),
            "draft": prof.get("draft"),
        }
        overview = {k: v for k, v in overview.items() if v not in (None, {}, [])}
        ctx.record("get_player_overview", {"player_id": player_id, "season": s}, [overview])
        return _dumps(overview)

    @beta_tool
    def get_player_splits(player_id: str, season: int, category: str, dimension: str) -> str:
        """The platform's centerpiece: a player's stat line conditioned on ONE
        situational dimension at a time. Use for questions like "under
        pressure", "on 3rd down", "in the red zone", "on deep passes",
        "vs play-action", "by opponent".

        category is one of: passing, rushing, receiving, defense.
        dimension must be a valid name for that category (call get_metadata if
        unsure). Coverage: FTN dimensions (play_action, blitz, box_count) are
        2022+; defensive splits are counting stats only.

        Args:
            player_id: The player's id from resolve_entity.
            season: The season year, e.g. 2023.
            category: passing | rushing | receiving | defense.
            dimension: The situational dimension, e.g. "pressure" or "down".
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        cat = category.lower().strip()
        dim = dimension.lower().strip()
        s = int(season)
        args = {"player_id": player_id, "season": s, "category": cat, "dimension": dim}

        if not _valid_player_id(player_id):
            ctx.record("get_player_splits", args)
            return _PLAYER_ID_MSG

        if cat not in _DIMENSIONS:
            ctx.record("get_player_splits", args)
            return f"Invalid category '{category}'. Use one of: {', '.join(_DIMENSIONS)}."

        if cat == "defense":
            all_rows = def_splits_builder.read_or_materialize(player_id)
            rows = [r for r in all_rows if int(r.get("season")) == s and r.get("split_dim") == dim]
        else:
            all_rows = splits_builder.read_or_materialize(player_id)
            rows = [r for r in all_rows
                    if int(r.get("season")) == s and r.get("category") == cat and r.get("split_dim") == dim]

        ctx.record("get_player_splits", args, rows)
        if not rows:
            return (f"No {cat} splits by '{dim}' for that player in {s}. "
                    f"Valid {cat} dimensions: {', '.join(_DIMENSIONS[cat])}. "
                    f"Note FTN dimensions (play_action, blitz, box_count) start in 2022.")
        return _dumps(rows)

    @beta_tool
    def get_team_splits(team: str, season: int, side: str, dimension: str) -> str:
        """A team's offense or defense rate profile (EPA/play, success%, pass
        rate, yards/play, explosive%) conditioned on one situation. Use for
        "how is the 49ers defense in the red zone" or "Bills offense on 3rd down".

        Args:
            team: Team abbreviation from resolve_entity, e.g. "KC".
            season: The season year, e.g. 2023.
            side: offense | defense.
            dimension: One of down, quarter, game_script, field_zone, home_away,
                roof, surface, no_huddle, game_state, opponent, opp_division.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        sd = side.lower().strip()
        dim = dimension.lower().strip()
        s = int(season)
        args = {"team": team, "season": s, "side": sd, "dimension": dim}
        if sd not in ("offense", "defense"):
            ctx.record("get_team_splits", args)
            return "Invalid side. Use 'offense' or 'defense'."
        all_rows = team_splits_builder.read_or_materialize(team.upper(), s)
        rows = [r for r in all_rows if r.get("side") == sd and r.get("split_dim") == dim]
        ctx.record("get_team_splits", args, rows)
        if not rows:
            return (f"No {sd} splits by '{dim}' for {team} in {s}. "
                    f"Valid dimensions: {', '.join(_TEAM_DIMS)}.")
        return _dumps(rows)

    @beta_tool
    def get_leaders(stat: str, season: int, limit: int = 10) -> str:
        """League leaders for a single counting/EPA stat in a season. Use for
        "who led the league in X" questions.

        Args:
            stat: A leader stat, e.g. "rush_yards", "pass_tds", "pass_epa",
                "receptions", "sacks". Call get_metadata for the full list.
            season: The season year, e.g. 2022.
            limit: How many leaders to return (default 10, max 25).
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        st = stat.lower().strip()
        s = int(season)
        n = max(1, min(int(limit), 25))
        args = {"stat": st, "season": s, "limit": n}
        if st not in _LEADER_STATS:
            ctx.record("get_leaders", args)
            return f"Invalid stat '{stat}'. Valid stats: {', '.join(_LEADER_STATS)}."
        rows = _leaders_query(season=s)
        ranked = sorted((r for r in rows if r.get(st) is not None),
                        key=lambda r: r.get(st) or 0, reverse=True)[:n]
        out = [{"rank": i + 1, "player": r.get("player_name"), "team": r.get("team"),
                "position": r.get("position"), st: r.get(st),
                "games_played": r.get("games_played")} for i, r in enumerate(ranked)]
        ctx.record("get_leaders", args, out)
        return _dumps(out) if out else f"No leaders found for {st} in {s}."

    @beta_tool
    def get_standings(season: int) -> str:
        """Final/current division standings for a season (records, points for/
        against, division record, streak). Use for "how did the AFC North
        finish" or "who won the NFC East".

        Args:
            season: The season year, e.g. 2021.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        s = int(season)
        divisions = _standings_query(season=s)
        out = []
        for div in divisions:
            for t in div.get("teams", []):
                out.append({"division": div["division"], "team": t["team"],
                            "w": t["w"], "l": t["l"], "t": t["t"], "pct": t["pct"],
                            "pf": t["pf"], "pa": t["pa"], "div": t["div"], "streak": t["strk"]})
        ctx.record("get_standings", {"season": s}, out)
        return _dumps(out) if out else f"No standings for {s}."

    @beta_tool
    def get_comparables(player_id: str) -> str:
        """Players statistically most similar to a given player, by career
        per-game / per-attempt efficiency (cosine similarity within position
        group). Use for "who is similar to X" or "comparable players".

        Args:
            player_id: The player's id from resolve_entity.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        if not _valid_player_id(player_id):
            ctx.record("get_comparables", {"player_id": player_id})
            return _PLAYER_ID_MSG
        rows = comparables_builder.read_or_materialize(player_id, 8)
        out = [{"player": r.get("player_name"), "position": r.get("position"),
                "team": r.get("team"), "similarity_pct": r.get("similarity"),
                "seasons": f'{r.get("first_season")}-{r.get("last_season")}'} for r in rows]
        ctx.record("get_comparables", {"player_id": player_id}, out)
        return _dumps(out) if out else "No comparables available for that player."

    @beta_tool
    def get_metadata() -> str:
        """The exact vocabulary this platform supports: seasons available,
        split categories/dimensions/values and their plain-English synonyms,
        rankable and derived stats, team abbreviations, and coverage limits.
        Call this when unsure whether a stat/dimension/value/season exists.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        meta = {
            "seasons": {"first": FIRST_SEASON, "current": CURRENT_SEASON},
            "split_categories": list(_DIMENSIONS),
            "split_dimensions": _DIMENSIONS,
            "team_split_dimensions": _TEAM_DIMS,
            "split_value_vocabulary": _SPLIT_VOCABULARY,
            "leader_stats": _LEADER_STATS,
            "derived_metrics": _DERIVED_METRICS,
            "teams": TEAM_NAMES,
            "other_data": [
                "query_plays", "find_games", "get_game_detail", "get_player_game_log",
                "get_player_career", "get_team_overview", "get_power_rankings",
            ],
            "coverage_limits": _COVERAGE,
        }
        ctx.record("get_metadata", {})
        return _dumps(meta)

    @beta_tool
    def report_data_gap(topic: str, detail: str) -> str:
        """Record that the platform is MISSING data needed to fully answer the
        question. Call this (once) whenever you had to decline, fall back to a
        proxy, or note that a requested stat / split / season isn't available —
        so the team can review the gaps and decide what to add. Still give the
        user your best answer with what IS available; this is a side note, not a
        replacement for answering.

        Args:
            topic: Short label for the missing data, e.g. "two-minute drill splits".
            detail: One sentence on what the user wanted and why it's unavailable.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        _log_gap(ctx.question, topic.strip(), detail.strip())
        ctx.record("report_data_gap", {"topic": topic.strip()})
        return "Logged the data gap for later review."

    return [resolve_entity, query_plays, find_games, get_game_detail, get_player_game_log,
            get_player_career, get_team_overview, get_power_rankings,
            get_player_overview, get_player_splits, get_team_splits, get_leaders,
            get_standings, get_comparables, get_metadata, report_data_gap]


# ── System prompt ─────────────────────────────────────────────────────────────
# The vocabulary is embedded here (not just behind get_metadata) so routing is
# reliable on the first try — the biggest lever on answer accuracy. It also
# enlarges the cacheable prefix.

def _dim_lines() -> str:
    return "\n".join(f"  - {cat}: {', '.join(dims)}" for cat, dims in _DIMENSIONS.items())


def _vocab_lines() -> str:
    lines = []
    for dim, spec in _SPLIT_VOCABULARY.items():
        if spec.get("prompt"):
            detail = spec["prompt"]
        else:
            parts = []
            for value in spec["values"]:
                synonyms = spec["synonyms"].get(value, [])
                hint = f" [{'/'.join(synonyms)}]" if synonyms else ""
                parts.append(f"{value}{hint}")
            detail = "; ".join(parts)
        lines.append(f"- {dim}: {detail}")
    return "\n".join(lines)


SYSTEM_PROMPT = f"""You are the NFL stats assistant for this analytics platform. \
You answer questions about NFL players and teams ONLY by calling the provided \
tools, which read the platform's verified statistics database. You never invent, \
estimate, or recall numbers from memory — every figure in your answer must come \
from a tool result in this conversation.

DATA YOU CAN REACH (seasons {FIRST_SEASON}-{CURRENT_SEASON}):
- resolve_entity: name -> id. ALWAYS call first for any player/team named.
- query_plays: server-defined play-by-play measures over granular structured filters.
- find_games: regular-season and playoff schedules/results; returns game_ids when filtered.
- get_game_detail: one trimmed game result with quarter scores and top performers.
- get_player_game_log: one player's regular-season game rows for a season.
- get_player_career: one player's per-season and career regular-season totals.
- get_team_overview: team record/standing; current injuries and skill-position starters.
- get_power_rankings: this platform's EPA model rankings, not a media poll.
- get_player_overview: a player's season line + NGS, red-zone/3rd-down, snaps, awards, draft.
- get_player_splits: a player's stat line conditioned on ONE situation (the centerpiece).
- get_team_splits: a team's offense/defense rate profile by situation.
- get_leaders: league leaders for a stat in a season.
- get_standings: division standings for a season.
- get_comparables: statistically similar players.
- get_metadata: exact dimensions, values/synonyms, stats, and coverage limits.

SPLIT DIMENSIONS (the `dimension` argument to get_player_splits):
{_dim_lines()}
Team split dimensions: {', '.join(_TEAM_DIMS)}

SPLIT VALUE VOCABULARY (exact labels precede brackets; brackets are normal phrasing):
{_vocab_lines()}

GRANULAR PLAY QUERIES:
- Use query_plays ONLY for situational cuts the shaped tools cannot answer. For \
standard season or career totals, ALWAYS prefer the existing stat tools because \
their official reconciled numbers can differ slightly from play-by-play sums.
- When answering from query_plays, explicitly say the result is play-by-play derived.

DERIVED METRICS:
- You MAY compute completion %, yards/attempt, yards/carry, catch rate, and TD \
rate only from counting-stat inputs fetched in this conversation. Show the \
inputs and arithmetic (for example, "389/579 = 67.2%").
- Never derive a metric requiring an input you did not fetch. Compute passer \
rating only after fetching attempts, completions, pass yards, pass TDs, and \
interceptions (all four formula components); otherwise decline.

CONVERSATION CONTEXT:
- Prior turns are context for resolving references and follow-ups. Every number \
in a NEW answer must come from a tool call made for that answer; never reuse a \
figure from an earlier assistant message.

COVERAGE LIMITS — respect these; if asked for data outside them, say it is not \
available rather than guessing:
- Game schedules/results include playoffs (WC/DIV/CON/SB); player career, \
season, game-log, and team stat tools are regular-season only.
- NGS tracking stats (CPOE, time-to-throw, separation, etc.): 2016 onward.
- FTN charting dimensions (play_action, blitz, box_count): 2022 onward.
- Snap counts: ~2012 onward.
- Defensive splits are counting stats only (no coverage/assignment data).
- Awards reflect a curated set of real, voted postseason awards — report what \
the data shows; never infer an award from a stat line.

HOW TO ANSWER:
1. Resolve any player/team name to an id with resolve_entity first.
2. Call the most specific tool. If unsure of an exact dimension/stat name or a \
season's availability, call get_metadata.
3. Answer concisely in plain language, leading with the key number(s). Name the \
player/team, season, and the situation you pulled.
4. If a tool returns no rows, say the data is not available for that combination \
— do not fabricate.
5. Politely decline questions that are not about NFL stats this platform covers.
6. Whenever you had to decline, approximate, or note that a requested stat / \
split / season isn't available, call report_data_gap ONCE (after giving your \
best answer) to record what was missing — this is how we find what to add next.
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def run_ask(question: str, history: list[dict] | None = None) -> dict:
    """Run one question plus bounded text history through the tool-calling
    loop and return {answer, data, tools_used}. Raises anthropic.* errors on
    auth / upstream failures (the route maps them to HTTP statuses)."""
    ctx = _Ctx()
    ctx.question = question
    tools = _build_tools(ctx)
    client = _get_client()

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=2048,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=tools,
        messages=_conversation_messages(question, history),
    )

    answer = ""
    for message in runner:
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        if text:
            answer = text  # the final assistant turn's text wins

    return {"answer": answer, "data": ctx.data,
            "tools_used": [{"tool": c["tool"], "args": c["args"]} for c in ctx.calls]}


def run_ask_stream(question: str, history: list[dict] | None = None):
    """Streaming sibling of run_ask, for the SSE endpoint. Yields event dicts:

        {"type": "tool",  "tool": <name>}                    a tool call has begun
        {"type": "delta", "text": <chunk>}                   answer text, token by token
        {"type": "done",  "answer", "data", "tools_used"}    final authoritative payload

    It runs the tool-calling loop **manually** (instead of the SDK tool runner)
    so it can emit progress between tool calls and stream the final answer's
    tokens — the part that makes the UI feel like watching the agent work. The
    tools, system prompt, and grounding are identical to run_ask: each tool's
    JSON schema comes from the same `@beta_tool` definitions (`.to_dict()`), and
    execution goes through the same `.func`, so behaviour can't drift between the
    two paths. Anthropic errors propagate to the route, which maps them to an
    `error` event.
    """
    ctx = _Ctx()
    ctx.question = question
    tools = _build_tools(ctx)
    by_name = {t.name: t for t in tools}
    tool_params = [t.to_dict() for t in tools]
    client = _get_client()

    messages = _conversation_messages(question, history)
    answer = ""

    while True:
        with client.messages.stream(
            model=MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=tool_params,
            messages=messages,
        ) as stream:
            for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "tool_use":
                    yield {"type": "tool", "tool": event.content_block.name}
                elif event.type == "content_block_delta" and getattr(event.delta, "type", None) == "text_delta":
                    yield {"type": "delta", "text": event.delta.text}
            final = stream.get_final_message()

        if final.stop_reason != "tool_use":
            answer = "".join(b.text for b in final.content if b.type == "text").strip()
            break

        # Feed the requested tools' results back, then loop for the next turn.
        messages.append({"role": "assistant", "content": final.content})
        results = []
        for b in final.content:
            if b.type == "tool_use":
                t = by_name.get(b.name)
                try:
                    out = t.func(**(b.input or {})) if t else f"Unknown tool '{b.name}'."
                except Exception as e:  # a tool bug must not kill the stream
                    out = f"Tool error: {e}"
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        messages.append({"role": "user", "content": results})

    yield {"type": "done", "answer": answer, "data": ctx.data,
           "tools_used": [{"tool": c["tool"], "args": c["args"]} for c in ctx.calls]}
