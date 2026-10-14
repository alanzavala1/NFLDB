"""Core feed failures are distinct from absent assets and never erase stored seasons."""
from urllib.error import HTTPError

import duckdb
import pandas as pd
import pytest

import ingest
from pipeline import sources
from tests.test_weekly_columns import _feed_frame


def missing(url):
    return HTTPError(url, 404, 'not found', None, None)


def test_real_historical_parquet_projection_and_precision_match_provider(tmp_path, monkeypatch):
    import nfl_data_py

    path = tmp_path / 'plays.parquet'
    pd.DataFrame({
        'game_id': ['2024_01_BUF_MIA'], 'play_id': [1.0], 'week': [1],
        'epa': [0.123456789012], 'unused_column': ['discard'],
    }).to_parquet(path, index=False)
    read = pd.read_parquet
    calls = []

    def local_asset(url, **kwargs):
        calls.append(kwargs.get('columns'))
        return read(path, **kwargs)

    monkeypatch.setattr(sources.pd, 'read_parquet', local_asset)
    feed = sources.fetch_play_by_play([2024], log=lambda _: None)
    assert len(calls) == 2 and calls[0] and calls[1] is None
    assert 'season' not in calls[0] and 'route' not in calls[0]
    assert 'nflverse_game_id' not in calls[0]
    # Use the installed provider on the same local parquet, with no network.
    provider = nfl_data_py.import_pbp_data([2024], include_participation=False)
    expected = provider[[c for c in sources.PLAYS_KEEP_COLUMNS if c in provider.columns]]
    pd.testing.assert_frame_equal(feed.data, expected)
    assert str(feed.data['epa'].dtype) == 'float32'
    assert feed.loaded_seasons == [2024] and feed.not_found_seasons == []


def test_mixed_play_seasons_report_actual_availability(monkeypatch):
    def read(url, **kwargs):
        if '2027' in url:
            raise missing(url)
        return pd.DataFrame({'game_id': ['game'], 'play_id': [1.0], 'week': [1]})

    monkeypatch.setattr(sources.pd, 'read_parquet', read)
    feed = sources.fetch_play_by_play([2024, 2027])
    assert feed.loaded_seasons == [2024]
    assert feed.not_found_seasons == [2027]
    assert list(feed.data['season']) == [2024]


@pytest.mark.parametrize('fetch', [sources.fetch_play_by_play, sources.fetch_weekly_stats])
def test_actual_404_is_an_explicit_missing_asset(monkeypatch, fetch):
    def read(url, **kwargs):
        raise missing(url)

    monkeypatch.setattr(sources.pd, 'read_parquet', read)
    result = fetch([2027])
    assert result.data is None and result.loaded_seasons == []
    assert result.not_found_seasons == [2027]


@pytest.mark.parametrize('fetch', [sources.fetch_play_by_play, sources.fetch_weekly_stats])
@pytest.mark.parametrize('error', [
    TimeoutError('timed out'), OSError('404 in a message is not an HTTP status'),
    ValueError('invalid parquet file'), HTTPError('url', 503, 'unavailable', None, None),
    NameError('provider bug'),
])
def test_download_faults_stop_instead_of_becoming_missing_data(monkeypatch, fetch, error):
    calls = []

    def read(url, **kwargs):
        calls.append(url)
        raise error

    monkeypatch.setattr(sources.pd, 'read_parquet', read)
    with pytest.raises(sources.SourceError, match=r'\[2024\]') as caught:
        fetch([2024])
    assert caught.value.season == 2024
    assert caught.value.__cause__ is error
    assert len(calls) == 1, 'only missing projected columns warrant a full-file retry'


@pytest.mark.parametrize('fetch', [sources.fetch_play_by_play, sources.fetch_weekly_stats])
def test_empty_published_asset_is_a_failure(monkeypatch, fetch):
    monkeypatch.setattr(sources.pd, 'read_parquet', lambda *a, **k: pd.DataFrame())
    with pytest.raises(sources.SourceError, match='published asset returned no rows'):
        fetch([2024])


def test_weekly_schema_is_checked_per_season_before_concat(monkeypatch):
    def read(url):
        frame = _feed_frame(2024 if '2024' in url else 2025)
        return frame if '2024' in url else frame.drop(columns='passing_epa')

    monkeypatch.setattr(sources.pd, 'read_parquet', read)
    with pytest.raises(sources.SourceError, match=r'2025.*passing_epa'):
        sources.fetch_weekly_stats([2024, 2025])


def test_wrong_season_payload_is_not_inserted_under_requested_year(monkeypatch):
    monkeypatch.setattr(sources.pd, 'read_parquet', lambda url: _feed_frame(2025))
    with pytest.raises(sources.SourceError, match='unexpected seasons'):
        sources.fetch_weekly_stats([2024])


