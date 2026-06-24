"""Gold-set evaluation for the natural-language /ask assistant.

This is the headline deliverable: a measured accuracy number, not a vibe. It
runs ~20 plain-English questions through the real model + tools and checks two
things per question:

  (a) routing  — did the model call the expected tool with the expected args?
  (b) answer   — does the number/name it reported match the DB ground truth?

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

import pytest

_DB = os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")

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


def _pid(fns, name):
    rows = json.loads(fns["resolve_entity"](name=name))
    return next(x["id"] for x in rows if x["type"] == "player")


def _split_val(fns, name, season, cat, dim, value, field):
    rows = json.loads(fns["get_player_splits"](
        player_id=_pid(fns, name), season=season, category=cat, dimension=dim))
    return next(r for r in rows if r["split_value"] == value)[field]


def _overview_val(fns, name, season, key):
    ov = json.loads(fns["get_player_overview"](player_id=_pid(fns, name), season=season))
    return ov["season_totals"][key]


def _leader_top(fns, stat, season):
    return json.loads(fns["get_leaders"](stat=stat, season=season, limit=1))[0]["player"]


def _team_split_val(fns, team, season, side, dim, value, field):
    rows = json.loads(fns["get_team_splits"](team=team, season=season, side=side, dimension=dim))
    return next(r for r in rows if r["split_value"] == value)[field]


def _comp_top(fns, name, n=3):
    rows = json.loads(fns["get_comparables"](player_id=_pid(fns, name)))
    return [r["player"] for r in rows[:n]]


def _standings_record(fns, season, team):
    rows = json.loads(fns["get_standings"](season=season))
    r = next(x for x in rows if x["team"] == team)
    return f"{r['w']}-{r['l']}"


# ── Graders ───────────────────────────────────────────────────────────────────

def num_in(answer, value):
    """An integer value appears in the answer (commas tolerated)."""
    return str(int(round(float(value)))) in answer.replace(",", "")


def text_in(answer, options):
    a = answer.lower()
    return any(o.lower() in a for o in options)


def _lastname(name):
    import re
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
    whole-number form the model is likely to print (e.g. 44.9 -> "44.9%")."""
    v = float(value)
    return f"{round(v, 1)}" in answer or f"{round(v)}" in answer


def _leader_tops(fns, stat, season):
    """Every player tied at the top value — with a stat tie (e.g. four players
    at 6 INTs), naming any of them is a correct 'who led the league' answer."""
    rows = json.loads(fns["get_leaders"](stat=stat, season=season, limit=25))
    if not rows:
        return []
    top = rows[0][stat]
    return [r["player"] for r in rows if r[stat] == top]


# ── The gold set ──────────────────────────────────────────────────────────────
# Each: question, expected tool, expected (subset of) args, and a grader that
# computes truth from the oracle and checks the model's answer.

