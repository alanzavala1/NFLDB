"""Offline search behavior and HTTP/assistant consumer checks."""
import json

import duckdb
import pytest

from services.search import search


@pytest.fixture
def search_roster(monkeypatch):
    import database

    with duckdb.connect(':memory:') as conn:
        conn.execute('''CREATE TABLE rosters (
            player_id VARCHAR, season INTEGER, player_name VARCHAR,
            position VARCHAR, team VARCHAR, headshot_url VARCHAR
        )''')
        conn.executemany('INSERT INTO rosters VALUES (?, ?, ?, ?, ?, ?)', [
            ('allen', 2023, 'Josh Allen', 'QB', 'OLD', 'old.png'),
            ('allen', 2024, 'Josh Allen', 'QB', 'BUF', 'current.png'),
            ('prefix', 2025, 'Josh Allenby', 'WR', 'SF', None),
            ('substring', 2026, 'My Josh Allen', 'WR', 'KC', None),
            ('compact', 2027, 'JoshAllen', 'WR', 'KC', None),
            ('mahomes', 2024, 'Patrick Mahomes', 'QB', 'KC', None),
            ('cmc', 2024, 'Christian McCaffrey', 'RB', 'SF', None),
            ('brown', 2024, 'Amon-Ra St. Brown', 'WR', 'DET', None),
            ('watt', 2024, 'T.J. Watt', 'LB', 'PIT', None),
            ('chase', 2024, "Ja'Marr Chase", 'WR', 'CIN', None),
        ])
        monkeypatch.setattr(database, '_conn', conn)
        yield conn


@pytest.mark.parametrize(('query', 'kind', 'entity'), [
    (' CMC ', 'player', 'cmc'), ('Niners', 'team', 'SF'),
    ('P. Mahomes', 'player', 'mahomes'), ('Amon Ra St Brown', 'player', 'brown'),
    ('TJ Watt', 'player', 'watt'), ('JaMarr Chase', 'player', 'chase'),
    ('buf', 'team', 'BUF'),
])
def test_aliases_initials_and_punctuation_keep_their_matches(search_roster, query, kind, entity):
    assert any(row['type'] == kind and row['id'] == entity for row in search(query))


def test_exact_prefix_substring_and_compact_order_and_latest_roster(search_roster):
    rows = search('Josh Allen')
    assert [row['id'] for row in rows] == ['allen', 'prefix', 'substring', 'compact']
    assert rows[0] == {
        'type': 'player', 'id': 'allen', 'name': 'Josh Allen',
        'position': 'QB', 'team': 'BUF', 'headshot_url': 'current.png',
    }


def test_one_character_search_keeps_teams_first_and_caps_results(search_roster):
    search_roster.executemany('INSERT INTO rosters VALUES (?, ?, ?, ?, ?, ?)', [
        (f'cap-{i:02}', 2030, f'Alex Player {i:02}', 'WR', 'BUF', None) for i in range(12)
    ])
    rows = search('a')
    assert len(rows) == 10
    assert [row['type'] for row in rows] == ['team'] * 3 + ['player'] * 7
    assert [row['id'] for row in rows[3:]] == [f'cap-{i:02}' for i in range(7)]


@pytest.mark.parametrize('query', ['', '   ', '?!', '...'])
def test_blank_and_punctuation_only_inputs_do_not_query_rosters(monkeypatch, query):
    import services.search

    def unexpected_query(*args, **kwargs):
        pytest.fail('empty normalized input reached the roster query')

    monkeypatch.setattr(services.search, 'safe_query', unexpected_query)
    assert search(query) == []


def test_http_and_entity_tool_share_matches_and_keep_the_tool_projection(client, search_roster):
    import llm

    expected = search('CMC')
    response = client.get('/api/search', params={'q': 'CMC'})
    assert response.status_code == 200
    assert response.json() == expected
    ctx = llm._Ctx()
    tool = next(tool for tool in llm._build_tools(ctx) if tool.name == 'resolve_entity')
    raw = tool.func(name='CMC')
    assert json.loads(raw) == [{key: row[key] for key in ('type', 'id', 'name', 'position', 'team')} for row in expected]
    assert ctx.calls == [{'tool': 'resolve_entity', 'args': {'name': 'CMC'}}]
    assert ctx.raw_results == [raw]
    assert tool.func(name='no such person') == 'No player or team matched that name.'


def test_http_keeps_required_nonempty_query_validation(client):
    assert client.get('/api/search').status_code == 422
    assert client.get('/api/search', params={'q': ''}).status_code == 422
    assert client.get('/api/search', params={'q': '   '}).json() == []


def test_unexpected_roster_failure_propagates(monkeypatch):
    import sql_helpers

    def fail(*args, **kwargs):
        raise RuntimeError('roster query failed')

    monkeypatch.setattr(sql_helpers, 'query_to_dict', fail)
    with pytest.raises(RuntimeError, match='roster query failed'):
        search('Niners')
