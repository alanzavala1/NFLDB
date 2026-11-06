"""Required schedule/roster downloads preserve provider behavior and source context."""
from urllib.error import HTTPError

import pandas as pd
import pytest

from pipeline import context_sources as context, loading, sources
from pipeline.source_results import SourceError, SeasonalFeed


def schedule(season):
    return pd.DataFrame({'season': [season], 'game_id': ['game'], 'week': [1],
                         'away_team': ['BUF'], 'home_team': ['MIA'],
                         'away_score': [None], 'home_score': [None]})


def test_schedule_matches_installed_provider_filter_without_network(monkeypatch):
    raw = pd.concat([schedule(2023), schedule(2024), schedule(2025)], ignore_index=True)
    def read(url):
        assert url == context.SCHEDULE_CSV
        return raw.copy()

    monkeypatch.setattr(context.pd, 'read_csv', read)
    expected = context.nfl_data_py.import_schedules([2023, 2025])
    feed = context.fetch_schedules([2023, 2025])
    pd.testing.assert_frame_equal(feed.data, expected)
    assert [(o.season, o.rows) for o in feed.outcomes('schedules')] == [(2023, 1), (2025, 1)]


def test_roster_real_parquet_keeps_provider_identity_dates_age_and_null_filter(tmp_path, monkeypatch):
    path = tmp_path / 'rosters.parquet'
    pd.DataFrame({'season': [2024, 2024, 2024], 'gsis_id': ['a', 'b', None],
                  'full_name': ['Alpha', 'Beta', 'Orphan'],
                  'birth_date': ['1990-05-03', '1998-09-01', None]}).to_parquet(path, index=False)
    read = pd.read_parquet
    monkeypatch.setattr(context.pd, 'read_parquet', lambda url: read(path))
    expected = context.nfl_data_py.import_seasonal_rosters([2024]).reset_index(drop=True)
    feed = context.fetch_rosters([2024])
    pd.testing.assert_frame_equal(feed.data, expected)
    assert list(feed.data['player_id']) == ['a', 'b']
    assert list(feed.data['age']) == [34, 25]  # Existing month-based provider rule.


def test_roster_missing_year_is_reported_without_discarding_other_year(monkeypatch):
    def roster(years):
        if years == [2027]:
            raise HTTPError('url', 404, 'not found', None, None)
        return pd.DataFrame({'season': years, 'player_id': ['p'], 'player_name': ['Player']})

    monkeypatch.setattr(context.nfl_data_py, 'import_seasonal_rosters', roster)
    feed = context.fetch_rosters([2024, 2027])
    assert feed.loaded_seasons == [2024] and feed.not_found_seasons == [2027]


@pytest.mark.parametrize('error', [TimeoutError('offline'), ValueError('bad frame'), NameError('provider bug')])
@pytest.mark.parametrize('source', ['schedules', 'rosters'])
def test_provider_failure_reports_source_and_original_cause(monkeypatch, source, error):
    def fail(*args):
        raise error

    if source == 'schedules':
        monkeypatch.setattr(context.pd, 'read_csv', fail)
    else:
        monkeypatch.setattr(context.nfl_data_py, 'import_seasonal_rosters', fail)
    fetch = context.fetch_schedules if source == 'schedules' else context.fetch_rosters
    with pytest.raises(SourceError, match=source) as caught:
        fetch([2024])
    assert caught.value.__cause__ is error


def test_schedule_missing_requested_year_is_not_successful_empty_data(monkeypatch):
    monkeypatch.setattr(context.pd, 'read_csv', lambda url: schedule(2023))
    with pytest.raises(SourceError, match='2024.*no schedule rows'):
        context.fetch_schedules([2024])


@pytest.mark.parametrize('source', ['schedules', 'rosters'])
def test_incomplete_schema_is_not_stored(monkeypatch, source):
    if source == 'schedules':
        monkeypatch.setattr(context.pd, 'read_csv', lambda url: pd.DataFrame({'season': [2024]}))
    else:
        monkeypatch.setattr(context.nfl_data_py, 'import_seasonal_rosters',
                            lambda years: pd.DataFrame({'season': years}))
    fetch = context.fetch_schedules if source == 'schedules' else context.fetch_rosters
    with pytest.raises(SourceError, match='missing required columns'):
        fetch([2024])


def test_missing_roster_for_played_season_stops_before_writes(monkeypatch):
    monkeypatch.setattr(loading, 'fetch_play_by_play',
                        lambda *a, **k: SeasonalFeed(pd.DataFrame({'season': [2024]}), [2024], []))
    monkeypatch.setattr(loading, 'fetch_schedules', lambda years: SeasonalFeed(schedule(2024), [2024], []))
    monkeypatch.setattr(loading, 'fetch_rosters', lambda years: SeasonalFeed(None, [], [2024]))
    monkeypatch.setattr(loading, 'upsert_by_season', lambda *a, **k: pytest.fail('invalid source reached storage'))
    with pytest.raises(SourceError, match='roster data is required'):
        loading.load_and_store_raw(object(), [2024])


def test_weekly_source_with_only_unidentified_players_blocks_played_year(monkeypatch):
    import duckdb
    from tests.test_weekly_columns import _feed_frame

    frame = _feed_frame(2024)
    frame['player_id'] = None
    monkeypatch.setattr(sources.pd, 'read_parquet', lambda url: frame)
    with duckdb.connect(':memory:') as conn:
        with pytest.raises(SourceError, match='no identified players'):
            loading.load_weekly_player_stats(conn, [2024], required_seasons=[2024])
        assert conn.execute('SHOW TABLES').fetchall() == []
