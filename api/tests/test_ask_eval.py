"""Gold-set evaluation for the natural-language /ask assistant.

This is the headline deliverable: a measured accuracy number, not a vibe. It
runs 110 plain-English questions through the real model + tools and checks two
things per question:

  (a) routing  — did the model call the expected tool with the expected args?
  (b) answer   — does the number/name it reported match the DB ground truth?

Each case is tagged with capability categories (splits-def, era, ambiguity,
phrasing, ...) and results are reported as a per-category matrix, so weak
areas stay visible instead of averaging away. Every run also performs a
mechanical provenance audit: numerals in each answer are checked against the
tool results fetched for that question (see _unsupported_figures).

Ground truth is computed *live* from the same reconciled tools (the "oracle"),
so the eval can't rot when the underlying data updates — it always checks
against whatever the DB currently holds.

It is opt-in and costs LLM tokens, so it only runs when RUN_ASK_EVAL is set AND
the real DB is present; it skips cleanly otherwise (so plain `pytest` and CI
stay green and free). Run it deliberately:

    cd api
    RUN_ASK_EVAL=1 pytest tests/test_ask_eval.py -s        # (bash)
    $env:RUN_ASK_EVAL=1; pytest tests/test_ask_eval.py -s  # (PowerShell)

The `-s` flag shows the per-question table and the final accuracy line.
"""
import json
import os
import re
import time
from datetime import datetime, timezone

import pytest

_DB = os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")
_OUT = os.path.join(os.path.dirname(__file__), "out", "ask_eval_runs.jsonl")
_HARNESS_VERSION = 3

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_ASK_EVAL") or not os.path.exists(_DB),
    reason="billed eval — set RUN_ASK_EVAL=1 and have the real nfl.duckdb to run it",
)


# ── Oracle: ground truth from the same reconciled tools ───────────────────────

def _oracle():
    """Direct tool access for computing ground truth. The per-request tool-call
    budget is a guardrail for the *model* loop, not for us — disable it here so
    the oracle can answer all gold questions without tripping it."""
    import llm
    ctx = llm._Ctx()
    ctx.over_budget = lambda: False
    return {t.name: t.func for t in llm._build_tools(ctx)}


def _pid(fns, name, pos=None):
    """First matching player id, optionally filtered by position — required
    for names shared by multiple players (the DB's 2026 rookie class added a
    second Justin Jefferson), where result order is not guaranteed."""
    rows = json.loads(fns["resolve_entity"](name=name))
    return next(x["id"] for x in rows if x["type"] == "player"
                and (pos is None or x.get("position") == pos))


def _split_val(fns, name, season, cat, dim, value, field):
    rows = json.loads(fns["get_player_splits"](
        player_id=_pid(fns, name), season=season, category=cat, dimension=dim))
    return next(r for r in rows if r["split_value"] == value)[field]


def _overview_val(fns, name, season, key):
    ov = json.loads(fns["get_player_overview"](player_id=_pid(fns, name), season=season))
    return ov["season_totals"][key]


def _award_seasons(fns, name, award, probe_season=2023):
    """Seasons in which the player won the named award, from the overview's
    career-wide awards list (the probe season only anchors the overview call)."""
    ov = json.loads(fns["get_player_overview"](player_id=_pid(fns, name), season=probe_season))
    return [int(row["season"]) for row in ov.get("awards", [])
            if str(row.get("award", "")).lower() == award.lower()]


def _def_split_val(fns, name, season, dim, value, field):
    rows = json.loads(fns["get_player_splits"](
        player_id=_pid(fns, name), season=season, category="defense", dimension=dim))
    return next(r for r in rows if r["split_value"] == value)[field]


def _ambig_val(fns, name, season, col):
    """Ground truth for an ambiguous player name: of everyone sharing the
    name, exactly one has this stat in this season (verified at build time) —
    the same way a human reader disambiguates the question."""
    rows = json.loads(fns["resolve_entity"](name=name))
    values = []
    for row in rows:
        if row.get("type") != "player":
            continue
        try:
            ov = json.loads(fns["get_player_overview"](player_id=row["id"], season=season))
        except (ValueError, TypeError):
            continue
        value = ov.get("season_totals", {}).get(col)
        if value:
            values.append(value)
    assert len(values) == 1, f"not uniquely resolvable: {name} {season} {col} -> {values}"
    return values[0]


def _draft_info(fns, name, probe_season=2023, pos=None):
    ov = json.loads(fns["get_player_overview"](
        player_id=_pid(fns, name, pos=pos), season=probe_season))
    return ov["draft"]


def _leader_top(fns, stat, season):
    return json.loads(fns["get_leaders"](stat=stat, season=season, limit=1))[0]["player"]


def _team_split_val(fns, team, season, side, dim, value, field):
    rows = json.loads(fns["get_team_splits"](team=team, season=season, side=side, dimension=dim))
    return next(r for r in rows if r["split_value"] == value)[field]


def _comp_top(fns, name, n=3, pos=None):
    rows = json.loads(fns["get_comparables"](player_id=_pid(fns, name, pos=pos)))
    return [r["player"] for r in rows[:n]]


def _standings_record(fns, season, team):
    rows = json.loads(fns["get_standings"](season=season))
    r = next(x for x in rows if x["team"] == team)
    return f"{r['w']}-{r['l']}"


def _find_game(fns, season, *, team="", week=0, away=None, home=None, game_type=None):
    payload = json.loads(fns["find_games"](season=season, team=team, week=week))
    return next(
        game for game in payload["games"]
        if (away is None or game["away_team"] == away)
        and (home is None or game["home_team"] == home)
        and (game_type is None or game["game_type"] == game_type)
    )


def _game_log(fns, name, season):
    return json.loads(fns["get_player_game_log"](
        player_id=_pid(fns, name), season=season))["games"]


def _career_val(fns, name, key):
    payload = json.loads(fns["get_player_career"](player_id=_pid(fns, name)))
    return payload["career_total"][key]


def _team_overview_record(fns, team, season):
    payload = json.loads(fns["get_team_overview"](team=team, season=season))
    return payload["record"]


