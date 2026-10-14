"""Optional vendor coverage is explicit, and storage errors never become gaps."""
from urllib.error import HTTPError, URLError

import duckdb
import pandas as pd
import pytest

import ingest
from pipeline import vendor_sources as vendor
from pipeline.source_results import SourceError


def frame_for(spec, seasons):
    rows = []
    for season in seasons:
        row = {column: 'p' for column in spec.required_columns}
        if 'season' in row:
            row['season'] = season
        if spec.scope == 'snapshot':
            row['dt'] = f'{season}-09-01'
        if spec.name == 'ftn_charting':
            row['nflverse_play_id'] = 1.0
        rows.append(row)
    return pd.DataFrame(rows)


def mock_reads(monkeypatch, read):
    monkeypatch.setattr(vendor.pd, 'read_parquet', read)
    monkeypatch.setattr(vendor.pd, 'read_csv', read)


@pytest.mark.parametrize('spec', (*vendor.ADVANCED_SOURCES, *vendor.SUPPLEMENTAL_SOURCES), ids=lambda s: s.name)
def test_catalog_sources_load_without_database_or_provider_wrappers(monkeypatch, spec):
    calls = []

    def read(url):
        calls.append(url)
        return frame_for(spec, [2024])

    mock_reads(monkeypatch, read)
    feed = vendor.fetch_vendor(spec, [2024])
    assert feed.source == spec.name and len(feed.data) == 1
    assert [(o.status, o.rows) for o in feed.outcomes] == [('loaded', 1)]
    assert calls == [spec.url.format(season=2024)]


@pytest.mark.parametrize('status,error', [
    ('not_found', HTTPError('url', 404, 'missing', None, None)),
    ('failed', HTTPError('url', 503, 'outage', None, None)),
    ('failed', TimeoutError('timeout')), ('failed', URLError('offline')),
])
def test_expected_remote_gaps_preserve_per_season_outcomes(monkeypatch, status, error):
    def read(url):
        raise error

    mock_reads(monkeypatch, read)
    feed = vendor.fetch_vendor(vendor.NGS_SOURCES[0], [2024, 2025])
    assert feed.data is None and feed.loaded_seasons == []
    assert [(o.season, o.status) for o in feed.outcomes] == [(2024, status), (2025, status)]


@pytest.mark.parametrize('error', [ValueError('bad parquet'), NameError('code bug'), RuntimeError('unexpected')])
def test_unexpected_faults_fail_refresh_with_source_and_original_cause(monkeypatch, error):
    def read(url):
        raise error

    mock_reads(monkeypatch, read)
    with pytest.raises(SourceError, match=r'pfr_pass\[2024\]') as caught:
        vendor.fetch_vendor(vendor.PFR_SOURCES[0], [2024])
    assert caught.value.__cause__ is error


def test_missing_required_vendor_schema_is_not_an_optional_gap(monkeypatch):
    mock_reads(monkeypatch, lambda url: pd.DataFrame({'season': [2024]}))
    with pytest.raises(SourceError, match='player_gsis_id'):
        vendor.fetch_vendor(vendor.NGS_SOURCES[0], [2024])


def test_bulk_asset_is_read_once_and_filters_exact_requested_years(monkeypatch):
    calls = []

    def read(url):
        calls.append(url)
        return frame_for(vendor.NGS_SOURCES[0], [2023, 2024, 2025, 2026])

    mock_reads(monkeypatch, read)
    feed = vendor.fetch_vendor(vendor.NGS_SOURCES[0], [2023, 2026])
    assert len(calls) == 1
    assert list(feed.data['season']) == [2023, 2026]
    assert feed.loaded_seasons == [2023, 2026]


def test_out_of_coverage_years_do_not_download_or_prevent_supported_years(monkeypatch):
    calls = []

    def read(url):
        calls.append(url)
        return frame_for(vendor.SNAPS, [2012])

    mock_reads(monkeypatch, read)
    feed = vendor.fetch_vendor(vendor.SNAPS, [2010, 2012])
    assert calls == [vendor.SNAPS.url.format(season=2012)]
    assert [(o.season, o.status) for o in feed.outcomes] == [(2010, 'unsupported'), (2012, 'loaded')]


def test_pre_coverage_only_request_makes_no_network_call(monkeypatch):
    mock_reads(monkeypatch, lambda url: pytest.fail('unsupported year downloaded'))
    feed = vendor.fetch_vendor(vendor.FTN, [2020])
    assert feed.data is None and feed.outcomes[0].status == 'unsupported'


def test_successful_bulk_asset_without_requested_year_reports_empty(monkeypatch):
    mock_reads(monkeypatch, lambda url: frame_for(vendor.PFR_SOURCES[0], [2024]))
    feed = vendor.fetch_vendor(vendor.PFR_SOURCES[0], [2026])
    assert feed.data is None and feed.outcomes[0].status == 'empty'


def test_wrong_year_in_seasonal_asset_fails_validation(monkeypatch):
    mock_reads(monkeypatch, lambda url: frame_for(vendor.SNAPS, [2025]))
    with pytest.raises(SourceError, match='unexpected seasons'):
        vendor.fetch_vendor(vendor.SNAPS, [2024])


