"""Offline refresh: isolated candidate, stable observed marks, immutable bundle."""
from pathlib import Path

import duckdb

from pipeline.refresh_tracking import acknowledged_watermarks
from pipeline.releases import create_release
from pipeline.snapshots import prepare_candidate, check_preparation
from pipeline.source_results import SourceOutcome


def prepare_refresh_release(source, candidate, output, seasons, *, core_inputs, passing_inputs,
                            previous_watermarks, observe, log=print):
    """No publication or mutation of previous marks. Select the bundle separately.

    Until per-season metadata has a stable leaf identity, rebuild all analytics
    against the new collection. Existing historical native exports are reused;
    this does not rerun R or silently retain old collection revision metadata.
    """
    seasons = sorted(set(seasons))
    before = {year: observe(year) for year in seasons}
    prepared = prepare_candidate(Path(source), Path(candidate), seasons, log=log,
                                 core_inputs=Path(core_inputs), passing_inputs=Path(passing_inputs),
                                 rebuild_all_analytics=True)
    with duckdb.connect(str(prepared), read_only=True) as conn:
        record = check_preparation(conn, seasons)
    outcomes = [SourceOutcome(**value) for value in record['source_outcomes']]
    marks = dict(previous_watermarks)
    for year in seasons:
        after = observe(year)
        marks = acknowledged_watermarks(marks, year, before[year], after, outcomes, captured_core=True)
    manifest = create_release(prepared, output, core_inputs=core_inputs, passing_inputs=passing_inputs,
                              watermarks=marks)
    log(f'Validated release bundle: {output}; current release selection is unchanged')
    return manifest
