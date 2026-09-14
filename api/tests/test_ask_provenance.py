"""Free tests pinning the provenance capture both tool-call paths rely on.

The eval's figure audit needs every tool result string recorded on the
request's _Ctx. Tools are invoked two different ways — the SDK tool runner
dispatches through `_func_with_validate` (run_ask) while the manual streaming
loop calls `.func` (run_ask_stream) — and an SDK upgrade could quietly change
either, so both paths are asserted here with a DB-free tool.
"""


def _metadata_tool(ctx):
    import llm

    return next(t for t in llm._build_tools(ctx) if t.name == "get_metadata")


def test_streaming_path_captures_exactly_one_result_per_call():
    import llm

    ctx = llm._Ctx()
    tool = _metadata_tool(ctx)
    out = tool.func()
    assert ctx.raw_results == [out]
    assert '"seasons"' in ctx.raw_results[0]


def test_sdk_runner_path_captures_exactly_one_result_per_call():
    import llm

    ctx = llm._Ctx()
    tool = _metadata_tool(ctx)
    tool.call({})
    assert len(ctx.raw_results) == 1
    assert '"seasons"' in ctx.raw_results[0]


def test_contexts_do_not_share_captures():
    import llm

    ctx_a = llm._Ctx()
    ctx_b = llm._Ctx()
    _metadata_tool(ctx_a).func()
    assert ctx_a.raw_results and not ctx_b.raw_results
