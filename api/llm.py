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
from routers.leaders import get_leaders as _leaders_query
from routers.leaders import get_standings as _standings_query
from routers.leaders import search as _search_query
from routers.players import get_player as _player_profile

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

# Numeric columns the leaders table exposes (the season totals you can rank by).
_LEADER_STATS = [
    "attempts", "completions", "pass_yards", "pass_tds", "interceptions_thrown",
    "sacks_taken", "carries", "rush_yards", "rush_tds", "targets", "receptions",
    "rec_yards", "rec_tds", "yac", "air_yards", "pass_epa", "rush_epa", "rec_epa",
    "solo_tackles", "assist_tackles", "tackles_for_loss", "sacks", "qb_hits",
    "def_interceptions", "pass_breakups", "forced_fumbles", "fumble_recoveries",
    "fg_att", "fg_made", "xp_att", "xp_made", "punts", "punt_yards",
]

_COVERAGE = {
    "seasons": f"{FIRST_SEASON}-{CURRENT_SEASON} (regular season)",
    "ngs_tracking_stats_from": 2016,      # CPOE, time-to-throw, separation, ...
    "ftn_charting_dims_from": 2022,       # play_action, blitz, box_count
    "snap_counts_from": 2012,
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
        rows = comparables_builder.read_or_materialize(player_id, 8)
        out = [{"player": r.get("player_name"), "position": r.get("position"),
                "team": r.get("team"), "similarity_pct": r.get("similarity"),
                "seasons": f'{r.get("first_season")}-{r.get("last_season")}'} for r in rows]
        ctx.record("get_comparables", {"player_id": player_id}, out)
        return _dumps(out) if out else "No comparables available for that player."

    @beta_tool
    def get_metadata() -> str:
        """The exact vocabulary this platform supports: seasons available,
        split categories and their valid dimensions, the rankable leader stats,
        team abbreviations, and data coverage limits. Call this when you are
        unsure whether a stat/dimension/season exists before answering.
        """
        if ctx.over_budget():
            return _BUDGET_MSG
        meta = {
            "seasons": {"first": FIRST_SEASON, "current": CURRENT_SEASON},
            "split_categories": list(_DIMENSIONS),
            "split_dimensions": _DIMENSIONS,
            "team_split_dimensions": _TEAM_DIMS,
            "leader_stats": _LEADER_STATS,
            "teams": TEAM_NAMES,
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

    return [resolve_entity, get_player_overview, get_player_splits, get_team_splits,
            get_leaders, get_standings, get_comparables, get_metadata, report_data_gap]


# ── System prompt ─────────────────────────────────────────────────────────────
# The vocabulary is embedded here (not just behind get_metadata) so routing is
# reliable on the first try — the biggest lever on answer accuracy. It also
# enlarges the cacheable prefix.

def _dim_lines() -> str:
    return "\n".join(f"  - {cat}: {', '.join(dims)}" for cat, dims in _DIMENSIONS.items())


SYSTEM_PROMPT = f"""You are the NFL stats assistant for this analytics platform. \
You answer questions about NFL players and teams ONLY by calling the provided \
tools, which read the platform's verified statistics database. You never invent, \
estimate, or recall numbers from memory — every figure in your answer must come \
from a tool result in this conversation.

DATA YOU CAN REACH (seasons {FIRST_SEASON}-{CURRENT_SEASON}, regular season):
- resolve_entity: name -> id. ALWAYS call first for any player/team named.
- get_player_overview: a player's season line + NGS, red-zone/3rd-down, snaps, awards, draft.
- get_player_splits: a player's stat line conditioned on ONE situation (the centerpiece).
- get_team_splits: a team's offense/defense rate profile by situation.
- get_leaders: league leaders for a stat in a season.
- get_standings: division standings for a season.
- get_comparables: statistically similar players.
- get_metadata: the exact valid categories/dimensions/stats and coverage limits.

SPLIT DIMENSIONS (the `dimension` argument to get_player_splits):
{_dim_lines()}
Team split dimensions: {', '.join(_TEAM_DIMS)}

COVERAGE LIMITS — respect these; if asked for data outside them, say it is not \
available rather than guessing:
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

def run_ask(question: str) -> dict:
    """Run one natural-language question through the tool-calling loop and
    return {answer, data, tools_used}. Raises anthropic.* errors on auth /
    upstream failures (the route maps them to HTTP statuses)."""
    ctx = _Ctx()
    ctx.question = question
    tools = _build_tools(ctx)
    client = _get_client()

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=2048,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=tools,
        messages=[{"role": "user", "content": question}],
    )

    answer = ""
    for message in runner:
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        if text:
            answer = text  # the final assistant turn's text wins

    return {"answer": answer, "data": ctx.data,
            "tools_used": [{"tool": c["tool"], "args": c["args"]} for c in ctx.calls]}


def run_ask_stream(question: str):
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

    messages: list[dict] = [{"role": "user", "content": question}]
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
