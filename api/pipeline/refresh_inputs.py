"""Replace complete seasonal captures in a new, validated pair of collections."""
import json
from pathlib import Path

from pipeline.passing_inputs import PassingInputs, assemble_passing_inputs
from pipeline.receiving_core_collection import open_core_inputs, assemble_core_inputs
from pipeline.receiving_preview import file_sha256


def _bundles(inputs):
    values = inputs.owners.values() if hasattr(inputs, 'owners') else [inputs]
    return {item.directory: item for item in values}.values()


def replace_input_seasons(core_inputs, passing_inputs, fresh_core, fresh_passing, output, *, log=print):
    """Reuse historical bytes, validate every season, write pair marker last.

    No source edits, downloads, R execution, DB writes or publication. Refuse a
    partial replacement of a multi-season bundle rather than dropping history.
    """
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    base, passing = open_core_inputs(Path(core_inputs)), PassingInputs(Path(passing_inputs))
    fresh = open_core_inputs(Path(fresh_core))
    if base.seasons != passing.seasons:
        raise ValueError('Existing core and passing collections must cover the same seasons')
    replacements = set(fresh.seasons)
    remaining = []
    for bundle in _bundles(base):
        overlap = replacements.intersection(bundle.seasons)
        if overlap and overlap != set(bundle.seasons):
            raise ValueError('Replace every season of an overlapping multi-season core bundle')
        if not overlap:
            remaining.append(bundle.directory)
    exports = {}
    for directory in fresh_passing:
        directory = Path(directory).resolve()
        year = json.loads((directory/'run.json').read_bytes()).get('season')
        if type(year) is not int or year not in replacements or year in exports:
            raise ValueError('Fresh passing exports must cover exactly the fresh core seasons without duplicates')
        exports[year] = directory
    if set(exports) != replacements:
        raise ValueError('Provide one fresh passing export for every fresh core season')
    exports = {**{year: path for year, (path, _) in passing.exports.items() if year not in replacements}, **exports}
    expected = sorted(set(base.seasons) | replacements)
    output.mkdir()
    core = assemble_core_inputs([*remaining, *(item.directory for item in _bundles(fresh))], output/'core', log=log)
    combined = assemble_passing_inputs([exports[year] for year in sorted(exports)], output/'passing', core, log=log)
    if core.seasons != expected or combined.seasons != expected:
        raise ValueError('Combined collections lost season coverage')
    for source in (base, passing, fresh):
        if file_sha256(source.directory/'run.json') != source.manifest_sha256:
            raise ValueError('Source collection changed during composition')
    record = dict(format_version=1, kind='native_refresh_inputs', refreshed_seasons=sorted(replacements),
                  seasons=expected, core=str(core.directory), passing=str(combined.directory),
                  core_revision=core.revision(), passing_revision=combined.revision(), publication_ready=False)
    with (output/'inputs.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    log(f'Validated input pair: {output}; database preparation remains separate')
    return record