def test_partial_snap_refresh_preserves_missing_seasons_in_real_storage(monkeypatch):
    spec = vendor.SNAPS
    seed = frame_for(spec, [2024, 2025]).assign(week=1)

    def read(url):
        if '2025' in url:
            raise HTTPError(url, 404, 'missing', None, None)
        return frame_for(spec, [2024]).assign(week=2)

    mock_reads(monkeypatch, read)
    monkeypatch.setattr(ingest, 'ADVANCED_SOURCES', (spec,))
    with duckdb.connect(':memory:') as conn:
        conn.register('seed', seed)
        conn.execute('CREATE TABLE snap_counts AS SELECT * FROM seed')
        outcomes = ingest.load_advanced_stats(conn, [2024, 2025])
        assert conn.execute('SELECT season, week FROM snap_counts ORDER BY season').fetchall() == [(2024, 2), (2025, 1)]
    assert [(o.season, o.status) for o in outcomes] == [(2024, 'loaded'), (2025, 'not_found')]


def test_storage_failure_propagates_after_successful_download(monkeypatch):
    mock_reads(monkeypatch, lambda url: frame_for(vendor.SNAPS, [2024]))
    monkeypatch.setattr(ingest, 'ADVANCED_SOURCES', (vendor.SNAPS,))

    def fail(*args, **kwargs):
        raise RuntimeError('write failed')

    monkeypatch.setattr(ingest, '_upsert_by_season', fail)
    with pytest.raises(RuntimeError, match='write failed'):
        ingest.load_advanced_stats(object(), [2024])


@pytest.mark.parametrize('stage', ['DESCRIBE', 'DELETE'])
def test_upsert_storage_fault_does_not_create_or_append_after_error(stage):
    statements = []

    class FailedStorage:
        def register(self, *args):
            pass

        def execute(self, sql, *args):
            statements.append(sql)
            if sql.startswith(stage):
                raise RuntimeError('storage failed')
            return self

        def fetchall(self):
            return [('season', 'INTEGER')]

    with pytest.raises(RuntimeError, match='storage failed'):
        ingest._upsert_by_season(FailedStorage(), 'snap_counts', pd.DataFrame({'season': [2024]}), [2024])
    assert not any(sql.startswith(('CREATE', 'INSERT')) for sql in statements)


def test_reference_refresh_keeps_full_historical_window_for_old_request(monkeypatch):
    spec = next(s for s in vendor.SUPPLEMENTAL_SOURCES if s.name == 'draft_picks')
    mock_reads(monkeypatch, lambda url: frame_for(spec, [1980, 1999, 2024, 2030]))
    feed = vendor.fetch_vendor(spec, [1999])
    assert list(feed.data['season']) == [1980, 1999, 2024]
    assert feed.outcomes[0].season is None


def test_latest_depth_snapshot_and_legacy_formats_preserve_selection(monkeypatch):
    spec = next(s for s in vendor.SUPPLEMENTAL_SOURCES if s.name == 'depth_charts')

    def read(url):
        if '2024' in url:
            return pd.DataFrame({'season': [2024], 'old_rank': [1]})
        return pd.DataFrame({'dt': ['2025-09-01', '2025-09-02', '2025-09-02'], 'player': ['old', 'a', 'b']})

    mock_reads(monkeypatch, read)
    feed = vendor.fetch_vendor(spec, [2024, 2025])
    assert list(feed.data['player']) == ['a', 'b']
    assert [(o.season, o.status) for o in feed.outcomes] == [(2024, 'unsupported_format'), (2025, 'loaded')]
    assert feed.outcomes[-1].rows == 2


def test_ftn_real_parquet_matches_provider_normalization(tmp_path, monkeypatch):
    import nfl_data_py

    path = tmp_path / 'ftn.parquet'
    pd.DataFrame({'season': [2024], 'nflverse_game_id': ['game'],
                  'nflverse_play_id': [11.0], 'n_blitzers': [3.123456789],
                  'unused': ['discard']}).to_parquet(path, index=False)
    read = pd.read_parquet
    monkeypatch.setattr(vendor.pd, 'read_parquet', lambda url, **kwargs: read(path, **kwargs))
    feed = vendor.fetch_vendor(vendor.FTN, [2024])
    expected = nfl_data_py.import_ftn_data([2024]).drop(columns='unused').rename(
        columns={'nflverse_game_id': 'game_id', 'nflverse_play_id': 'play_id'})
    expected['play_id'] = expected['play_id'].astype('float64')
    pd.testing.assert_frame_equal(feed.data, expected)


def test_static_awards_failure_is_not_swallowed_as_an_optional_feed(monkeypatch):
    monkeypatch.setattr(ingest, 'SUPPLEMENTAL_SOURCES', ())

    def fail(*args, **kwargs):
        raise RuntimeError('awards seed failed')

    monkeypatch.setattr(ingest, '_load_player_awards', fail)
    with pytest.raises(RuntimeError, match='awards seed failed'):
        ingest.load_supplemental_data(object(), [2024])
