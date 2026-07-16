"""Contract tests for the /ask split vocabulary and entity resolution.

The vocabulary is deliberately static so it remains in the cacheable system
prompt. These tests compare that contract with the real materialized split
tables, but skip cleanly when the repository's full DuckDB is absent.
"""
import os

import duckdb
import pytest

_DB = os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")

pytestmark = pytest.mark.skipif(
    not os.path.exists(_DB),
    reason="real nfl.duckdb required for split-vocabulary contract checks",
)


def _grouped_values(conn, table: str, group_col: str | None) -> dict:
    if group_col:
        rows = conn.execute(
            f"""
            SELECT {group_col}, split_dim, LIST(DISTINCT split_value)
            FROM {table}
            GROUP BY 1, 2
            """
        ).fetchall()
        return {(group, dim): set(values) for group, dim, values in rows}

    rows = conn.execute(
        f"""
        SELECT split_dim, LIST(DISTINCT split_value)
        FROM {table}
        GROUP BY 1
        """
    ).fetchall()
    return {dim: set(values) for dim, values in rows}


def test_split_vocabulary_values_exist_in_materialized_tables():
    import llm

    used_dims = {dim for dims in llm._DIMENSIONS.values() for dim in dims}
    used_dims.update(llm._TEAM_DIMS)
    assert set(llm._SPLIT_VOCABULARY) == used_dims

    conn = duckdb.connect(_DB, read_only=True)
    try:
        player = _grouped_values(conn, "player_splits", "category")
        defense = _grouped_values(conn, "defense_splits", None)
        team = _grouped_values(conn, "team_splits", "side")
    finally:
        conn.close()

    for category, dims in llm._DIMENSIONS.items():
        for dim in dims:
            expected = set(llm._SPLIT_VOCABULARY[dim]["values"])
            actual = defense[dim] if category == "defense" else player[(category, dim)]
            assert expected == actual, (
                f"{category}.{dim}: missing {sorted(expected - actual)}, "
                f"unexpected {sorted(actual - expected)}"
            )

    for side in ("offense", "defense"):
        for dim in llm._TEAM_DIMS:
            expected = set(llm._SPLIT_VOCABULARY[dim]["values"])
            actual = team[(side, dim)]
            assert expected == actual, (
                f"team {side}.{dim}: missing {sorted(expected - actual)}, "
                f"unexpected {sorted(actual - expected)}"
            )


def test_search_accepts_conservative_aliases_and_normalized_names(monkeypatch):
    import database
    from routers.leaders import search

    conn = duckdb.connect(_DB, read_only=True)
    monkeypatch.setattr(database, "_conn", conn)
    try:
        assert any(r["type"] == "player" and r["name"] == "Christian McCaffrey"
                   for r in search(q="CMC"))
        assert any(r["type"] == "team" and r["id"] == "SF"
                   for r in search(q="Niners"))
        assert any(r["type"] == "player" and r["name"] == "Patrick Mahomes"
                   for r in search(q="P. Mahomes"))
        assert any(r["type"] == "player" and r["name"] == "Amon-Ra St. Brown"
                   for r in search(q="Amon Ra St Brown"))
    finally:
        conn.close()
