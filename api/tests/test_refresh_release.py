"""A complete local refresh packages marks, but never changes the current release."""
from dataclasses import asdict
import json
from functools import cache

import duckdb
import pytest

from pipeline import refresh_release, releases
from pipeline.source_results import SourceOutcome
from pipeline.vendor_sources import WATCHED_VENDOR_SOURCES


def test_isolated_prepare_full_rebuild_and_stable_vendor_marks_are_bundled_together(tmp_path, monkeypatch):
    source, candidate, output = tmp_path/'source.duckdb', tmp_path/'candidate.duckdb', tmp_path/'release'
    source.write_bytes(b'unchanged published file')
    previous = {'pbp:2026':'old-capture', 'weekly:2026':'old-capture', 'snaps:2026':'old', 'pfr_pass:2026':'old'}
    observed = []
    def observe(year):
        observed.append(year)
        return {'pbp':'today', 'weekly':'today', 'snaps':'today', 'pfr_pass':'first' if len(observed)==1 else 'second'}
    def prepare(given_source, given_candidate, seasons, **options):
        assert given_source == source and given_candidate == candidate and seasons == [2026]
        assert options['rebuild_all_analytics'] is True
        assert options['core_inputs'] == tmp_path/'core' and options['passing_inputs'] == tmp_path/'passing'
        outcomes = []
        with duckdb.connect(str(candidate)) as conn:
            for table in ['schedules','plays','rosters','weekly_player_stats','player_game_stats']:
                conn.execute(f'CREATE TABLE {table} AS SELECT 2026 AS season')
                if table != 'player_game_stats': outcomes.append(SourceOutcome(table,2026,'loaded',1))
            outcomes.extend([SourceOutcome('snap_counts',2026,'loaded',1), SourceOutcome(WATCHED_VENDOR_SOURCES['pfr_pass'].name,2026,'loaded',1)])
            conn.execute('CREATE TABLE snapshot_preparation (format_version INTEGER,requested_seasons JSON,source_outcomes JSON)')
            conn.execute('INSERT INTO snapshot_preparation VALUES (1,?,?)', ['[2026]',json.dumps([asdict(item) for item in outcomes])])
        return candidate
    monkeypatch.setattr(refresh_release, 'prepare_candidate', prepare)
    monkeypatch.setattr(releases, '_validate', lambda *args: dict(publication_ready=True,
        official_receiving=True, official_passing=True, played_seasons=[2026],api_requests=['/api/seasons'],
        source_revisions={'core':'capture','passing':'exports'}))
    result = refresh_release.prepare_refresh_release(source,candidate,output,[2026],core_inputs=tmp_path/'core',
        passing_inputs=tmp_path/'passing',previous_watermarks=previous,observe=observe,log=lambda _:None)
    assert result['kind'] == 'native_nfl_release' and observed == [2026,2026]
    marks = json.loads((output/'watermarks.json').read_bytes())
    assert marks == {**previous,'snaps:2026':'today'}
    assert previous['snaps:2026'] == 'old' and source.read_bytes() == b'unchanged published file'
    assert not (tmp_path/'current.json').exists()


def test_failed_candidate_never_changes_previous_marks_or_creates_release(tmp_path,monkeypatch):
    previous = {'pbp:2026':'old'}
    def fail(*args,**kwargs): raise RuntimeError('source validation failed')
    monkeypatch.setattr(refresh_release,'prepare_candidate',fail)
    with pytest.raises(RuntimeError,match='source validation failed'):
        refresh_release.prepare_refresh_release(tmp_path/'old',tmp_path/'candidate',tmp_path/'release',[2026],
            core_inputs=tmp_path/'core',passing_inputs=tmp_path/'passing',previous_watermarks=previous,
            observe=lambda year:{'pbp':'new'})
    assert previous == {'pbp:2026':'old'} and not (tmp_path/'release').exists()


def test_prepare_cli_observes_remote_versions_fresh_each_time(tmp_path, monkeypatch):
    from jobs import refresh
    marks = tmp_path/'marks.json'
    marks.write_text('{"pbp:2026":"old"}')
    calls, observed = [], []
    versions = iter(['old-cached','before','after'])
    @cache
    def assets(tag):
        value = next(versions)
        calls.append(value)
        return {'pbp':value}
    assets('pbp')
    monkeypatch.setattr(refresh, '_release_assets', assets)
    def remote(year):
        result = refresh._release_assets('pbp')
        observed.append(result['pbp'])
        return result
    monkeypatch.setattr(refresh, 'remote_watermarks', remote)
    def prepare(*args, **options):
        assert options['previous_watermarks'] == {'pbp:2026':'old'}
        options['observe'](2026)
        options['observe'](2026)
    monkeypatch.setattr(refresh_release, 'prepare_refresh_release', prepare)
    assert refresh.main(['refresh','prepare',str(marks),'--source',str(tmp_path/'old'),
        '--candidate',str(tmp_path/'new'),'--release',str(tmp_path/'release'),'--seasons','2026',
        '--core-inputs',str(tmp_path/'core'),'--passing-inputs',str(tmp_path/'passing')]) == 0
    assert observed == ['before','after'] and calls == ['old-cached','before','after']
    assert json.loads(marks.read_bytes()) == {'pbp:2026':'old'}
