"""Only successful consumption of a stable observed version advances its mark."""
import pytest

from pipeline.refresh_tracking import acknowledged_watermarks
from pipeline.source_results import SourceOutcome


@pytest.mark.parametrize('status,advanced', [('loaded',True),('empty',True),('failed',False),('not_found',False),('unsupported',False)])
def test_vendor_status_controls_acknowledgment(status, advanced):
    previous = {'snaps:2026':'old'}
    result = acknowledged_watermarks(previous, 2026, {'snaps':'new'}, {'snaps':'new'}, [SourceOutcome('snap_counts',2026,status)])
    assert result == {'snaps:2026':'new' if advanced else 'old'}
    assert previous == {'snaps:2026':'old'}


def test_changes_during_build_and_unobserved_sources_keep_previous_marks():
    result = acknowledged_watermarks({'snaps:2026':'old'},2026,{'snaps':'before','weekly':'same'},
        {'snaps':'after','weekly':'same'},[SourceOutcome('snap_counts',2026,'loaded')])
    assert result == {'snaps:2026':'old'}


def test_captured_core_never_claims_today_upstream_files_were_downloaded():
    outcomes = [SourceOutcome('plays',2026,'loaded'),SourceOutcome('weekly_player_stats',2026,'loaded'),
                SourceOutcome('snap_counts',2026,'loaded')]
    stamps = {'pbp':'today','weekly':'today','snaps':'today'}
    result = acknowledged_watermarks({'pbp:2026':'captured-old'},2026,stamps,stamps,outcomes,captured_core=True)
    assert result == {'pbp:2026':'captured-old','snaps:2026':'today'}


def test_live_core_requires_a_loaded_outcome_and_matching_season():
    outcomes = [SourceOutcome('plays',2026,'loaded'),SourceOutcome('weekly_player_stats',2025,'loaded')]
    stamps = {'pbp':'new','weekly':'new'}
    assert acknowledged_watermarks({},2026,stamps,stamps,outcomes) == {'pbp:2026':'new'}


def test_native_proof_versions_acknowledge_only_stable_loaded_sources():
    outcomes = [SourceOutcome('plays',2026,'loaded'),SourceOutcome('weekly_player_stats',2026,'loaded')]
    stamps = {'pbp_rds':'pbp','weekly_rds':'weekly','playstats':'credits','pbp':'parquet'}
    proof = {key:stamps[key] for key in ('pbp_rds','weekly_rds','playstats')}
    after = {**stamps,'playstats':'republished'}
    assert acknowledged_watermarks({},2026,stamps,after,outcomes,captured_core=True,core_versions=proof) == {
        'pbp_rds:2026':'pbp','weekly_rds:2026':'weekly'}
    assert acknowledged_watermarks({},2026,stamps,stamps,outcomes,captured_core=True) == {}
    assert acknowledged_watermarks({},2025,stamps,stamps,outcomes,core_versions=proof) == {}
