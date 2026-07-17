"""Free validation checks for model-facing /ask tool arguments."""
import pytest


def test_player_tools_reject_names_before_querying(monkeypatch):
    import llm

    def unexpected_query(*args, **kwargs):
        pytest.fail("invalid player id reached the verified query layer")

    monkeypatch.setattr(llm, "_player_profile", unexpected_query)
    monkeypatch.setattr(llm.splits_builder, "read_or_materialize", unexpected_query)
    monkeypatch.setattr(llm.def_splits_builder, "read_or_materialize", unexpected_query)
    monkeypatch.setattr(llm.comparables_builder, "read_or_materialize", unexpected_query)

    ctx = llm._Ctx()
    tools = {tool.name: tool.func for tool in llm._build_tools(ctx)}
    expected = ("That is not a player id — call resolve_entity first and use "
                "the returned id.")
    calls = [
        ("get_player_overview", {"player_id": "Josh Allen", "season": 2023}),
        ("get_player_splits", {"player_id": "CMC", "season": 2023,
                               "category": "rushing", "dimension": "down"}),
        ("get_player_game_log", {"player_id": "Derrick Henry", "season": 2020}),
        ("get_player_career", {"player_id": "Aaron Rodgers"}),
        ("get_comparables", {"player_id": "Mahomes"}),
    ]

    for name, args in calls:
        assert tools[name](**args) == expected
