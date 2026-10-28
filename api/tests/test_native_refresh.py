import pytest

from jobs import refresh
from pipeline.upstream_assets import CORE_ASSETS, asset_version
from tests.test_upstream_proof import published


def test_native_observer_watches_rds_and_credit_feed_instead_of_parquet(monkeypatch):
    from pipeline import upstream_assets
    calls = []
    def watched(year, assets):
        calls.extend(key for key,_,_ in assets)
        return {'snaps':'vendor-version'}
    monkeypatch.setattr(refresh,'_watched_watermarks',watched)
    metadata = {key:published(key) for key in CORE_ASSETS}
    monkeypatch.setattr(upstream_assets,'observe_core_assets',lambda year:metadata)
    result = refresh.native_remote_watermarks(2026)
    assert 'pbp' not in calls and 'weekly' not in calls
    assert result == {'snaps':'vendor-version',**{key:asset_version(value) for key,value in metadata.items()}}


@pytest.mark.parametrize('credit_changed',[False,True])
def test_native_check_detects_credit_updates_without_opening_or_writing_a_database(tmp_path,monkeypatch,capsys,credit_changed):
    import json
    previous = {f'{key}:2026':'same' for key in CORE_ASSETS}
    marks = tmp_path/'marks.json'
    marks.write_text(json.dumps(previous))
    original = marks.read_bytes()
    monkeypatch.setenv('REFRESH_SEASON','2026')
    monkeypatch.setenv('REFRESH_FORCE','0')
    monkeypatch.delenv('GITHUB_OUTPUT',raising=False)
    monkeypatch.setattr(refresh,'native_remote_watermarks',lambda year:{
        **dict.fromkeys(CORE_ASSETS,'same'),'playstats':'changed' if credit_changed else 'same'})
    monkeypatch.setattr(refresh,'remote_watermarks',lambda year:pytest.fail('legacy observer called'))
    assert refresh.main(['refresh','native-check',str(marks)]) == 0
    assert f'changed={str(credit_changed).lower()}' in capsys.readouterr().out
    assert marks.read_bytes() == original


def test_environment_check_runs_before_source_download_callback(tmp_path,monkeypatch):
    from pipeline import receiving_preview
    from pipeline import receiving_inputs, r_runtime
    events = []
    def environment(*args):events.append('environment')
    monkeypatch.setattr(receiving_preview,'_check_environment',environment)
    monkeypatch.setattr(receiving_inputs,'prepare_receiving_inputs',lambda *args:events.append('charting'))
    monkeypatch.setattr(r_runtime,'run_r_export',lambda *args,**kwargs:events.append('producer'))
    receiving_preview._run_export(tmp_path/'Rscript',tmp_path/'library',tmp_path,[2026],'run',
                                 before_export=lambda:events.append('raw-assets'))
    assert events == ['environment','raw-assets','charting','producer']
