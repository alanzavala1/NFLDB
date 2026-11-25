# Calculator producers and audits

This directory contains the R producers used by offline preparation and Python
utilities for checking their output. It also retains a small independent receiving
credit implementation used by regression fixtures.

| File | Purpose |
|---|---|
| `upstream_receiving_splits.R` | Capture receiving inputs and run the official calculator on play subsets |
| `upstream_passing_down.R` | Export passing whole/bucket references for requested dimensions |
| `receiving_history_sources.R` | Extract independent audit controls from captured inputs and schedule data |
| `receiving_history_audit.py` | Check receiving preview counts, context, metrics and game coverage |
| `receiving_credits.py` | Aggregate detailed receiving credits and join them to game/play context |
| `evaluate_upstream_receiving_splits.py` | Compare saved receiving exports with weekly totals and credit replay |
| `receiving_partition_controls.R` | Generate partition controls for calculator checks |

Use the Python jobs to run calculator producers; they bind the scripts,
[locked R environment](../r/README.md), inputs and output hashes. Keep generated
artifacts under ignored `api/data/`.

## Receiving diagnostic

From `api/`, with a closed source database and new output paths:

```sh
uv run --locked python -m jobs.receiving_preview \
  --source data/source.duckdb --candidate data/receiving-preview.duckdb \
  --exports data/receiving-exports --seasons 2026 \
  --rscript PATH_TO_RSCRIPT --r-library PATH_TO_LOCKED_LIBRARY

uv run --locked python -m experiments.receiving_history_audit \
  --source data/source.duckdb --candidate data/receiving-preview.duckdb \
  --exports data/receiving-exports --season 2026 \
  --rscript PATH_TO_RSCRIPT --r-library PATH_TO_LOCKED_LIBRARY
```

Examples use Bash continuations. The independent audit can fetch schedule/control
inputs on its first run. Exit 0 means its available-data and game-coverage checks
pass; exit 2 means calculations pass but game coverage is incomplete. Other
nonzero exits indicate failure. Results are written to `audit-result.json`.
Do not use Python `-O`, which disables the audit's assertions.

A receiving preview is not a publishable database: it does not coherently rebuild
all other analytics. Use the [release workflow](../../docs/OFFLINE_RELEASES.md)
for production preparation.

## Fixture checks

```sh
uv run --locked pytest tests/test_receiving_credit_pilot.py
```

Fixtures cover negative catches, repeated lateral credits, conversions, missing
context and cross-game play IDs. Credit replay preserves raw repeated records;
it does not deduplicate them into one player/stat row. Observed target credits
are not proof of complete historical targets.

See [receiving definitions and validation](../../docs/RECEIVING_RELEASE_VALIDATION.md)
and [passing definitions](../../docs/PASSING_RELEASE_VALIDATION.md).
