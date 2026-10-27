"""Prepared passing HTTP reads preserve independent totals and NULL reasons."""
import asyncio
import json

import duckdb
import httpx
import pytest

from pipeline.passing_build import _DDL
from pipeline.passing_down import adapt_passing_down
from pipeline.passing_metrics import apply_passing_metrics
from pipeline.passing_summary import prepare_passing_summary
from tests.passing_cases import metric_case
from tests.test_passing_summary import whole


@pytest.fixture
def prepared(monkeypatch):
    import database
    import splits_builder
    data = metric_case()
    rows, _ = adapt_passing_down(**{k: v for k, v in data.items() if k != 'credits'})
    rows, metrics = apply_passing_metrics(rows, data['down'], data['context'], data['credits'], 2024)
    report = {'season': 2024, 'format_version': 1,
        'summary': prepare_passing_summary(whole(data), data['context'], data['credits'], 2024, ['qb']),
        'dimensions': {'down': {'metric_availability': metrics,
            'coverage': {'status': 'complete', 'reason': None, 'definition': 'Recorded down.'},
            'excluded_by_player': {'qb': dict(attempts=0, completions=0, passing_yards=0,
                passing_tds=0, passing_interceptions=0, passing_first_downs=0, sacks_suffered=0)}}},
        'source_directory': 'private-path', 'another_player': 'private-player'}
    with duckdb.connect(':memory:') as conn:
        splits_builder.ensure_table(conn)
        conn.register('prepared_rows', rows)
        conn.execute('INSERT INTO player_splits BY NAME SELECT * FROM prepared_rows')
        conn.unregister('prepared_rows')
        conn.execute(_DDL)
        conn.execute('INSERT INTO passing_build_preparation VALUES (?,?)', [2024, json.dumps(report)])
        monkeypatch.setattr(database, '_conn', conn)
        def forbidden(*args, **kwargs): raise AssertionError('HTTP attempted build')
        monkeypatch.setattr(splits_builder, 'materialize', forbidden)
        yield conn, report


def get(player='qb'):
    async def request():
        from main import app
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            return await client.get(f'/api/players/{player}/passing-splits')
    return asyncio.run(request())


def update(conn, report):
    conn.execute('UPDATE passing_build_preparation SET record=?', [json.dumps(report)])


def test_http_independent_whole_totals_components_and_private_projection(prepared):
    response = get()
    assert response.status_code == 200, response.text
    payload = response.json()
    season, = payload['seasons']
    assert season['status'] == 'prepared'
    assert season['overall']['att'] == 50 and season['overall']['yards'] == 400
    assert season['overall']['aggregation']['cpoe_count'] == 33
    assert season['overall']['aggregation']['cpoe_sum'] == 132
    assert season['overall']['epa'] == .05 and season['overall']['unavailable_metrics'] == {}
    assert len(season['rows']) == 2
    assert season['views']['down']['excluded']['att'] == 0
    assert 'private-path' not in response.text and 'private-player' not in response.text
    assert get('backup').json()['seasons'] == []
    assert get('absent').json()['seasons'] == []
    from pipeline.passing_api_checks import check_passing_api
    assert asyncio.run(check_passing_api(prepared[0], [2024])) == ['/api/players/qb/passing-splits']


def test_partial_view_retains_excluded_counts_and_independent_total(prepared):
    conn, report = prepared
    conn.execute("DELETE FROM player_splits WHERE split_value='2'")
    view = report['dimensions']['down']
    view['coverage'].update(status='partial', reason='Some plays lack recorded down.')
    view['excluded_by_player']['qb'].update(attempts=25, completions=15, passing_yards=150,
        passing_tds=1, passing_interceptions=1, passing_first_downs=7)
    update(conn, report)
    response = get()
    assert response.status_code == 200, response.text
    year, = response.json()['seasons']
    assert year['overall']['yards'] == 400 and year['rows'][0]['yards'] == 250
    assert year['views']['down']['excluded']['yards'] == 150


def test_older_preparation_is_explicitly_unverified_without_building(prepared):
    conn, report = prepared
    del report['summary']
    update(conn, report)
    response = get()
    assert response.status_code == 200
    year, = response.json()['seasons']
    assert year['status'] == 'unverified' and year['overall'] is None and year['rows'] == []


@pytest.mark.parametrize('fault', ['components', 'excluded', 'reason'])
def test_release_api_check_detects_response_only_corruption(prepared, monkeypatch, fault):
    from pipeline.passing_api_checks import check_passing_api
    from pipeline.validation import SnapshotValidationError
    original = httpx.AsyncClient.get
    async def changed(*args, **kwargs):
        response = await original(*args, **kwargs)
        payload = response.json()
        season = payload['seasons'][0]
        if fault == 'components': season['rows'][0]['aggregation']['cpoe_count'] += 1
        elif fault == 'excluded': season['views']['down']['excluded']['yards'] += 1
        else: season['rows'][0]['unavailable_metrics']['epa'] = 'changed explanation'
        return httpx.Response(200, json=payload)
    monkeypatch.setattr(httpx.AsyncClient, 'get', changed)
    with pytest.raises(SnapshotValidationError): asyncio.run(check_passing_api(prepared[0], [2024]))


@pytest.mark.parametrize('fault', ['components', 'explanation', 'conservation', 'duplicate', 'infinite', 'partial_cpoe'])
def test_corrupt_prepared_data_fails_without_repair_or_internal_details(prepared, fault):
    conn, report = prepared
    metric = report['dimensions']['down']['metric_availability']
    if fault == 'components': metric['aggregation'][0]['epa_sum'] += 9
    elif fault == 'explanation': conn.execute("UPDATE player_splits SET epa=NULL WHERE split_value='1'")
    elif fault == 'conservation': report['summary']['rows'][0]['yards'] += 1
    elif fault == 'duplicate': metric['aggregation'].append(metric['aggregation'][0])
    elif fault == 'infinite': metric['aggregation'][0]['epa_sum'] = float('inf')
    elif fault == 'partial_cpoe': metric['aggregation'][0]['cpoe_sum'] = None
    update(conn, report)
    before = conn.execute('SELECT * FROM player_splits ORDER BY ALL').fetchall()
    response = get()
    assert response.status_code == 503
    assert response.json() == {'detail': 'Prepared passing data is unavailable'}
    assert conn.execute('SELECT * FROM player_splits ORDER BY ALL').fetchall() == before
