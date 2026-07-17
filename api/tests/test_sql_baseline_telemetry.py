"""Free checks for loading the typed arm's latest comparison telemetry."""
import json

from tests.test_sql_baseline import _latest_ask_summary


def test_latest_ask_summary_uses_last_valid_json_line(tmp_path):
    path = tmp_path / "ask_eval_runs.jsonl"
    older = {"questions": 56, "avg_latency_seconds": 1.5, "total_tokens": 100}
    latest = {"questions": 56, "avg_latency_seconds": 1.2, "total_tokens": 90}
    path.write_text(
        json.dumps(older) + "\nnot json\n" + json.dumps(latest) + "\n",
        encoding="utf-8",
    )

    assert _latest_ask_summary(str(path)) == latest


def test_latest_ask_summary_returns_none_without_log(tmp_path):
    assert _latest_ask_summary(str(tmp_path / "missing.jsonl")) is None
