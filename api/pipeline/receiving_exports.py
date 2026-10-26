"""One acceptance path for official receiving exports in previews and builds."""
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pipeline.receiving_dimensions import DIMENSIONS
from pipeline.receiving_inputs import verify_receiving_inputs
from pipeline.receiving_preview_validation import load_receiving_preview_partition, validate_whole_receiving
from pipeline.receiving_qualification import qualify_receiving_context
from pipeline.receiving_splits import COUNT_COLUMNS, adapt_receiving_overall, read_export_csv, validate_export_manifest
from pipeline.snapshots import CandidateError
from services.receiving_coverage import targets_unavailable, yac_unavailable


@dataclass
class ReceivingSeason:
    rows: dict[str, pd.DataFrame]
    reference: pd.DataFrame
    totals: pd.DataFrame
    exclusions: dict
    qualification: dict
    whole: dict
    dimensions: dict


def load_receiving_season(directory: Path, manifest: dict, season: int, *, require_qualified=False) -> ReceivingSeason:
    """Verify shared inputs and every partition before any caller writes rows."""
    validate_export_manifest(manifest, season)
    weekly = read_export_csv(directory, manifest, f"weekly-{season}.csv", season=season)
    overall = read_export_csv(directory, manifest, f"overall-{season}.csv", season=season)
    context = read_export_csv(directory, manifest, f"context-{season}.csv", season=season)
    ftn = verify_receiving_inputs(directory, manifest, context, season)
    qualified, qualification = qualify_receiving_context(context, season, manifest["files"][f"context-{season}.csv"])
    if require_qualified and not qualified:
        raise CandidateError(f"receiving[{season}]: no qualified players for preview")
    whole = validate_whole_receiving(overall, weekly, season, qualified)
    whole["source_revisions"] = {name: manifest["files"][name] for name in
                                 (f"overall-{season}.csv", f"weekly-{season}.csv")}
    rows, dimensions, exclusions = {}, {}, {player: {} for player in qualified}
    for dimension in DIMENSIONS:
        rows[dimension], report = load_receiving_preview_partition(
            directory, manifest, context=context, overall=overall, season=season,
            dimension=dimension, qualified=qualified,
        )
        if dimension in ("play_action", "blitz"):
            report["coverage"]["charting_source"] = ftn
            if ftn["status"] != "loaded":
                report["coverage"]["reason"] = f"FTN {ftn['status']}: {ftn.get('detail', '')}".rstrip(": ")
        dimensions[dimension] = report
        # Preserve independently checked excluded credits per player. Serving
        # must not reinterpret an accidentally missing split row as a source gap.
        omitted = read_export_csv(directory, manifest, f"excluded-{dimension}-{season}.csv", season=season)
        omitted = omitted.set_index("player_id")[list(COUNT_COLUMNS)].reindex(
            qualified, fill_value=0).rename(columns=COUNT_COLUMNS)
        for player, values in omitted.iterrows():
            exclusions[player][dimension] = {field: (None if (
                field == "att" and targets_unavailable([season]) or field == "yac" and yac_unavailable([season])
            ) else int(value)) for field, value in values.items()}
    totals = adapt_receiving_overall(overall, context=context, season=season, qualified_players=qualified)
    if set(totals.player_id) != set(qualified):
        raise CandidateError(f"receiving[{season}]: qualified player missing from whole totals")
    return ReceivingSeason(rows, overall.loc[overall.player_id.isin(qualified)].copy(),
                            totals, exclusions, qualification, whole, dimensions)
