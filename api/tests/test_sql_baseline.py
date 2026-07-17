"""Opt-in billed head-to-head run for the isolated text-to-SQL baseline.

The runner imports the typed agent's GOLD cases and live oracle so both arms
answer identical questions and face identical answer graders. It is never run
by plain pytest; reviewers opt in with RUN_SQL_BASELINE=1.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import anthropic
import pytest

from tests.sql_baseline import HARNESS_VERSION, MODEL, SQLBaseline
from tests.test_ask_eval import GOLD, _oracle


_DB = os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")
_OUT = os.path.join(os.path.dirname(__file__), "out", "sql_baseline_runs.jsonl")

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_SQL_BASELINE") or not os.path.exists(_DB),
    reason="billed SQL baseline - set RUN_SQL_BASELINE=1 and have nfl.duckdb",
)


def _ascii(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _print_summary(summary: dict) -> None:
    total = summary["questions"]
    passed = summary["passed"]
    print("\n================ text-to-SQL baseline eval ================")
    print("System       | Accuracy       | Avg latency | Input tok | Output tok | Total tok")
    print("-------------+----------------+-------------+-----------+------------+----------")
    print(f"Typed tools  | {total}/{total} (100%) | TBD         | TBD       | TBD        | TBD")
    print(
        f"SQL baseline | {passed}/{total} ({summary['accuracy']:.0%})"
        f" | {summary['avg_latency_seconds']:.2f}s"
        f"       | {summary['input_tokens']}"
        f"     | {summary['output_tokens']}"
        f"      | {summary['total_tokens']}"
    )
    print(
        f"Repairs: {summary['repairs']} | SQL errors: {summary['sql_errors']} | "
        f"NOT_ANSWERABLE: {summary['not_answerable']}"
    )
    print("============================================================\n")


def test_sql_baseline_against_gold(monkeypatch):
    import database

    baseline = SQLBaseline.from_database(_DB)
    monkeypatch.setattr(database, "_conn", baseline.conn)
    cases = []
    try:
        fns = _oracle()
        for index, gold in enumerate(GOLD, 1):
            try:
                result = baseline.run(gold["q"], history=gold.get("history", []))
            except anthropic.AuthenticationError:
                if not cases:
                    pytest.skip("no Anthropic credentials (API key or logged-in profile)")
                raise

            try:
                passed = bool(gold["grade"](result.answer, fns))
            except Exception:
                passed = False

            mark = "OK" if passed else "X"
            answer_preview = result.answer.replace("\n", " ")[:90]
            print(f"{mark} {index:02d} | {_ascii(gold['q'])} | {_ascii(answer_preview)}")
            if not passed:
                print(f"     SQL: {_ascii(result.sql or 'NOT_ANSWERABLE')}")
                print(f"     error: {_ascii(result.error or '(none)')}")

            cases.append({
                "question": gold["q"],
                "passed": passed,
                "answer": result.answer,
                "sql": result.sql,
                "error": result.error,
                "latency_seconds": round(result.latency_seconds, 4),
                "input_tokens": result.usage.input,
                "uncached_input_tokens": result.usage.uncached_input,
                "cache_creation_input_tokens": result.usage.cache_creation_input,
                "cache_read_input_tokens": result.usage.cache_read_input,
                "output_tokens": result.usage.output,
                "total_tokens": result.usage.total,
                "sql_error_count": result.sql_error_count,
                "repair_used": result.repair_used,
                "not_answerable": result.not_answerable,
            })
    finally:
        baseline.close()

    total = len(cases)
    passed = sum(case["passed"] for case in cases)
    total_latency = sum(case["latency_seconds"] for case in cases)
    summary = {
        "harness_version": HARNESS_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": MODEL,
        "questions": total,
        "passed": passed,
        "accuracy": passed / total if total else 0,
        "total_latency_seconds": round(total_latency, 4),
        "avg_latency_seconds": round(total_latency / total, 4) if total else 0,
        "input_tokens": sum(case["input_tokens"] for case in cases),
        "uncached_input_tokens": sum(case["uncached_input_tokens"] for case in cases),
        "cache_creation_input_tokens": sum(case["cache_creation_input_tokens"] for case in cases),
        "cache_read_input_tokens": sum(case["cache_read_input_tokens"] for case in cases),
        "output_tokens": sum(case["output_tokens"] for case in cases),
        "total_tokens": sum(case["total_tokens"] for case in cases),
        "sql_errors": sum(case["sql_error_count"] for case in cases),
        "repairs": sum(case["repair_used"] for case in cases),
        "not_answerable": sum(case["not_answerable"] for case in cases),
        "schema_prompt_chars": len(baseline.schema_prompt),
        "schema_prompt_tokens_estimate": round(len(baseline.schema_prompt) / 4),
        "cases": cases,
    }
    _print_summary(summary)
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    with open(_OUT, "a", encoding="utf-8") as output:
        output.write(json.dumps(summary, ensure_ascii=True, separators=(",", ":")) + "\n")

    assert total == len(GOLD)
