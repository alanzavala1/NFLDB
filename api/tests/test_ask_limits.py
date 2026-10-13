"""Offline regression checks for an assistant that keeps requesting tools.

Use the real Anthropic runner and stream parser with a fake HTTP provider:
no credentials, database, or billed model calls are needed.
"""
import json

import anthropic
import pytest

import llm

# The SDK changed HTTP libraries in 1.x. Its fake transport must use the same
# library as the installed SDK; keep these checks usable in the older local env.
if int(anthropic.__version__.split(".", 1)[0]) >= 1:
    import httpx2 as httpx
else:
    import httpx


def _sse(message):
    events = []

    def emit(kind, **fields):
        payload = json.dumps({"type": kind, **fields})
        events.append(f"event: {kind}\ndata: {payload}\n\n")

    start = {**message, "content": [], "stop_reason": None,
             "usage": {"input_tokens": 1, "output_tokens": 0}}
    emit("message_start", message=start)
    for index, block in enumerate(message["content"]):
        if block["type"] == "text":
            emit("content_block_start", index=index,
                 content_block={"type": "text", "text": ""})
            emit("content_block_delta", index=index,
                 delta={"type": "text_delta", "text": block["text"]})
        else:
            emit("content_block_start", index=index,
                 content_block={**block, "input": {}})
            emit("content_block_delta", index=index,
                 delta={"type": "input_json_delta",
                        "partial_json": json.dumps(block["input"])})
        emit("content_block_stop", index=index)
    emit("message_delta", delta={"stop_reason": message["stop_reason"],
                                 "stop_sequence": None},
         usage={"output_tokens": 1})
    emit("message_stop")
    return "".join(events)


@pytest.fixture
def fake_provider(monkeypatch):
    requests = []
    contexts = []
    spend = []
    behavior = {"name": "get_metadata", "input": {}, "finish_on": None}

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        # Keep a broken implementation from hanging the regression test.
        assert len(requests) <= 3, "Assistant exceeded its model-turn limit"
        finished = len(requests) == behavior["finish_on"]
        content = [{"type": "text", "text": "Final answer." if finished
                    else "Still working."}]
        if not finished:
            content.append({"type": "tool_use", "id": f"tool_{len(requests)}",
                            "name": behavior["name"], "input": behavior["input"]})
        message = {"id": f"msg_{len(requests)}", "type": "message",
                   "role": "assistant", "model": llm.MODEL, "content": content,
                   "stop_reason": "end_turn" if finished else "tool_use",
                   "stop_sequence": None,
                   "usage": {"input_tokens": 1, "output_tokens": 1}}
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text=_sse(message))
        return httpx.Response(200, json=message)

    build_tools = llm._build_tools

    def capture_context(ctx):
        contexts.append(ctx)
        return build_tools(ctx)

    client = anthropic.Anthropic(
        api_key="offline-test-key", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(llm, "_get_client", lambda: client)
    monkeypatch.setattr(llm, "_build_tools", capture_context)
    monkeypatch.setattr(llm, "_record_spend", spend.append)
    monkeypatch.setattr(llm, "_MAX_TOOL_CALLS", 1)
    monkeypatch.setattr(llm, "_MAX_MODEL_TURNS", 3, raising=False)
    yield behavior, requests, contexts, spend
    client.close()


def _run(streaming):
    if streaming:
        events = list(llm.run_ask_stream("Which seasons are available?"))
        assert events[-1]["type"] == "done"
        assert sum(event["type"] == "done" for event in events) == 1
        return events[-1]
    return llm.run_ask("Which seasons are available?")


@pytest.mark.parametrize("streaming", [False, True], ids=["runner", "stream"])
@pytest.mark.parametrize("name,args", [
    ("get_metadata", {}),
    ("missing_tool", {}),
    ("get_player_overview", {"season": 2023}),  # required player_id is absent
], ids=["budget-denied", "unknown-tool", "invalid-input"])
def test_repeated_tool_requests_stop_at_model_turn_limit(fake_provider, streaming, name, args):
    behavior, requests, contexts, spend = fake_provider
    behavior.update(name=name, input=args)

    if name == "missing_tool" and not streaming:
        with pytest.warns(UserWarning, match="Tool 'missing_tool' not found"):
            result = _run(streaming)
    else:
        result = _run(streaming)

    assert len(requests) == 3
    assert result["answer"] == llm._LIMIT_ANSWER
    assert "Still working." not in result["answer"]
    ctx = contexts[0]
    if name == "get_metadata":
        # One successful call and one budget denial. The final requested tool
        # must not execute after the model limit, even through the SDK runner.
        assert ctx.n_calls == 2
        assert result["tools_used"] == [{"tool": "get_metadata", "args": {}}]
        assert ctx.raw_results
    else:
        assert ctx.n_calls == 0
        assert result["tools_used"] == []
    assert sum(item["uncached_input"] for item in spend) == 3
    assert sum(item["output"] for item in spend) == 3


@pytest.mark.parametrize("streaming", [False, True], ids=["runner", "stream"])
def test_final_answer_on_last_allowed_turn_is_kept(fake_provider, streaming):
    behavior, requests, contexts, spend = fake_provider
    behavior["finish_on"] = 3

    result = _run(streaming)

    assert len(requests) == 3
    assert result["answer"] == "Final answer."
    assert contexts[0].n_calls == 2
    assert result["tools_used"] == [{"tool": "get_metadata", "args": {}}]
    assert sum(item["uncached_input"] for item in spend) == 3
    assert sum(item["output"] for item in spend) == 3


@pytest.mark.parametrize("streaming", [False, True], ids=["runner", "stream"])
def test_valid_tool_round_trip_preserves_sampling_and_provenance(fake_provider, streaming):
    behavior, requests, contexts, spend = fake_provider
    behavior["finish_on"] = 2

    result = _run(streaming)

    assert result["answer"] == "Final answer."
    assert len(requests) == 2  # tool request, then answer after the tool result
    assert all(request["temperature"] == 0 for request in requests)
    assert all(request["model"] == llm.MODEL for request in requests)
    assert result["tools_used"] == [{"tool": "get_metadata", "args": {}}]
    assert contexts[0].n_calls == 1
    assert len(contexts[0].raw_results) == 1
    assert sum(item["uncached_input"] for item in spend) == 2
    assert sum(item["output"] for item in spend) == 2
