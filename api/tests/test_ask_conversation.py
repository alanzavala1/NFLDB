"""Free contract tests for bounded, Anthropic-safe /ask conversation history."""
import pytest
from pydantic import ValidationError

from llm import _conversation_messages
from routers.assistant import _MAX_HISTORY_CHARS, _normalize_history
from schemas.assistant import AskHistoryMessage, AskRequest


def _message(role: str, content: str) -> AskHistoryMessage:
    return AskHistoryMessage(role=role, content=content)


def test_empty_history_preserves_single_question_behavior():
    assert AskRequest(question="Who led in sacks?").history == []
    assert _normalize_history([]) == []
    assert _conversation_messages("Who led in sacks?", []) == [
        {"role": "user", "content": "Who led in sacks?"}
    ]


def test_history_keeps_only_last_twelve_messages():
    history = [
        _message("user" if i % 2 == 0 else "assistant", f"message-{i}")
        for i in range(14)
    ]

    normalized = _normalize_history(history)

    assert [message["content"] for message in normalized] == [
        f"message-{i}" for i in range(2, 14)
    ]


def test_history_character_cap_trims_oldest_whole_messages():
    history = [
        _message("user", "a" * 3_000),
        _message("assistant", "b" * 3_000),
        _message("user", "c" * 3_000),
        _message("assistant", "d" * 3_000),
    ]

    normalized = _normalize_history(history)

    assert [message["content"][0] for message in normalized] == ["c", "d"]
    assert sum(len(message["content"]) for message in normalized) <= _MAX_HISTORY_CHARS


def test_history_drops_assistant_prefix_and_merges_consecutive_roles():
    history = [
        _message("assistant", "orphaned answer"),
        _message("user", "first user part"),
        _message("user", "second user part"),
        _message("assistant", "first answer part"),
        _message("assistant", "second answer part"),
    ]

    assert _normalize_history(history) == [
        {"role": "user", "content": "first user part\n\nsecond user part"},
        {"role": "assistant", "content": "first answer part\n\nsecond answer part"},
    ]


def test_message_builder_defensively_normalizes_history_and_current_question():
    messages = _conversation_messages("current question", [
        {"role": "assistant", "content": "orphaned answer"},
        {"role": "user", "content": "unfinished prior question"},
    ])

    assert messages == [
        {"role": "user", "content": "unfinished prior question\n\ncurrent question"}
    ]


def test_history_role_is_schema_validated():
    with pytest.raises(ValidationError):
        AskRequest.model_validate({
            "question": "What about 2022?",
            "history": [{"role": "tool", "content": "untrusted result"}],
        })


def test_invalid_history_role_returns_422(client):
    response = client.post("/api/ask", json={
        "question": "What about 2022?",
        "history": [{"role": "tool", "content": "untrusted result"}],
    })

    assert response.status_code == 422