def _power_rank(fns, team, season):
    payload = json.loads(fns["get_power_rankings"](season=season, week=0))
    return next(row["rank"] for row in payload["rankings"] if row["team"] == team)


def _game_coaches(fns, game_id):
    payload = json.loads(fns["get_game_detail"](game_id=game_id))
    return payload["game"]["away_coach"], payload["game"]["home_coach"]


def _winner_options(fns, season, game_type):
    from config import TEAM_NAMES

    game = _find_game(fns, season, game_type=game_type)
    winner = game["away_team"] if game["away_score"] > game["home_score"] else game["home_team"]
    full_name = TEAM_NAMES[winner]
    return [winner, full_name, full_name.split()[-1]]


def _score_in(answer, game):
    away, home = int(game["away_score"]), int(game["home_score"])
    return text_in(answer, [f"{away}-{home}", f"{away} to {home}",
                            f"{home}-{away}", f"{home} to {away}"])


def _query_play_payload(fns, **kwargs):
    return json.loads(fns["query_plays"](**kwargs))


def _query_play_value(fns, key, **kwargs):
    return _query_play_payload(fns, **kwargs)["rows"][0][key]


def _query_play_top_group(fns, group_key, **kwargs):
    rows = _query_play_payload(fns, group_by=group_key, **kwargs)["rows"]
    return max(rows, key=lambda row: row["plays"])[group_key]


# ── Graders ───────────────────────────────────────────────────────────────────

_DASH_TRANSLATION = str.maketrans({"–": "-", "—": "-", "−": "-"})


def _normalize_answer(answer):
    return answer.translate(_DASH_TRANSLATION)


def num_in(answer, value):
    """An integer value appears in the answer as a standalone number (commas
    tolerated). Boundary-checked so a small value cannot ride along inside a
    season year — "3" must not pass just because the answer says "2023"."""
    target = str(int(round(float(value))))
    text = _normalize_answer(answer).replace(",", "")
    # The model sometimes echoes a stored float verbatim ("27.0 tackles"), so
    # the trailing-.0 form is as correct as the bare integer.
    return re.search(rf"(?<![\d.]){target}(?:\.0)?(?!\.?\d)", text) is not None


def stat_in(answer, value):
    """num_in for stats that can be legitimately fractional (sacks come in
    halves): an integer value grades like num_in; 22.5 must match "22.5"."""
    v = float(value)
    if v.is_integer():
        return num_in(answer, v)
    text = _normalize_answer(answer).replace(",", "")
    return re.search(rf"(?<![\d.]){re.escape(str(v))}(?!\d)", text) is not None


def text_in(answer, options):
    a = _normalize_answer(answer).lower()
    return any(o.lower() in a for o in options)


def record_in(answer, record):
    """Accept a W-L record or an equivalent wins/losses sentence."""
    if text_in(answer, [record]):
        return True
    match = re.fullmatch(r"(\d+)-(\d+)", record)
    if not match:
        return False
    wins, losses = match.groups()
    normalized = _normalize_answer(answer).lower()
    count_phrase = re.search(
        rf"\b{wins}\s+wins?\s*(?:,\s*)?(?:and\s+)?{losses}\s+loss(?:es)?\b",
        normalized,
    )
    verb_phrase = re.search(
        rf"\bwon\s+{wins}\b[\s\S]*?\blost\s+{losses}\b",
        normalized,
    )
    return bool(count_phrase or verb_phrase)


def _lastname(name):
    parts = [p for p in re.split(r"[.\s]+", name.strip()) if p]
    return parts[-1] if parts else name


def name_in(answer, names):
    """Match a player by surname. The leaders/defensive data abbreviates first
    names ("N.Bosa") while the model writes them out ("Nick Bosa"), so comparing
    on the last-name token is the fair check."""
    a = answer.lower()
    if isinstance(names, str):
        names = [names]
    return any(_lastname(n).lower() in a for n in names)


def pct_in(answer, value):
    """A success-rate percentage (stored 0-100); match on the one-decimal or
    whole-number form the model is likely to print (e.g. 44.9 -> "44.9%").
    Boundary-checked like num_in so "4.9" cannot match inside "44.9"."""
    v = float(value)
    text = _normalize_answer(answer).replace(",", "")
    return any(
        re.search(rf"(?<![\d.]){re.escape(form)}(?!\.?\d)", text)
        for form in (f"{round(v, 1)}", f"{round(v)}")
    )


_NEGATION_PHRASES = ["never", "has not", "hasn't", "did not", "didn't",
                     "not won", "no mvp", "none"]


def award_polarity_in(answer, seasons):
    """Grade a "has X ever won <award>?" answer with polarity, not topic words.

    `seasons` is the oracle's list of winning seasons. If the player HAS won,
    the answer must affirm (no negation phrase) and carry either a winning
    season year or an explicit affirmation. If the player has NOT won, the
    answer must negate. A bare mention of the award passes neither branch.
    """
    a = _normalize_answer(answer).lower()
    negated = any(p in a for p in _NEGATION_PHRASES)
    if not seasons:
        return negated
    affirmed = ("yes" in a or "won" in a
                or any(num_in(answer, s) for s in seasons))
    return affirmed and not negated


def declines_offtopic(answer):
    """An off-topic question was refused: the answer states its NFL/football
    scope AND contains an actual refusal, not just an apology or topic word."""
    a = answer.lower()
    scoped = any(t in a for t in ["nfl", "football"])
    refused = any(t in a for t in [
        "can't", "cannot", "unable", "don't", "do not", "outside",
        "only answer", "only help", "not something", "beyond",
    ])
    return scoped and refused


def down_in(answer, value):
    options = {
        1: ["first down", "1st down"],
        2: ["second down", "2nd down"],
        3: ["third down", "3rd down"],
        4: ["fourth down", "4th down"],
    }
    return text_in(answer, options[int(value)])


def _leader_tops(fns, stat, season):
    """Every player tied at the top value — with a stat tie (e.g. four players
    at 6 INTs), naming any of them is a correct 'who led the league' answer."""
    rows = json.loads(fns["get_leaders"](stat=stat, season=season, limit=25))
    if not rows:
        return []
    top = rows[0][stat]
    return [r["player"] for r in rows if r[stat] == top]


