"""Free safety and control-flow tests for the isolated SQL baseline."""
from types import SimpleNamespace

import pytest

from tests.sql_baseline import (
    SQLBaseline,
    SQLGuardError,
    _extract_sql,
    connect_read_only,
    guard_select,
)


class _StubMessages:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.texts.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=2),
        )


class _StubClient:
    def __init__(self, texts):
        self.messages = _StubMessages(texts)


class _StubConnection:
    def __init__(self, fail_first=False):
        self.fail_first = fail_first
        self.calls = []
        self.description = [("answer",)]

    def execute(self, sql):
        self.calls.append(sql)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("missing column")
        return self

    def fetchmany(self, size):
        assert size == 50
        return [(42,)]


@pytest.mark.parametrize("verb", ["UPDATE", "DELETE", "DROP", "ATTACH", "PRAGMA", "COPY"])
def test_guard_rejects_non_select_statements(verb):
    with pytest.raises(SQLGuardError):
        guard_select(f"{verb} something")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DROP TABLE plays",
        "SELECT 1; SELECT 2;",
        "-- harmless-looking prefix\nDROP TABLE plays",
        "/* SELECT 1 */ UPDATE plays SET season = 0",
        "WITH x AS (SELECT 1) DELETE FROM plays",
    ],
)
def test_guard_rejects_multiple_and_comment_hidden_statements(sql):
    with pytest.raises(SQLGuardError):
        guard_select(sql)


def test_guard_accepts_select_and_with_after_comment_stripping():
    assert guard_select("  -- generated query\nSELECT 1;  ") == "SELECT 1"
    assert guard_select("/* read only */ WITH x AS (SELECT 1 AS n) SELECT n FROM x") == (
        "WITH x AS (SELECT 1 AS n) SELECT n FROM x"
    )


def test_fenced_select_executes():
    client = _StubClient([
        "```SQL\nSELECT 42 AS answer\n```",
        "The answer is 42.",
    ])
    conn = _StubConnection()

    result = SQLBaseline(client, conn, "schema").run("What is the answer?")

    assert result.sql == "SELECT 42 AS answer"
    assert conn.calls == ["SELECT 42 AS answer"]


def test_fenced_not_answerable_short_circuits_database_execution():
    client = _StubClient([
        "```\nNOT_ANSWERABLE\n```",
        "That data is not available.",
    ])
    conn = _StubConnection()

    result = SQLBaseline(client, conn, "schema").run("Where should I get pizza?")

    assert result.not_answerable is True
    assert conn.calls == []


def test_fenced_drop_is_still_rejected_by_guard():
    with pytest.raises(SQLGuardError, match="must start with SELECT or WITH"):
        guard_select(_extract_sql("```sql\nDROP TABLE plays\n```"))


def test_extract_sql_leaves_unfenced_input_unchanged():
    assert _extract_sql("  SELECT 1  ") == "SELECT 1"
    assert _extract_sql("  NOT_ANSWERABLE  ") == "NOT_ANSWERABLE"


def test_sql_error_gets_exactly_one_repair_round():
    client = _StubClient([
        "SELECT missing FROM plays",
        "SELECT 42 AS answer",
        "The answer is 42.",
    ])
    conn = _StubConnection(fail_first=True)
    baseline = SQLBaseline(client, conn, "schema")

    result = baseline.run("What is the answer?")

    assert result.answer == "The answer is 42."
    assert result.sql == "SELECT 42 AS answer"
    assert result.sql_error_count == 1
    assert result.repair_used is True
    assert len(conn.calls) == 2
    assert len(client.messages.calls) == 3
    assert client.messages.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_not_answerable_short_circuits_database_execution():
    client = _StubClient([
        "NOT_ANSWERABLE",
        "The NFL database cannot answer that question.",
    ])
    conn = _StubConnection()
    baseline = SQLBaseline(client, conn, "schema")

    result = baseline.run("Where should I get pizza?")

    assert result.not_answerable is True
    assert result.repair_used is False
    assert conn.calls == []
    assert len(client.messages.calls) == 2


def test_database_connection_is_forced_read_only():
    seen = {}
    marker = object()

    def connect(path, **kwargs):
        seen["path"] = path
        seen["kwargs"] = kwargs
        return marker

    assert connect_read_only("nfl.duckdb", connect=connect) is marker
    assert seen == {"path": "nfl.duckdb", "kwargs": {"read_only": True}}
