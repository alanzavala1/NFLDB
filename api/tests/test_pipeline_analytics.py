"""Offline preparation preserves seasonal scope and global calibration order."""
import importlib

import pandas as pd
import pytest

from pipeline.analytics import prepare_analytics
from pipeline.source_results import RawLoad, SourceOutcome


@pytest.fixture
def preparation_steps(monkeypatch):
    import database

    calls = []
    for name in (
        'team_analytics_builder', 'power_rankings_builder', 'game_ratings_builder',
        'ol_grades_builder', 'splits_builder', 'def_splits_builder',
        'team_splits_builder', 'comparables_builder',
    ):
        def record(*args, name=name):
            calls.append((name, args))
            return (7, 14) if name == 'comparables_builder' else 3
        monkeypatch.setattr(importlib.import_module(name), 'materialize', record)
    monkeypatch.setattr(database, 'ensure_indexes', lambda: calls.append(('indexes', ())))
    return calls


def test_seasonal_builds_keep_batch_scope_and_global_builds_run_once(preparation_steps):
    messages = []
    prepare_analytics([2023, 2026], log=messages.append)
    assert preparation_steps == [
        ('team_analytics_builder', (2023,)), ('team_analytics_builder', (2026,)),
        ('power_rankings_builder', (2023,)), ('power_rankings_builder', (2026,)),
        ('game_ratings_builder', ()), ('ol_grades_builder', ()),
        ('splits_builder', (2023,)), ('splits_builder', (2026,)),
        ('def_splits_builder', (2023,)), ('def_splits_builder', (2026,)),
        ('team_splits_builder', (2023,)), ('team_splits_builder', (2026,)),
        ('comparables_builder', ()), ('indexes', ()),
    ]
    assert '  team_season_analytics[2023]: 3 rows' in messages
    assert '  team_power_rankings[2026]: 3 rows' in messages
    assert '  player_career_summary: 7 players' in messages
    assert '  player_comparables:    14 rows' in messages
    assert messages[-1] == '\nDone.'


def test_failed_build_stops_preparation_before_later_builds_and_success_log(
    preparation_steps, monkeypatch,
):
    import power_rankings_builder

    def fail(season):
        raise RuntimeError('rankings build failed')

    monkeypatch.setattr(power_rankings_builder, 'materialize', fail)
    messages = []
    with pytest.raises(RuntimeError, match='rankings build failed'):
        prepare_analytics([2024], log=messages.append)
    assert preparation_steps == [('team_analytics_builder', (2024,))]
    assert '\nDone.' not in messages


@pytest.mark.parametrize('has_plays', [False, True])
@pytest.mark.parametrize('requested', [[2024], [2024, 2027]])
def test_ingest_prepares_only_after_source_and_player_stat_loading(monkeypatch, has_plays, requested):
    import ingest

    connection = object()
    plays = pd.DataFrame({'season': [2024]})
    calls = []
    monkeypatch.setattr(ingest, 'get_connection', lambda: connection)

    def load_raw(conn, seasons, log):
        assert conn is connection and seasons == requested
        calls.append('raw')
        return RawLoad(plays if has_plays else None, [SourceOutcome('schedules', 2024, 'loaded', 1)])

    def build_player_stats(conn, frame, seasons, log):
        assert conn is connection and frame is plays and seasons == [2024]
        calls.append('player_stats')

    monkeypatch.setattr(ingest, 'load_and_store_raw', load_raw)
    monkeypatch.setattr(ingest, 'build_player_game_stats', build_player_stats)
    for name in ('load_advanced_stats', 'load_supplemental_data'):
        def load(conn, seasons, log, name=name):
            assert conn is connection and seasons == [2024]
            calls.append(name)
            return []
        monkeypatch.setattr(ingest, name, load)

    def prepare(seasons, log):
        assert seasons == [2024]
        calls.append('analytics')

    monkeypatch.setattr(ingest, 'prepare_analytics', prepare)
    outcomes = ingest.run_ingest(requested, log=lambda message: None)
    assert outcomes == [SourceOutcome('schedules', 2024, 'loaded', 1)]
    assert calls == (['raw', 'player_stats', 'load_advanced_stats',
                      'load_supplemental_data', 'analytics'] if has_plays else ['raw'])