def _leader_second_ties(fns, stat, season):
    rows = json.loads(fns["get_leaders"](stat=stat, season=season, limit=25))
    if len(rows) < 2:
        return []
    second_value = rows[1][stat]
    return [row["player"] for row in rows if row[stat] == second_value]


# ── The gold set ──────────────────────────────────────────────────────────────
# Each: question, expected tool (or alternate tools), expected arg subset, and
# a grader that computes truth from the oracle and checks the model's answer.

GOLD = [
    # ── player splits (the centerpiece) ──
    {"q": "How many pass attempts did Josh Allen have under pressure in 2023?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pressure", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Josh Allen", 2023, "passing", "pressure", "pressured", "att"))},

    {"q": "How many passing yards did Josh Allen have from a clean pocket in 2023?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pressure", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Josh Allen", 2023, "passing", "pressure", "clean", "yards"))},

    {"q": "How many receiving yards did Tyreek Hill get on deep targets in 2023?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "receiving", "dimension": "target_depth", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Tyreek Hill", 2023, "receiving", "target_depth", "deep", "yards"))},

    {"q": "How did Christian McCaffrey run on first down in 2023 — how many carries?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "down", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Christian McCaffrey", 2023, "rushing", "down", "1", "att"))},

    # ── player overview (season line + advanced) ──
    {"q": "How many rushing touchdowns did Josh Allen have in 2023?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Josh Allen", 2023, "rush_tds"))},

    {"q": "How many passing yards did Patrick Mahomes throw for in 2022?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {"season": 2022},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Patrick Mahomes", 2022, "pass_yards"))},

    {"q": "Has Josh Allen ever won MVP?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {},
     "grade": lambda a, f: award_polarity_in(a, _award_seasons(f, "Josh Allen", "MVP"))},

    # ── leaders ──
    {"q": "Who led the NFL in rushing yards in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "rush_yards", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "rush_yards", 2022))},

    {"q": "Who threw the most passing touchdowns in 2023?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "pass_tds", "season": 2023},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "pass_tds", 2023))},

    {"q": "Who had the most receptions in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "receptions", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "receptions", 2022))},

    {"q": "Who led the league in sacks in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "sacks", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "sacks", 2022))},

    # ── standings ──
    {"q": "What was the Cincinnati Bengals' record in 2021?",
     "tags": ["teams"],
     "tools": ["get_standings", "get_team_overview"], "args": {"season": 2021},
     "grade": lambda a, f: record_in(a, _standings_record(f, 2021, "CIN"))},

    {"q": "What was the Detroit Lions' record in 2023?",
     "tags": ["teams"],
     "tools": ["get_standings", "get_team_overview"], "args": {"season": 2023},
     "grade": lambda a, f: record_in(a, _standings_record(f, 2023, "DET"))},

    # ── team splits ──
    {"q": "What was the Chiefs defense success rate in the red zone in 2023?",
     "tags": ["teams"],
     "tool": "get_team_splits", "args": {"side": "defense", "dimension": "field_zone", "season": 2023},
     "grade": lambda a, f: pct_in(a, _team_split_val(f, "KC", 2023, "defense", "field_zone", "red_zone", "success_pct"))},

    # ── comparables ──
    {"q": "Which players are most statistically similar to Justin Jefferson?",
     "tags": ["lookup"],
     "tool": "get_comparables", "args": {},
     "grade": lambda a, f: name_in(a, _comp_top(f, "Justin Jefferson", pos="WR"))},

    {"q": "Who are some comparable players to Derrick Henry?",
     "tags": ["lookup"],
     "tool": "get_comparables", "args": {},
     "grade": lambda a, f: name_in(a, _comp_top(f, "Derrick Henry"))},

    # ── coverage limits respected (don't fabricate) ──
    {"q": "What was Aaron Rodgers' play-action passing EPA in 2015?",
     "tags": ["coverage-honesty"],
     "tool": None,  # FTN charting starts 2022 — the model should decline, not invent
     "grade": lambda a, f: text_in(a, ["2022", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    {"q": "What was Peyton Manning's completion percentage above expectation in 2004?",
     "tags": ["coverage-honesty"],
     "tool": None,  # NGS starts 2016
     "grade": lambda a, f: text_in(a, ["2016", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    # ── metadata / scope ──
    {"q": "What seasons of data do you have?",
     "tags": ["coverage-honesty"],
     "tool": "get_metadata", "args": {},
     "grade": lambda a, f: num_in(a, 1999)},

    {"q": "Can you recommend a good pizza place near me?",
     "tags": ["coverage-honesty"],
     "tool": None,  # off-topic — should decline with an explicit scope statement
     "grade": lambda a, f: declines_offtopic(a)},

    # ── expanded set (→ 40 total), built only from values confirmed in the DB ──
    # more player splits
    {"q": "How many passing yards did Joe Burrow have under pressure in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pressure", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Joe Burrow", 2022, "passing", "pressure", "pressured", "yards"))},

    {"q": "How many carries did Christian McCaffrey have on third down in 2023?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "down", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Christian McCaffrey", 2023, "rushing", "down", "3", "att"))},

    {"q": "How many receiving yards did Tyreek Hill have on short targets in 2023?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "receiving", "dimension": "target_depth", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Tyreek Hill", 2023, "receiving", "target_depth", "short", "yards"))},

    {"q": "How many pass attempts did Patrick Mahomes have from a clean pocket in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pressure", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Patrick Mahomes", 2022, "passing", "pressure", "clean", "att"))},

    {"q": "How many rushing yards did Saquon Barkley have on first down in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "down", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Saquon Barkley", 2022, "rushing", "down", "1", "yards"))},

    # more overview (season totals — pick clearly non-zero stats; _nonzero drops 0s)
    {"q": "How many receptions did Justin Jefferson have in 2022?",
     "tags": ["lookup", "ambiguity"],  # the 2026 rookie class added a second Justin Jefferson
     "tool": "get_player_overview", "args": {"season": 2022},
     "grade": lambda a, f: num_in(a, _ambig_val(f, "Justin Jefferson", 2022, "receptions"))},

    {"q": "How many rushing yards did Derrick Henry have in 2020?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {"season": 2020},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Derrick Henry", 2020, "rush_yards"))},

    {"q": "How many passing touchdowns did Patrick Mahomes throw in 2022?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {"season": 2022},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Patrick Mahomes", 2022, "pass_tds"))},

    {"q": "How many receiving yards did Tyreek Hill have in 2023?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Tyreek Hill", 2023, "rec_yards"))},

    {"q": "How many interceptions did Josh Allen throw in 2023?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Josh Allen", 2023, "interceptions_thrown"))},

    {"q": "How many rushing touchdowns did Christian McCaffrey score in 2023?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Christian McCaffrey", 2023, "rush_tds"))},

    # more leaders
    {"q": "Who led the NFL in receiving yards in 2023?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "rec_yards", "season": 2023},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "rec_yards", 2023))},

    {"q": "Who had the most rushing touchdowns in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "rush_tds", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "rush_tds", 2022))},

    {"q": "Who had the most interceptions on defense in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "def_interceptions", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "def_interceptions", 2022))},

    {"q": "Who threw for the most passing yards in 2021?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "pass_yards", "season": 2021},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "pass_yards", 2021))},

    # more standings
    {"q": "What was the Philadelphia Eagles' record in 2022?",
     "tags": ["teams"],
     "tools": ["get_standings", "get_team_overview"], "args": {"season": 2022},
     "grade": lambda a, f: record_in(a, _standings_record(f, 2022, "PHI"))},

    {"q": "What was the San Francisco 49ers' record in 2023?",
     "tags": ["teams"],
     "tools": ["get_standings", "get_team_overview"], "args": {"season": 2023},
     "grade": lambda a, f: record_in(a, _standings_record(f, 2023, "SF"))},

    # more team splits
    {"q": "What was the Eagles offense success rate in the red zone in 2022?",
     "tags": ["teams"],
     "tool": "get_team_splits", "args": {"side": "offense", "dimension": "field_zone", "season": 2022},
     "grade": lambda a, f: pct_in(a, _team_split_val(f, "PHI", 2022, "offense", "field_zone", "red_zone", "success_pct"))},

    # more comparables
    {"q": "Which players are most similar to Patrick Mahomes?",
     "tags": ["lookup"],
     "tool": "get_comparables", "args": {},
     "grade": lambda a, f: name_in(a, _comp_top(f, "Patrick Mahomes"))},

    # another coverage-limit decline (blitz is FTN charting, 2022+)
    {"q": "What blitz rate did Tom Brady face in 2008?",
     "tags": ["coverage-honesty"],
     "tool": None,
     "grade": lambda a, f: text_in(a, ["2022", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    # schedules, games, careers, teams, and platform power rankings
    {"q": "What was the score of the Bills-Chiefs game in week 14 of 2023?",
     "tags": ["games"],
     "tool": "find_games", "args": {"season": 2023, "week": 14},
     "grade": lambda a, f: _score_in(
         a, _find_game(f, 2023, week=14, away="BUF", home="KC"))},

    {"q": "Who won the Super Bowl after the 2022 season?",
     "tags": ["games"],
     "tool": "find_games", "args": {"season": 2022},
     "grade": lambda a, f: text_in(a, _winner_options(f, 2022, "SB"))},

    {"q": "Who coached the teams in the Super Bowl after the 2022 season?",
     "tags": ["games"],
     "tool": "get_game_detail", "args": {"game_id": "2022_22_KC_PHI"},
     "grade": lambda a, f: all(
         coach.lower() in a.lower() for coach in _game_coaches(f, "2022_22_KC_PHI"))},

    {"q": "How many rushing yards did Derrick Henry have in week 8 of 2020?",
     "tags": ["lookup", "games"],
     "tool": "get_player_game_log", "args": {"season": 2020},
     "grade": lambda a, f: num_in(
         a, next(game for game in _game_log(f, "Derrick Henry", 2020)
                 if game["week"] == 8)["rush_yards"])},

    {"q": "How many career passing touchdowns does Aaron Rodgers have?",
     "tags": ["career"],
     "tool": "get_player_career", "args": {},
     "grade": lambda a, f: num_in(a, _career_val(f, "Aaron Rodgers", "pass_tds"))},

    {"q": "What was Derrick Henry's best rushing game of 2020?",
     "tags": ["lookup", "games"],
     "tool": "get_player_game_log", "args": {"season": 2020},
     "grade": lambda a, f: num_in(
         a, max(game.get("rush_yards", 0) for game in _game_log(f, "Derrick Henry", 2020)))},

    {"q": "What was the Ravens' record in 2023?",
     "tags": ["teams"],
     "tools": ["get_standings", "get_team_overview"], "args": {"season": 2023},
     "grade": lambda a, f: record_in(a, _team_overview_record(f, "BAL", 2023))},

    {"q": "Where did the Chiefs rank in the 2023 power rankings?",
     "tags": ["rankings"],
     "tool": "get_power_rankings", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _power_rank(f, "KC", 2023))},

    {"q": "How many receiving yards did Jerry Rice have in 1989?",
     "tags": ["coverage-honesty", "era"],
     "tool": None,
     "grade": lambda a, f: text_in(a, ["1999", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    # granular semantic play queries
    {"q": "How many rushing touchdowns did the Eagles score in the red zone in 2022?",
     "tags": ["plays"],
     "tool": "query_plays",
     "args": {"season": 2022, "offense": "PHI", "play": "run", "red_zone": True},
     "grade": lambda a, f: num_in(a, _query_play_value(
         f, "touchdowns", season=2022, offense="PHI", play="run", red_zone=True))},

    {"q": "What was Patrick Mahomes' success rate on deep passes on first down in 2022?",
     "tags": ["plays"],
     "tool": "query_plays",
     "args": {"season": 2022, "play": "pass", "pass_length": "deep", "down": 1},
     "grade": lambda a, f: pct_in(a, 100 * _query_play_value(
         f, "success_rate", season=2022, play="pass", pass_length="deep", down=1,
         passer_id=_pid(f, "Patrick Mahomes")))},

    {"q": "Which down did the Ravens run on most in 2023?",
     "tags": ["plays"],
     "tool": "query_plays",
     "args": {"season": 2023, "offense": "BAL", "play": "run", "group_by": "down"},
     "grade": lambda a, f: down_in(a, _query_play_top_group(
         f, "down", season=2023, offense="BAL", play="run"))},

    {"q": "What about on first down?",
     "tags": ["plays", "followup"],
     "history": [
         {"role": "user", "content": "How many rushing touchdowns did the Ravens score in the red zone in 2023?"},
         {"role": "assistant", "content": "I checked Baltimore's 2023 regular-season red-zone rushing plays."},
     ],
     "tool": "query_plays",
     "args": {"season": 2023, "offense": "BAL", "play": "run",
              "red_zone": True, "down": 1},
     "grade": lambda a, f: num_in(a, _query_play_value(
         f, "touchdowns", season=2023, offense="BAL", play="run",
         red_zone=True, down=1))},

    # multi-turn follow-ups (history is text context, not replayed tool state)
    {"q": "What about 2022?",
     "tags": ["followup", "lookup"],
     "history": [
         {"role": "user", "content": "How many passing yards did Patrick Mahomes have in 2023?"},
         {"role": "assistant", "content": "Patrick Mahomes threw for 4,183 yards in 2023."},
     ],
     "tool": "get_player_overview", "args": {"season": 2022},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Patrick Mahomes", 2022, "pass_yards"))},

    {"q": "And against light boxes?",
     "tags": ["followup", "splits-off"],
     "history": [
         {"role": "user", "content": "How many rushing yards did CMC have against stacked boxes in 2023?"},
         {"role": "assistant", "content": "I pulled Christian McCaffrey's 2023 stacked-box rushing split."},
     ],
     "tool": "get_player_splits",
     "args": {"category": "rushing", "dimension": "box_count", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(
         f, "Christian McCaffrey", 2023, "rushing", "box_count", "light_box", "yards"))},

    {"q": "Who was second?",
     "tags": ["followup", "leaders"],
     "history": [
         {"role": "user", "content": "Who led the league in sacks in 2022?"},
         {"role": "assistant", "content": "Nick Bosa led the NFL in sacks in 2022."},
     ],
     "tool": "get_leaders", "args": {"stat": "sacks", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_second_ties(f, "sacks", 2022))},

    # ── defensive splits (previously zero coverage) ──
    {"q": "How many sacks did T.J. Watt have on passing plays in 2021?",
     "tags": ["splits-def"],
     "tool": "get_player_splits", "args": {"category": "defense", "dimension": "vs_play", "season": 2021},
     "grade": lambda a, f: stat_in(a, _def_split_val(f, "T.J. Watt", 2021, "vs_play", "vs_pass", "sacks"))},

    {"q": "How many tackles did Micah Parsons have against the run in 2022?",
     "tags": ["splits-def"],
     "tool": "get_player_splits", "args": {"category": "defense", "dimension": "vs_play", "season": 2022},
     "grade": lambda a, f: stat_in(a, _def_split_val(f, "Micah Parsons", 2022, "vs_play", "vs_run", "tackles"))},

    {"q": "How many tackles did Bobby Wagner have on first down in 2022?",
     "tags": ["splits-def"],
     "tool": "get_player_splits", "args": {"category": "defense", "dimension": "down", "season": 2022},
     "grade": lambda a, f: stat_in(a, _def_split_val(f, "Bobby Wagner", 2022, "down", "1", "tackles"))},

    {"q": "How many tackles did Roquan Smith have on third down in 2023?",
     "tags": ["splits-def"],
     "tool": "get_player_splits", "args": {"category": "defense", "dimension": "down", "season": 2023},
     "grade": lambda a, f: stat_in(a, _def_split_val(f, "Roquan Smith", 2023, "down", "3", "tackles"))},

    {"q": "How many QB hits did Maxx Crosby have on passing plays in 2023?",
     "tags": ["splits-def"],
     "tool": "get_player_splits", "args": {"category": "defense", "dimension": "vs_play", "season": 2023},
     "grade": lambda a, f: stat_in(a, _def_split_val(f, "Maxx Crosby", 2023, "vs_play", "vs_pass", "qb_hits"))},

    {"q": "How many tackles did Fred Warner make while the 49ers were leading in 2023?",
     "tags": ["splits-def"],
     "tool": "get_player_splits", "args": {"category": "defense", "dimension": "game_script", "season": 2023},
     "grade": lambda a, f: stat_in(a, _def_split_val(f, "Fred Warner", 2023, "game_script", "leading", "tackles"))},

    # ── offense splits: previously untested dimensions ──
    {"q": "How many passing yards did Justin Herbert have when trailing in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "game_script", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Justin Herbert", 2022, "passing", "game_script", "trailing", "yards"))},

    {"q": "How many receiving yards did Davante Adams have against the Chiefs in 2021?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "receiving", "dimension": "opponent", "season": 2021},
     "grade": lambda a, f: num_in(a, _split_val(f, "Davante Adams", 2021, "receiving", "opponent", "KC", "yards"))},

    {"q": "How many rushing yards did Nick Chubb have against the AFC North in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "opp_division", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Nick Chubb", 2022, "rushing", "opp_division", "AFC North", "yards"))},

    {"q": "How many touchdown passes did Matthew Stafford throw in domes in 2021?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "roof", "season": 2021},
     "grade": lambda a, f: num_in(a, _split_val(f, "Matthew Stafford", 2021, "passing", "roof", "dome", "td"))},

    {"q": "How many rushing yards did Derrick Henry have on grass in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "surface", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Derrick Henry", 2022, "rushing", "surface", "grass", "yards"))},

    {"q": "How many pass attempts did Tom Brady have from shotgun in 2021?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "shotgun", "season": 2021},
     "grade": lambda a, f: num_in(a, _split_val(f, "Tom Brady", 2021, "passing", "shotgun", "shotgun", "att"))},

    {"q": "How many passing yards did Josh Allen have in the no-huddle in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "no_huddle", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Josh Allen", 2022, "passing", "no_huddle", "no_huddle", "yards"))},

    {"q": "How many receiving yards did CeeDee Lamb have in garbage time in 2023?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "receiving", "dimension": "game_state", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "CeeDee Lamb", 2023, "receiving", "game_state", "garbage", "yards"))},

    {"q": "How many carries did Josh Jacobs have around the end in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "run_gap", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Josh Jacobs", 2022, "rushing", "run_gap", "end", "att"))},

    {"q": "How many passing yards did Kirk Cousins have throwing left in 2022?",
     "tags": ["splits-off"],
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pass_location", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Kirk Cousins", 2022, "passing", "pass_location", "left", "yards"))},

    # ── historical eras and relocated franchises ──
    {"q": "How many passing touchdowns did Peyton Manning throw in 2004?",
     "tags": ["era", "lookup"],
     "tool": "get_player_overview", "args": {"season": 2004},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Peyton Manning", 2004, "pass_tds"))},

    {"q": "How many rushing touchdowns did LaDainian Tomlinson score in 2006?",
     "tags": ["era", "lookup"],
     "tool": "get_player_overview", "args": {"season": 2006},
     "grade": lambda a, f: num_in(a, _overview_val(f, "LaDainian Tomlinson", 2006, "rush_tds"))},

    {"q": "How many receiving yards did Randy Moss have in 1999?",
     "tags": ["era", "lookup"],
     "tool": "get_player_overview", "args": {"season": 1999},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Randy Moss", 1999, "rec_yards"))},

    {"q": "How many passing yards did Brett Favre throw for in 2007?",
     "tags": ["era", "lookup"],
     "tool": "get_player_overview", "args": {"season": 2007},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Brett Favre", 2007, "pass_yards"))},

    {"q": "How many receptions did Marvin Harrison have in 2002?",
     "tags": ["era", "lookup"],
     "tool": "get_player_overview", "args": {"season": 2002},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Marvin Harrison", 2002, "receptions"))},

    {"q": "Who led the NFL in rushing yards in 2002?",
     "tags": ["era", "leaders"],
     "tool": "get_leaders", "args": {"stat": "rush_yards", "season": 2002},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "rush_yards", 2002))},

    {"q": "What was the Oakland Raiders' record in 2002?",
     "tags": ["era", "teams"],
     "tools": ["get_standings", "get_team_overview"], "args": {"season": 2002},
     "grade": lambda a, f: record_in(a, _standings_record(f, 2002, "OAK"))},

    {"q": "What was the San Diego Chargers' record in 2005?",
     "tags": ["era", "teams"],
     "tools": ["get_standings", "get_team_overview"], "args": {"season": 2005},
     "grade": lambda a, f: record_in(a, _standings_record(f, 2005, "SD"))},

    # ── ambiguous names (multiple players share the name; context decides) ──
    {"q": "How many passing yards did Josh Allen have in 2022?",
     "tags": ["ambiguity", "lookup"],
     "tool": "get_player_overview", "args": {"season": 2022},
     "grade": lambda a, f: num_in(a, _ambig_val(f, "Josh Allen", 2022, "pass_yards"))},

    {"q": "How many rushing yards did Adrian Peterson have in 2012?",
     "tags": ["ambiguity", "lookup"],
     # per-season career totals reconcile with the overview, so both routes count
     "tools": ["get_player_overview", "get_player_career"], "args": {},
     "grade": lambda a, f: num_in(a, _ambig_val(f, "Adrian Peterson", 2012, "rush_yards"))},

    {"q": "How many receiving yards did Steve Smith have in 2005?",
     "tags": ["ambiguity", "lookup"],
     "tool": "get_player_overview", "args": {"season": 2005},
     "grade": lambda a, f: num_in(a, _ambig_val(f, "Steve Smith", 2005, "rec_yards"))},

    {"q": "How many receptions did Michael Thomas have in 2019?",
     "tags": ["ambiguity", "lookup"],
     "tool": "get_player_overview", "args": {"season": 2019},
     "grade": lambda a, f: num_in(a, _ambig_val(f, "Michael Thomas", 2019, "receptions"))},

    # ── leader stats never exercised before ──
    {"q": "Who made the most field goals in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "fg_made", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "fg_made", 2022))},

    {"q": "Which punter had the most punts in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "punts", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "punts", 2022))},

    {"q": "Who had the most QB hits in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "qb_hits", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "qb_hits", 2022))},

    {"q": "Who led the league in tackles for loss in 2022?",
     "tags": ["leaders"],
     "tool": "get_leaders", "args": {"stat": "tackles_for_loss", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "tackles_for_loss", 2022))},

    # ── awards (polarity-graded) and draft lookups ──
    {"q": "Has Myles Garrett ever won Defensive Player of the Year?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {},
     "grade": lambda a, f: award_polarity_in(a, _award_seasons(f, "Myles Garrett", "DPOY"))},

    {"q": "Did Ja'Marr Chase win Offensive Rookie of the Year?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {},
     "grade": lambda a, f: award_polarity_in(a, _award_seasons(f, "Ja'Marr Chase", "OROY"))},

    {"q": "Has Derrick Henry ever won MVP?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {},
     "grade": lambda a, f: award_polarity_in(a, _award_seasons(f, "Derrick Henry", "MVP"))},

    {"q": "Has Lamar Jackson won multiple MVP awards?",
     "tags": ["lookup"],
     "tool": "get_player_overview", "args": {},
     "grade": lambda a, f: (award_polarity_in(a, _award_seasons(f, "Lamar Jackson", "MVP"))
                           and all(num_in(a, s) for s in _award_seasons(f, "Lamar Jackson", "MVP")))},

    {"q": "When was the Vikings' Justin Jefferson drafted?",
     "tags": ["lookup", "ambiguity"],
     "tool": "get_player_overview", "args": {},
     "grade": lambda a, f: (num_in(a, _draft_info(f, "Justin Jefferson", pos="WR")["season"])
                           and text_in(a, ["first round", "1st round", "round 1",
                                           "first-round", "1st-round"]))},

    {"q": "What college did the Vikings' Justin Jefferson play at?",
     "tags": ["lookup", "ambiguity"],
     "tool": "get_player_overview", "args": {},
     "grade": lambda a, f: text_in(a, [_draft_info(f, "Justin Jefferson", pos="WR")["college"]])},

    # ── coverage honesty: decline cleanly AND log the gap ──
    {"q": "What was Antonio Brown's average separation in 2014?",
     "tags": ["coverage-honesty"],
     "tool": None, "must_call": "report_data_gap",  # NGS starts 2016
     "grade": lambda a, f: text_in(a, ["2016", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    {"q": "How many snaps did Ray Lewis play in 2005?",
     "tags": ["coverage-honesty"],
     "tool": None, "must_call": "report_data_gap",  # snap counts start ~2012
     "grade": lambda a, f: text_in(a, ["2012", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    {"q": "How many passing yards did Tom Brady have against the blitz in 2010?",
     "tags": ["coverage-honesty"],
     "tool": None,  # FTN charting starts 2022
     "grade": lambda a, f: text_in(a, ["2022", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    {"q": "How many rushing yards did Barry Sanders have in 1995?",
     "tags": ["coverage-honesty", "era"],
     "tool": None,  # dataset starts 1999
     "grade": lambda a, f: text_in(a, ["1999", "not available", "isn't available",
                                       "no data", "don't have", "do not have",
                                       "unavailable", "can't find", "couldn't find",
                                       "no player"])},
]


# ── Phrasing robustness: paraphrase clones of existing cases ─────────────────
# Same grader, same expected routing — only the wording changes. Casual, terse,
# nicknamed, and misspelled forms measure the "you must ask it the right way"
# brittleness directly.

def _phrasing_variant(question, new_q):
    base = next(case for case in GOLD if case["q"] == question)
    clone = dict(base)
    clone["q"] = new_q
    clone["tags"] = sorted(set(base.get("tags", [])) | {"phrasing"})
    clone.pop("history", None)
    return clone


GOLD += [
    _phrasing_variant("How many carries did Christian McCaffrey have on third down in 2023?",
                      "cmc carries on 3rd down 2023?"),
    _phrasing_variant("How many carries did Christian McCaffrey have on third down in 2023?",
                      "how many times did McCaffrey run the ball on third down in 2023"),
    _phrasing_variant("How many passing yards did Patrick Mahomes throw for in 2022?",
                      "Pat Mahomes passing yds 2022"),
    _phrasing_variant("How many passing yards did Patrick Mahomes throw for in 2022?",
                      "how many yards did mahomes throw for in 2022??"),
    _phrasing_variant("Who led the NFL in rushing yards in 2022?",
                      "who lead the league in rushing in 2022"),
    _phrasing_variant("Who led the NFL in rushing yards in 2022?",
                      "2022 rushing yards leader?"),
    _phrasing_variant("What was the Cincinnati Bengals' record in 2021?",
                      "bengals record 2021"),
    _phrasing_variant("What was the Cincinnati Bengals' record in 2021?",
                      "what did the bengals go in 2021"),
    _phrasing_variant("How many receiving yards did Tyreek Hill get on deep targets in 2023?",
                      "tyreek hill deep target yards 2023"),
    _phrasing_variant("How many receiving yards did Tyreek Hill get on deep targets in 2023?",
                      "how many yards did tyreek get on deep balls in 2023"),
    _phrasing_variant("Who led the league in sacks in 2022?",
                      "most sacks 2022?"),
    _phrasing_variant("Who led the league in sacks in 2022?",
                      "who got the most sacks in the 2022 season"),
]


# ── Provenance audit ─────────────────────────────────────────────────────────
# Every numeral the model prints should be traceable to a tool result from the
# same question. This is measured mechanically (no LLM judge) and REPORTED, not
# asserted: derived metrics the prompt allows (completion %, yards/attempt)
# legitimately produce figures absent from any single tool result, so flags are
# a review list, and the rate is the headline "hallucinated-figure" metric.

_NUMBER_RE = re.compile(r"\d+\.\d+|\.\d+|\d+")


def _unsupported_figures(answer, raw_results):
    """Numerals in the answer with no numeric source in any tool result.

    Comparison is numeric, not textual: tools serialize 36 as "36.0" and
    0.824 while answers print "36" and ".824", and rates stored as fractions
    are printed as percentages, so each corpus value also counts rounded to
    the answer's precision and scaled by 100. Whitelisted: years 1900-2030
    (data-range and season commentary) and integers up to 10 (ranks, downs,
    ordinals). "49ers" is stripped before extraction. The audit is a review
    list — the whitelist and x100 scaling are documented noise tradeoffs."""
    corpus = " ".join(raw_results).replace(",", "")
    corpus_values = {float(t) for t in _NUMBER_RE.findall(corpus)}
    text = _normalize_answer(answer).replace(",", "").replace("49ers", "")
    flagged, seen = [], set()
    for token in _NUMBER_RE.findall(text):
        if token in seen:
            continue
        seen.add(token)
        value = float(token)
        if value.is_integer() and (value <= 10 or 1900 <= value <= 2030):
            continue
        decimals = len(token.split(".")[1]) if "." in token else 0
        if any(round(v, decimals) == value or round(v * 100, decimals) == value
               for v in corpus_values):
            continue
        flagged.append(token)
    return flagged


# ── Helpers ───────────────────────────────────────────────────────────────────

def _args_match(actual: dict, expected: dict) -> bool:
    """Expected args are a subset; string compares are case-insensitive."""
    for k, v in expected.items():
        if k not in actual:
            return False
        av = actual[k]
        if isinstance(v, str) and isinstance(av, str):
            if av.lower() != v.lower():
                return False
        elif av != v:
            return False
    return True


# ── The eval ──────────────────────────────────────────────────────────────────

def test_ask_eval_accuracy():
    import anthropic
    from llm import MODEL, run_ask

    try:
        fns = _oracle()
        # Cheap probe so a missing/invalid credential skips instead of failing.
        run_ask("ping")
    except anthropic.AuthenticationError:
        pytest.skip("no Anthropic credentials (no API key and no logged-in profile)")

    total = len(GOLD)
    tool_hits = ans_hits = both_hits = 0
    rows = []
    cases = []
    by_tag: dict[str, dict] = {}

    for g in GOLD:
        started = time.perf_counter()
        res = run_ask(g["q"], history=g.get("history", []))
        latency = time.perf_counter() - started
        used, answer = res["tools_used"], res["answer"]
        usage = res.get("usage", {})

        expected_tools = g.get("tools")
        if expected_tools is None:
            expected_tools = [] if g.get("tool") is None else [g["tool"]]

        if not expected_tools:
            tool_ok = True  # decline questions: routing isn't asserted, only the answer
        else:
            tool_ok = any(
                call["tool"] in expected_tools and _args_match(call["args"], g["args"])
                for call in used
            )
        # A case may additionally require a side-effect tool (e.g. the model
        # must log a data gap when it declines) regardless of routing.
        must_call = g.get("must_call")
        if must_call and not any(call["tool"] == must_call for call in used):
            tool_ok = False

        try:
            ans_ok = bool(g["grade"](answer, fns))
        except Exception:
            ans_ok = False

        tool_hits += tool_ok
        ans_hits += ans_ok
        both_hits += tool_ok and ans_ok
        for tag in g.get("tags", ["untagged"]):
            bucket = by_tag.setdefault(
                tag, {"cases": 0, "tool_hits": 0, "answer_hits": 0, "passed": 0})
            bucket["cases"] += 1
            bucket["tool_hits"] += tool_ok
            bucket["answer_hits"] += ans_ok
            bucket["passed"] += tool_ok and ans_ok
        flagged = _unsupported_figures(answer, res.get("raw_results", []))
        rows.append((tool_ok, ans_ok, g["q"], answer.replace("\n", " ")[:90], used))
        case_input = sum(int(usage.get(key, 0) or 0) for key in (
            "uncached_input", "cache_creation_input", "cache_read_input"
        ))
        cases.append({
            "question": g["q"],
            "tags": g.get("tags", []),
            "tool_ok": tool_ok,
            "answer_ok": ans_ok,
            "unsupported_figures": flagged,
            "passed": bool(tool_ok and ans_ok),
            "answer": answer,
            "tools_used": used,
            "latency_seconds": round(latency, 4),
            "uncached_input_tokens": int(usage.get("uncached_input", 0) or 0),
            "cache_creation_input_tokens": int(usage.get("cache_creation_input", 0) or 0),
            "cache_read_input_tokens": int(usage.get("cache_read_input", 0) or 0),
            "input_tokens": case_input,
            "output_tokens": int(usage.get("output", 0) or 0),
            "total_tokens": case_input + int(usage.get("output", 0) or 0),
        })

    print("\n\n==================== /ask gold-set eval ====================")
    for tool_ok, ans_ok, q, ans, used in rows:
        mark = "OK" if (tool_ok and ans_ok) else ("~" if (tool_ok or ans_ok) else "X")
        print(f" {mark} [tool {'Y' if tool_ok else 'n'} | ans {'Y' if ans_ok else 'n'}] {q}")
        print(f"       -> {ans}")
        if not (tool_ok and ans_ok):
            if not used:
                print("       tool chain: (none)")
            for i, call in enumerate(used, 1):
                args = json.dumps(call.get("args", {}), sort_keys=True,
                                  ensure_ascii=True, separators=(",", ":"))
                print(f"       tool {i}: {call.get('tool')} {args}")
    print("------------------------------------------------------------")
    print(f" Tool routing accuracy : {tool_hits}/{total} = {tool_hits/total:.0%}")
    print(f" Answer accuracy       : {ans_hits}/{total} = {ans_hits/total:.0%}")
    print(f" Both correct          : {both_hits}/{total} = {both_hits/total:.0%}")
    print("------------------- capability report card -----------------")
    print(f" {'category':<18}{'cases':>6}{'tool':>7}{'answer':>8}{'both':>7}")
    for tag in sorted(by_tag):
        b = by_tag[tag]
        print(f" {tag:<18}{b['cases']:>6}"
              f"{b['tool_hits']:>7}{b['answer_hits']:>8}{b['passed']:>7}")
    audit_cases = [c for c in cases if c["unsupported_figures"]]
    print("---------------------- provenance audit --------------------")
    print(f" Answers with unsupported figures: {len(audit_cases)}/{total}")
    for c in audit_cases:
        print(f"   {c['question']}  ->  {', '.join(c['unsupported_figures'])}")
    total_latency = sum(case["latency_seconds"] for case in cases)
    total_tokens = sum(case["total_tokens"] for case in cases)
    print(f" Telemetry average     : {total_latency/total:.2f}s | "
          f"{total_tokens/total:,.0f} tokens/question")
    print("============================================================\n")

    input_tokens = sum(case["input_tokens"] for case in cases)
    output_tokens = sum(case["output_tokens"] for case in cases)
    summary = {
        "harness_version": _HARNESS_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": MODEL,
        "questions": total,
        "passed": both_hits,
        "accuracy": both_hits / total,
        "tool_hits": tool_hits,
        "tool_accuracy": tool_hits / total,
        "answer_hits": ans_hits,
        "answer_accuracy": ans_hits / total,
        "total_latency_seconds": round(total_latency, 4),
        "avg_latency_seconds": round(total_latency / total, 4),
        "uncached_input_tokens": sum(case["uncached_input_tokens"] for case in cases),
        "cache_creation_input_tokens": sum(
            case["cache_creation_input_tokens"] for case in cases
        ),
        "cache_read_input_tokens": sum(case["cache_read_input_tokens"] for case in cases),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "avg_tokens_per_question": round((input_tokens + output_tokens) / total, 2),
        "by_tag": by_tag,
        "unsupported_figure_cases": len(audit_cases),
        "cases": cases,
    }
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    with open(_OUT, "a", encoding="utf-8") as output:
        output.write(json.dumps(summary, ensure_ascii=True, separators=(",", ":")) + "\n")

    # A real but non-brittle gate. The printed numbers are the headline figure.
    assert ans_hits / total >= 0.7, f"answer accuracy {ans_hits/total:.0%} below 70% floor"