@pytest.mark.parametrize('action', [ingest._weekly_schema_is_legacy, ingest.build_offensive_stats_from_weekly])
def test_weekly_storage_fault_is_not_an_absent_table_fallback(action):
    class FailedReader:
        def execute(self, *args):
            raise RuntimeError('storage unavailable')

    with pytest.raises(RuntimeError, match='storage unavailable'):
        if action is ingest._weekly_schema_is_legacy:
            action(FailedReader())
        else:
            action(FailedReader(), [2024])


def test_network_failure_leaves_weekly_storage_unchanged(monkeypatch):
    with duckdb.connect(':memory:') as conn:
        conn.register('seed', _feed_frame(2024))
        conn.execute('CREATE TABLE weekly_player_stats AS SELECT * FROM seed')

        def read(url):
            if '2024' in url:
                return _feed_frame(2024, week=2)
            raise TimeoutError('weekly download failed')

        monkeypatch.setattr(sources.pd, 'read_parquet', read)
        with pytest.raises(sources.SourceError, match='2025'):
            ingest.load_weekly_player_stats(conn, [2024, 2025])
        assert conn.execute('SELECT season, week FROM weekly_player_stats').fetchall() == [(2024, 1)]


def test_missing_required_weekly_asset_blocks_played_season(monkeypatch):
    def read(url):
        raise missing(url)

    monkeypatch.setattr(sources.pd, 'read_parquet', read)
    with duckdb.connect(':memory:') as conn:
        with pytest.raises(sources.SourceError, match='official stats are required'):
            ingest.load_weekly_player_stats(conn, [2024], required_seasons=[2024])
        assert conn.execute('SHOW TABLES').fetchall() == []


def test_incomplete_legacy_download_does_not_drop_old_history(monkeypatch):
    with duckdb.connect(':memory:') as conn:
        conn.execute('CREATE TABLE weekly_player_stats (season INTEGER, recent_team VARCHAR)')
        conn.execute("INSERT INTO weekly_player_stats VALUES (2024, 'KC')")
        monkeypatch.setattr(ingest, 'FIRST_SEASON', 2023)

        def read(url):
            if '2023' in url:
                return _feed_frame(2023)
            raise missing(url)

        monkeypatch.setattr(sources.pd, 'read_parquet', read)
        with pytest.raises(sources.SourceError, match='legacy schema rebuild is incomplete'):
            ingest.load_weekly_player_stats(conn, [2024])
        assert conn.execute('SELECT * FROM weekly_player_stats').fetchall() == [(2024, 'KC')]


@pytest.mark.parametrize('completed', [False, True])
def test_missing_plays_are_allowed_only_for_unplayed_season(monkeypatch, completed):
    monkeypatch.setattr(ingest, 'fetch_play_by_play', lambda *a, **k: sources.SeasonalFeed(None, [], [2027]))
    monkeypatch.setattr(ingest.nfl_data_py, 'import_schedules', lambda years: pd.DataFrame({
        'season': [2027], 'away_score': [7 if completed else None],
        'home_score': [14 if completed else None],
    }))
    monkeypatch.setattr(ingest.nfl_data_py, 'import_seasonal_rosters',
                        lambda years: pd.DataFrame({'season': [2027], 'player_id': ['p']}))
    calls = []
    monkeypatch.setattr(ingest, '_upsert_by_season', lambda *a, **k: calls.append(a[1]))

    def weekly(conn, years, log, *, required_seasons):
        assert required_seasons == []
        calls.append('weekly')

    monkeypatch.setattr(ingest, 'load_weekly_player_stats', weekly)
    if completed:
        with pytest.raises(sources.SourceError, match='completed games'):
            ingest.load_and_store_raw(object(), [2027])
        assert calls == []
    else:
        assert ingest.load_and_store_raw(object(), [2027]) is None
        assert calls == ['schedules', 'rosters', 'weekly']


def test_partial_play_download_never_replaces_unavailable_season(monkeypatch):
    plays = pd.DataFrame({'season': [2024]})
    monkeypatch.setattr(ingest, 'fetch_play_by_play',
                        lambda *a, **k: sources.SeasonalFeed(plays, [2024], [2027]))
    monkeypatch.setattr(ingest.nfl_data_py, 'import_schedules', lambda years: pd.DataFrame({
        'season': [2024, 2027], 'away_score': [7, None], 'home_score': [14, None],
    }))
    monkeypatch.setattr(ingest.nfl_data_py, 'import_seasonal_rosters',
                        lambda years: pd.DataFrame({'season': [2024, 2027]}))
    replacements = []
    monkeypatch.setattr(ingest, '_upsert_by_season',
                        lambda conn, table, frame, years, **k: replacements.append((table, years)))
    monkeypatch.setattr(ingest, 'load_weekly_player_stats', lambda *a, **k: None)
    ingest.load_and_store_raw(object(), [2024, 2027])
    assert replacements == [('plays', [2024]), ('schedules', [2024, 2027]), ('rosters', [2024, 2027])]
