"""Free checks for internal typed-agent usage telemetry."""
from types import SimpleNamespace

import llm
from schemas.assistant import AskResponse


def _message(text, *, uncached, cache_creation, cache_read, output):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=uncached,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
            output_tokens=output,
        ),
    )


def test_run_ask_accumulates_every_model_messages_usage(monkeypatch):
    messages = [
        _message("intermediate", uncached=11, cache_creation=101,
                 cache_read=0, output=7),
        _message("Final answer.", uncached=13, cache_creation=0,
                 cache_read=103, output=9),
    ]
    tool_runner = lambda **kwargs: iter(messages)
    client = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner))
    )
    monkeypatch.setattr(llm, "_get_client", lambda: client)

    result = llm.run_ask("Who led the league?")

    assert result["answer"] == "Final answer."
    assert result["usage"] == {
        "uncached_input": 24,
        "cache_creation_input": 101,
        "cache_read_input": 103,
        "output": 16,
    }


def test_internal_usage_is_excluded_from_api_response_schema():
    result = {
        "answer": "Final answer.",
        "data": [],
        "tools_used": [],
        "usage": {"uncached_input": 1, "output": 1},
    }

    response = AskResponse.model_validate(result).model_dump()

    assert response == {"answer": "Final answer.", "data": [], "tools_used": []}
