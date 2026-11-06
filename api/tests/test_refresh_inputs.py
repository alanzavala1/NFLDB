"""Season replacement must preserve historical identity and complete coverage."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import refresh_inputs
from pipeline.receiving_core_collection import assemble_core_inputs
from pipeline.receiving_preview import file_sha256
from tests.test_receiving_core_inputs import bundle
from tests.test_receiving_core_collection import copy_year


@pytest.fixture
def sources(bundle,tmp_path,monkeypatch):
    earlier = copy_year(bundle,tmp_path/'earlier',1999)
    base = assemble_core_inputs([earlier,bundle],tmp_path/'base-core',log=lambda _:None)
    fresh = copy_year(bundle,tmp_path/'fresh',2024)
    passing = tmp_path/'base-passing'
    passing.mkdir()
    (passing/'run.json').write_text('{}')
    old_exports = {year:tmp_path/f'old-passing-{year}' for year in base.seasons}
    fresh_export = tmp_path/'fresh-passing'
    fresh_export.mkdir()
    (fresh_export/'run.json').write_text('{"season":2024}')
    monkeypatch.setattr(refresh_inputs,'PassingInputs',lambda path:SimpleNamespace(
        directory=passing,seasons=base.seasons,exports={year:(path,'fixture') for year,path in old_exports.items()},
        manifest_sha256=file_sha256(passing/'run.json')))
    calls = []
    def assemble(paths,output,core,**options):
        calls.append((paths,core))
        output.mkdir()
        return SimpleNamespace(directory=output,seasons=core.seasons,revision=lambda:'validated passing fixture')
    monkeypatch.setattr(refresh_inputs,'assemble_passing_inputs',assemble)
    return base,passing,fresh,fresh_export,old_exports,calls


def test_replace_only_requested_season_preserves_history_and_old_indexes(sources,tmp_path):
    base,passing,fresh,export,old_exports,calls = sources
    before = {path:file_sha256(path/'run.json') for path in [base.directory,passing,*[i.directory for i in base.owners.values()]]}
    output = tmp_path/'combined'
    record = refresh_inputs.replace_input_seasons(base.directory,passing,fresh,[export],output,log=lambda _:None)
    assert record['seasons'] == [1999,2024] and record['refreshed_seasons'] == [2024]
    paths,combined_core = calls[0]
    assert paths == [old_exports[1999],export]
    assert combined_core.owners[1999].manifest_sha256 == base.owners[1999].manifest_sha256
    assert combined_core.owners[2024].directory == fresh
    assert {path:file_sha256(path/'run.json') for path in before} == before
    assert json.loads((output/'inputs.json').read_bytes()) == record
    assert record['publication_ready'] is False
    with pytest.raises(FileExistsError):
        refresh_inputs.replace_input_seasons(base.directory,passing,fresh,[export],output)


def test_can_add_a_new_season_without_discarding_existing_seasons(sources,tmp_path):
    base,passing,fresh,export,old_exports,calls = sources
    newer = copy_year(fresh,tmp_path/'new-year',2025)
    (export/'run.json').write_text('{"season":2025}')
    record = refresh_inputs.replace_input_seasons(base.directory,passing,newer,[export],tmp_path/'combined',log=lambda _:None)
    assert record['seasons'] == [1999,2024,2025]
    assert calls[0][0] == [old_exports[1999],old_exports[2024],export]


@pytest.mark.parametrize('fault',['missing','duplicate','wrong_season','incomplete_history'])
def test_invalid_replacement_is_rejected_before_output_is_created(sources,tmp_path,monkeypatch,fault):
    base,passing,fresh,export,_,_ = sources
    exports = [export]
    if fault == 'missing': exports = []
    if fault == 'duplicate':exports = [export,export]
    if fault == 'wrong_season':(export/'run.json').write_text('{"season":2025}')
    if fault == 'incomplete_history':
        original = refresh_inputs.PassingInputs
        def incomplete(path):
            value=original(path);value.seasons=[2024];return value
        monkeypatch.setattr(refresh_inputs,'PassingInputs',incomplete)
    output = tmp_path/'combined'
    with pytest.raises(ValueError):
        refresh_inputs.replace_input_seasons(base.directory,passing,fresh,exports,output)
    assert not output.exists()


def test_partial_multi_season_bundle_cannot_drop_an_unreplaced_season(sources,tmp_path,monkeypatch):
    base,passing,fresh,export,_,_ = sources
    original = refresh_inputs._bundles
    monkeypatch.setattr(refresh_inputs,'_bundles',lambda value:[SimpleNamespace(
        directory=base.directory,seasons=[1999,2024])] if value.directory==base.directory else original(value))
    with pytest.raises(ValueError,match='every season'):
        refresh_inputs.replace_input_seasons(base.directory,passing,fresh,[export],tmp_path/'combined')
    assert not (tmp_path/'combined').exists()


def test_late_passing_failure_cannot_complete_a_pair(sources,tmp_path,monkeypatch):
    base,passing,fresh,export,_,_ = sources
    original = file_sha256(base.directory/'run.json')
    def fail(*args,**options):raise ValueError('passing source mismatch')
    monkeypatch.setattr(refresh_inputs,'assemble_passing_inputs',fail)
    with pytest.raises(ValueError,match='source mismatch'):
        refresh_inputs.replace_input_seasons(base.directory,passing,fresh,[export],tmp_path/'combined')
    assert not (tmp_path/'combined/inputs.json').exists()
    assert file_sha256(base.directory/'run.json') == original
