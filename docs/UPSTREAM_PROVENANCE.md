# Native source-version proof

The pinned R calculator reads three published RDS assets for each season:

| Native refresh key | Repository / release | Asset |
| --- | --- | --- |
| `pbp_rds` | `nflverse-data` / `pbp` | `play_by_play_YEAR.rds` |
| `weekly_rds` | `nflverse-data` / `stats_player` | `stats_player_week_YEAR.rds` |
| `playstats` | `nflverse-pbp` / `playstats` | `play_stats_YEAR.rds` |

The last feed supplies detailed player credits used by `calculate_stats`, even
when the caller supplies its own play-by-play. Watching only Python's parquet
feeds cannot establish which native inputs were consumed. Native refresh uses
these three keys plus the existing vendor keys; the legacy check is unchanged.

## Capture one season

From `api/`, with an installed, locked R environment and an absent output path:

```powershell
uv run --locked python -m jobs.capture_core --season 2026 `
  --output data/fresh-2026 `
  --rscript PATH_TO_RSCRIPT --r-library PATH_TO_LOCKED_LIBRARY
```

The command checks the R environment before downloading. It records each GitHub
asset's repository, release, filename, ID, update time, size and published SHA256,
then downloads and verifies the raw bytes. Missing assets or missing digests stop
the capture.

The existing receiving producer runs unchanged. Its saved RDS files have different
serialization/metadata from the downloaded files, so equality cannot be inferred
from their byte hashes. A separate pinned R check compares every typed column,
row order and row count with the downloaded asset. It ignores only frame-level
wrappers such as download timestamps and data.table self-reference pointers.
Another metadata observation must show that all three versions stayed unchanged.

Only then does Python bind the raw inputs, comparison script/result and
`upstream-proof.json` into the new receiving manifest. Conversion produces the
ordinary `core/` bundle; `capture.json` marks completion of this source-only job.
Failures retain diagnostic exports but cannot issue a completed core capture.
The job opens no database, advances no watermarks and publishes no release.

## Check and acknowledge

```powershell
uv run --locked python -m jobs.refresh native-check watermarks.json
```

This check watches RDS content identities, including the separate play-credit
feed. It reads no database and does not modify watermarks. It currently requires
all three native assets to be published; preseason schedules-only handling
remains part of the legacy workflow.

`jobs.refresh prepare` observes those versions before and after preparation. A
core mark advances only when a hash-verified proof matches the observed version
and the corresponding core sources were loaded for that season. Credits also
require both plays and weekly stats to be loaded. Changed, absent or unverified
sources retain their previous marks. The resulting map is staged inside the
validated release bundle; selection still publishes database and marks together.

Old captures remain usable for statistics. Without a proof they cannot advance
the new RDS keys, and RDS evidence never acknowledges the legacy parquet keys.
Archive packing automatically retains these manifest-declared proof files.

## Scope and next integration

This proves published input identity, not completeness of the NFL schedule or
every upstream statistic. Existing game-coverage, statistical and API validation
remain required. No availability rules or counting definitions change.

A fresh core bundle still needs a matching passing export and a new collection
that reuses the unaffected historical seasons. That full candidate build and
cloud capture transport/publication are separate steps. The scheduled workflow
still uses its legacy path; it has not been migrated or deployed.

## Local verification (October 28, 2026)

The real 2026 capture matched all three upstream assets: 18,738 play-by-play rows,
7,447 weekly-stat rows and 72,716 play-credit rows. The converted core bundle
passed all 17 receiving views (4,706 canonical rows), and its calculator/converter
policy matches the existing historical collection. A later metadata read still
matched all three proof versions.

Nine real R controls accept unchanged data and frame-only metadata changes, and
reject changed play/credit values, column types, row order, missing columns,
wrong seasons and wrong hashes. The related Python suites have 232 distinct
passing checks. Repeat the R controls against a completed receiving run with:

```powershell
& $rscript --vanilla r/test_upstream_inputs.R `
  data/fresh-2026/receiving data/new-upstream-controls $rscript $library
```

Evidence and captures remain ignored under `api/data/`; no serving database or
release selection changed.