GOLD = [
    # ── player splits (the centerpiece) ──
    {"q": "How many pass attempts did Josh Allen have under pressure in 2023?",
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pressure", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Josh Allen", 2023, "passing", "pressure", "pressured", "att"))},

    {"q": "How many passing yards did Josh Allen have from a clean pocket in 2023?",
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pressure", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Josh Allen", 2023, "passing", "pressure", "clean", "yards"))},

    {"q": "How many receiving yards did Tyreek Hill get on deep targets in 2023?",
     "tool": "get_player_splits", "args": {"category": "receiving", "dimension": "target_depth", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Tyreek Hill", 2023, "receiving", "target_depth", "deep", "yards"))},

    {"q": "How did Christian McCaffrey run on first down in 2023 — how many carries?",
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "down", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Christian McCaffrey", 2023, "rushing", "down", "1", "att"))},

    # ── player overview (season line + advanced) ──
    {"q": "How many rushing touchdowns did Josh Allen have in 2023?",
     "tool": "get_player_overview", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Josh Allen", 2023, "rush_tds"))},

    {"q": "How many passing yards did Patrick Mahomes throw for in 2022?",
     "tool": "get_player_overview", "args": {"season": 2022},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Patrick Mahomes", 2022, "pass_yards"))},

    {"q": "Has Josh Allen ever won MVP?",
     "tool": "get_player_overview", "args": {},
     "grade": lambda a, f: text_in(a, ["mvp", "yes"])},

    # ── leaders ──
    {"q": "Who led the NFL in rushing yards in 2022?",
     "tool": "get_leaders", "args": {"stat": "rush_yards", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "rush_yards", 2022))},

    {"q": "Who threw the most passing touchdowns in 2023?",
     "tool": "get_leaders", "args": {"stat": "pass_tds", "season": 2023},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "pass_tds", 2023))},

    {"q": "Who had the most receptions in 2022?",
     "tool": "get_leaders", "args": {"stat": "receptions", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "receptions", 2022))},

    {"q": "Who led the league in sacks in 2022?",
     "tool": "get_leaders", "args": {"stat": "sacks", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "sacks", 2022))},

    # ── standings ──
    {"q": "What was the Cincinnati Bengals' record in 2021?",
     "tool": "get_standings", "args": {"season": 2021},
     "grade": lambda a, f: text_in(a, [_standings_record(f, 2021, "CIN")])},

    {"q": "What was the Detroit Lions' record in 2023?",
     "tool": "get_standings", "args": {"season": 2023},
     "grade": lambda a, f: text_in(a, [_standings_record(f, 2023, "DET")])},

    # ── team splits ──
    {"q": "What was the Chiefs defense success rate in the red zone in 2023?",
     "tool": "get_team_splits", "args": {"side": "defense", "dimension": "field_zone", "season": 2023},
     "grade": lambda a, f: pct_in(a, _team_split_val(f, "KC", 2023, "defense", "field_zone", "red_zone", "success_pct"))},

    # ── comparables ──
    {"q": "Which players are most statistically similar to Justin Jefferson?",
     "tool": "get_comparables", "args": {},
     "grade": lambda a, f: name_in(a, _comp_top(f, "Justin Jefferson"))},

    {"q": "Who are some comparable players to Derrick Henry?",
     "tool": "get_comparables", "args": {},
     "grade": lambda a, f: name_in(a, _comp_top(f, "Derrick Henry"))},

    # ── coverage limits respected (don't fabricate) ──
    {"q": "What was Aaron Rodgers' play-action passing EPA in 2015?",
     "tool": None,  # FTN charting starts 2022 — the model should decline, not invent
     "grade": lambda a, f: text_in(a, ["2022", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    {"q": "What was Peyton Manning's completion percentage above expectation in 2004?",
     "tool": None,  # NGS starts 2016
     "grade": lambda a, f: text_in(a, ["2016", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},

    # ── metadata / scope ──
    {"q": "What seasons of data do you have?",
     "tool": "get_metadata", "args": {},
     "grade": lambda a, f: num_in(a, 1999)},

    {"q": "Can you recommend a good pizza place near me?",
     "tool": None,  # off-topic — should decline
     "grade": lambda a, f: text_in(a, ["nfl", "football", "can't", "cannot", "only", "sorry", "stats"])},

    # ── expanded set (→ 40 total), built only from values confirmed in the DB ──
    # more player splits
    {"q": "How many passing yards did Joe Burrow have under pressure in 2022?",
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pressure", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Joe Burrow", 2022, "passing", "pressure", "pressured", "yards"))},

    {"q": "How many carries did Christian McCaffrey have on third down in 2023?",
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "down", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Christian McCaffrey", 2023, "rushing", "down", "3", "att"))},

    {"q": "How many receiving yards did Tyreek Hill have on short targets in 2023?",
     "tool": "get_player_splits", "args": {"category": "receiving", "dimension": "target_depth", "season": 2023},
     "grade": lambda a, f: num_in(a, _split_val(f, "Tyreek Hill", 2023, "receiving", "target_depth", "short", "yards"))},

    {"q": "How many pass attempts did Patrick Mahomes have from a clean pocket in 2022?",
     "tool": "get_player_splits", "args": {"category": "passing", "dimension": "pressure", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Patrick Mahomes", 2022, "passing", "pressure", "clean", "att"))},

    {"q": "How many rushing yards did Saquon Barkley have on first down in 2022?",
     "tool": "get_player_splits", "args": {"category": "rushing", "dimension": "down", "season": 2022},
     "grade": lambda a, f: num_in(a, _split_val(f, "Saquon Barkley", 2022, "rushing", "down", "1", "yards"))},

    # more overview (season totals — pick clearly non-zero stats; _nonzero drops 0s)
    {"q": "How many receptions did Justin Jefferson have in 2022?",
     "tool": "get_player_overview", "args": {"season": 2022},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Justin Jefferson", 2022, "receptions"))},

    {"q": "How many rushing yards did Derrick Henry have in 2020?",
     "tool": "get_player_overview", "args": {"season": 2020},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Derrick Henry", 2020, "rush_yards"))},

    {"q": "How many passing touchdowns did Patrick Mahomes throw in 2022?",
     "tool": "get_player_overview", "args": {"season": 2022},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Patrick Mahomes", 2022, "pass_tds"))},

    {"q": "How many receiving yards did Tyreek Hill have in 2023?",
     "tool": "get_player_overview", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Tyreek Hill", 2023, "rec_yards"))},

    {"q": "How many interceptions did Josh Allen throw in 2023?",
     "tool": "get_player_overview", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Josh Allen", 2023, "interceptions_thrown"))},

    {"q": "How many rushing touchdowns did Christian McCaffrey score in 2023?",
     "tool": "get_player_overview", "args": {"season": 2023},
     "grade": lambda a, f: num_in(a, _overview_val(f, "Christian McCaffrey", 2023, "rush_tds"))},

    # more leaders
    {"q": "Who led the NFL in receiving yards in 2023?",
     "tool": "get_leaders", "args": {"stat": "rec_yards", "season": 2023},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "rec_yards", 2023))},

    {"q": "Who had the most rushing touchdowns in 2022?",
     "tool": "get_leaders", "args": {"stat": "rush_tds", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "rush_tds", 2022))},

    {"q": "Who had the most interceptions on defense in 2022?",
     "tool": "get_leaders", "args": {"stat": "def_interceptions", "season": 2022},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "def_interceptions", 2022))},

    {"q": "Who threw for the most passing yards in 2021?",
     "tool": "get_leaders", "args": {"stat": "pass_yards", "season": 2021},
     "grade": lambda a, f: name_in(a, _leader_tops(f, "pass_yards", 2021))},

    # more standings
    {"q": "What was the Philadelphia Eagles' record in 2022?",
     "tool": "get_standings", "args": {"season": 2022},
     "grade": lambda a, f: text_in(a, [_standings_record(f, 2022, "PHI")])},

    {"q": "What was the San Francisco 49ers' record in 2023?",
     "tool": "get_standings", "args": {"season": 2023},
     "grade": lambda a, f: text_in(a, [_standings_record(f, 2023, "SF")])},

    # more team splits
    {"q": "What was the Eagles offense success rate in the red zone in 2022?",
     "tool": "get_team_splits", "args": {"side": "offense", "dimension": "field_zone", "season": 2022},
     "grade": lambda a, f: pct_in(a, _team_split_val(f, "PHI", 2022, "offense", "field_zone", "red_zone", "success_pct"))},

    # more comparables
    {"q": "Which players are most similar to Patrick Mahomes?",
     "tool": "get_comparables", "args": {},
     "grade": lambda a, f: name_in(a, _comp_top(f, "Patrick Mahomes"))},

    # another coverage-limit decline (blitz is FTN charting, 2022+)
    {"q": "What blitz rate did Tom Brady face in 2008?",
     "tool": None,
     "grade": lambda a, f: text_in(a, ["2022", "not available", "isn't available",
                                       "no data", "don't have", "do not have", "unavailable"])},
]


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
    from llm import run_ask

    try:
        fns = _oracle()
        # Cheap probe so a missing/invalid credential skips instead of failing.
        run_ask("ping")
    except anthropic.AuthenticationError:
        pytest.skip("no Anthropic credentials (no API key and no logged-in profile)")

    total = len(GOLD)
    tool_hits = ans_hits = both_hits = 0
    rows = []

    for g in GOLD:
        res = run_ask(g["q"])
        used, answer = res["tools_used"], res["answer"]

        if g["tool"] is None:
            tool_ok = True  # decline questions: routing isn't asserted, only the answer
        else:
            tool_ok = any(c["tool"] == g["tool"] and _args_match(c["args"], g["args"]) for c in used)

        try:
            ans_ok = bool(g["grade"](answer, fns))
        except Exception:
            ans_ok = False

        tool_hits += tool_ok
        ans_hits += ans_ok
        both_hits += tool_ok and ans_ok
        rows.append((tool_ok, ans_ok, g["q"], answer.replace("\n", " ")[:90]))

    print("\n\n==================== /ask gold-set eval ====================")
    for tool_ok, ans_ok, q, ans in rows:
        mark = "✓" if (tool_ok and ans_ok) else ("~" if (tool_ok or ans_ok) else "✗")
        print(f" {mark} [tool {'Y' if tool_ok else 'n'} | ans {'Y' if ans_ok else 'n'}] {q}")
        print(f"       → {ans}")
    print("------------------------------------------------------------")
    print(f" Tool routing accuracy : {tool_hits}/{total} = {tool_hits/total:.0%}")
    print(f" Answer accuracy       : {ans_hits}/{total} = {ans_hits/total:.0%}")
    print(f" Both correct          : {both_hits}/{total} = {both_hits/total:.0%}")
    print("============================================================\n")

    # A real but non-brittle gate. The printed numbers are the headline figure.
    assert ans_hits / total >= 0.7, f"answer accuracy {ans_hits/total:.0%} below 70% floor"
