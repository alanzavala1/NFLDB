"""Play query can run without an assistant context and preserves provenance data."""
import json

import duckdb
import pytest

from services import play_queries
from tests.conftest import _create_schema, _seed


def test_model_free_query_matches_tool_payload_and_recording(monkeypatch):
    import database
    import llm

    with duckdb.connect(':memory:') as conn:
        _create_schema(conn)
        _seed(conn)
        conn.execute('ALTER TABLE plays ADD COLUMN first_down INTEGER')
        monkeypatch.setattr(database, '_conn', conn)
        monkeypatch.setattr(play_queries, '_plays_columns_cache', None)
        monkeypatch.setattr(play_queries, '_plays_seasons_cache', None)
        args = {'season': 2024, 'play': 'pass', 'offense': ' buf ', 'group_by': 'qtr'}
        result = play_queries.query_plays(**args)
        assert result.rows and result.rows[0]['plays'] > 0
        assert result.arguments['offense'] == 'BUF'
        assert 'group_by' not in result.result['filters']
        ctx = llm._Ctx()
        tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'query_plays')
        raw = tool.func(**args)
        assert json.loads(raw) == result.result
        assert ctx.calls == [{'tool': 'query_plays', 'args': result.arguments}]
        assert ctx.data == result.rows and ctx.raw_results == [raw]


def test_invalid_filters_do_not_reach_storage(monkeypatch):
    def fail(*args):
        pytest.fail('invalid identifier reached storage')
    monkeypatch.setattr(play_queries, 'query_to_dict', fail)
    result = play_queries.query_plays(2024, group_by='qtr; DROP TABLE plays')
    assert result.result.startswith('Invalid group_by')
    assert result.rows == []
