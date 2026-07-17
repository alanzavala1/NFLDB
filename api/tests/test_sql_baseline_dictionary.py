"""Free real-DB contract checks for the baseline v2 data dictionary."""
import os

import pytest

from tests.sql_baseline import HARNESS_VERSION, build_schema_prompt, connect_read_only


_DB = os.path.join(os.path.dirname(__file__), "..", "data", "nfl.duckdb")

pytestmark = pytest.mark.skipif(
    not os.path.exists(_DB),
    reason="real nfl.duckdb required for baseline dictionary checks",
)


def test_v2_dictionary_exposes_verified_grain_and_vocabularies():
    conn = connect_read_only(_DB)
    try:
        prompt = build_schema_prompt(conn)
    finally:
        conn.close()

    assert HARNESS_VERSION == 2
    assert "player_game_stats contains both regular-season and playoff rows" in prompt
    assert "game types=[CON,DIV,REG,SB,WC]" in prompt
    assert "schedules.game_type='REG'" in prompt
    assert "player_splits category values=[passing,receiving,rushing]" in prompt
    assert "defense_splits split_dim values=" in prompt
    assert "team_splits side values=[defense,offense]" in prompt
    assert "ngs_* rows are player/season_type/week\n  AGGREGATES, not plays" in prompt
    assert "ftn_charting covers 2022-2025 and has one row per charted" in prompt
    assert "JAX=Jacksonville Jaguars" in prompt
    assert "JAC=Jacksonville Jaguars" not in prompt
