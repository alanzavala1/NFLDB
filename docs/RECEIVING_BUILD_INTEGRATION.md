# Receiving build integration: shared core inputs

The [all-history receiving audit](RECEIVING_HISTORY_VALIDATION.md) validated the
official calculator's available-data results for 1999–2026. The first integration
checkpoint connects its captured **inputs** to the ordinary offline build.
Replacing the canonical receiving split rows is still pending. Converted runs
can now be grouped into one revision-bound collection for historical updates.

## Why this boundary comes first

The Python loader and the R receiving producer previously downloaded plays and
weekly player stats independently. If upstream files changed between downloads,
receiving qualification/splits could describe a different revision from the
stored plays, player-game rows and other analytics.

The producer already retains full PBP and weekly RDS files, fingerprints them,
and exports the receiving context and weekly reference. The new conversion
reads those captures without downloading replacements. The Python loader then
accepts the converted plays/weekly feeds as an explicit input.

```text
Captured full PBP + weekly RDS ── official receiving exports (existing preview)
             │
             └── explicit offline conversion ── typed, fingerprinted CSV bundle
                                                        │
                          jobs.prepare --core-inputs ────┘
                                       │
                          ordinary raw loader / player-game build
                                       │
                          existing analytics and full candidate gates
```

R remains outside request handling. Reading a prepared bundle does not execute
R or download plays/weekly data. Schedule, roster and optional vendor refreshes
still use their existing owners; their coherence/coverage checks remain part of
the subsequent integration work.

## Implemented guarantees

- Frozen conversion script, environment check and lock; RDS hashes checked
  before and after conversion. Source exports and databases are not modified.
- Column types and a collision-checked missing-value marker travel with CSVs.
  Missing values remain distinct from empty strings and literal `NA`/`null` text;
  IDs retain their original strings. CSVs are read from verified bytes.
- Before the loader's existing float32 PBP policy, the converted REG nonconversion
  context must match the receiving context by unique game/play key. Converted
  REG weekly rows must match the original weekly receiving reference by
  player/season/type/week. This checks values and population, not just grand totals.
- Core inputs retain postseason and two-point plays. Receiving context remains
  REG/nonconversion; passing/rushing and other consumers keep their existing scope.
- Both feeds are checked before context downloads/storage. Every required year
  must exist in the bundle. A legacy weekly-schema migration needs its whole
  historical range; missing captures fail rather than trigger a second download.
- `snapshot_preparation.source_outcomes` retains bundle and receiving-run SHA256
  references in the plays/weekly outcomes. Existing source-copy, failure cleanup,
  full statistical and HTTP validation remain in place.

The converter verifies the relationship between captures and receiving references;
it does **not** certify that the provider supplied every scheduled game. In
particular, the three 1999–2000 game gaps and partial 2026 surface coverage remain.
No missing-game allowance or full-validation tolerance was changed.

## Commands

From `api/`, after producing a completed receiving export and restoring the
locked R library (see [R setup](../api/r/README.md)):

```powershell
uv run --locked python -m jobs.receiving_core_inputs --exports data/receiving-history-current-20261024 --output data/receiving-core-current-20261025 --rscript data/upstream-r-trial/R-4.6.1/bin/Rscript.exe --r-library data/receiving-r-clean-20261023
```

Use a new output directory. Failed conversion logs remain there for diagnosis;
an existing output is refused. The original export directory must remain
available because reading the bundle verifies its captured-source revisions.

The ordinary build accepts `--core-inputs PATH` alongside its existing source,
candidate and season arguments. This option aligns inputs; it **does not switch
receiving split calculation**. The existing local source has a legacy weekly
table, so a 2026-only bundle cannot migrate that source: the full historical
weekly range is required. Do not bypass that check or the full candidate gate.
A bundle belongs to one receiving run, which may contain multiple seasons.
Group separate converted runs without copying or recalculating their data:

```powershell
uv run --locked python -m jobs.receiving_core_inputs --bundles data/receiving-core-1999-20261025 data/receiving-core-2000-20261025 --output data/receiving-core-example-collection
```

The example contains two seasons; a full historical migration needs the whole
required range. Pass the resulting collection directory to the same
`jobs.prepare --core-inputs PATH` option. Creating/reading a collection requires
no R executable. Keep its referenced bundles and original receiving exports.

The collection index lists absolute bundle paths, their exact completion-marker
hashes and disjoint season ownership. It refuses overlapping years and different
producer/split-definition/conversion/environment/lock/column policies. Every season's inputs and
receiving references are validated before a completion index is written. Later
reads recheck the index and child revisions; missing requested years fail before
any per-season table reads or fallback downloads.

The loader validates historical PBP one season at a time and retains only the
play seasons being refreshed. A weekly-schema migration can therefore load its
full history of weekly stats without concatenating all historical play frames.
Its required range includes newer weekly seasons already stored in an old
schema: refreshing an older year must not discard those newer rows when the
whole old table is replaced.

## Executed checks, October 25, 2026

Real locked R conversion and Python reference/identity checks succeeded for
1999, 2004, 2024 and 2026, reusing the earlier audit's exact captures:

| Season | Full core play rows | Supplied REG games | Postseason play rows | Full weekly rows |
|---|---:|---:|---:|---:|
| 1999 | 46,136 | 247 | 1,972 | 16,839 |
| 2004 | 46,705 | 256 | 1,912 | 17,272 |
| 2024 | 49,492 | 272 | 2,218 | 18,983 |
| 2026 | 16,551 | 94 | 0 | 6,558 |

These are representative boundary checks, not a repeat of all 476 receiving
view audits or a full real candidate acceptance run. 1999's missing game remains
missing. In 2004, the supplied REG weekly feed has only five recorded targets
despite 9,773 catches; the converter preserves the source and does not claim
those target values are complete.

The real 2026 loader and player-game composition ran in an in-memory DuckDB,
with PBP/weekly network fetches forbidden and stored schedules/rosters as local
controls. It stored all 16,551 plays and 6,551 identified weekly/player-game rows
(seven unidentified weekly rows dropped by the existing policy). Receptions,
receiving yards and TD checks all had zero mismatches. Source DB SHA256 remained
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`.

Deterministic regression checks exercise real typed CSVs, DuckDB writes and
candidate subprocesses: changed bytes/revisions, missing years, duplicate keys,
rebound but inconsistent values, legacy migration safety, metadata persistence,
postseason/conversion preservation, source immutability and failed-gate cleanup.
Synthetic lifecycle controls stub analytics/vendors; they do not certify real
analytics or HTTP responses for a receiving-integrated candidate.

The actual candidate CLI was also exercised against a new copy of the local
source with the 2026-only input bundle. It correctly rejected the legacy weekly
migration's missing 1999–2025 captures before source storage; the failed copy
and WAL were removed, and source bytes were unchanged. This is an intentional
coverage-guard check, not a successful full real candidate build.

The backend suite passed **1,083 tests with two skips**. After final input-marker
validation/error-message review, the 49 focused input, candidate-lifecycle and
ingestion-order checks also passed.

Ignored evidence lives in `api/data/receiving-core-{YEAR}-20261025/`, including
the 2026 `ingestion-proof.json`. Backend suite output lives in
`api/data/receiving-core-backend-tests-20261025.{log,xml}`; the intentional
candidate rejection is in `api/data/receiving-core-candidate-gate-20261025.log`.

## Next checkpoint

The historical input collection and core-only schema migration are now verified
as described below. Integrate the validated official receiving rows and their whole-season,
per-view and per-field coverage records into candidate preparation, preserving
passing/rushing behavior. Carry source gaps and NULLs through API/UI aggregation before
exposing new rows, then pass full real-data candidate/HTTP and downstream checks.
The preview rejection guard stays until that replacement is ready. No source
replacement, serving change, push or deployment is part of this checkpoint.

## Historical collection and migration check, October 25, 2026

All 28 saved runs, 1999–2026, were converted and independently matched back to
their bound receiving context/weekly references. They contain **1,296,179 full
PBP rows and 482,717 raw weekly rows**. No official split calculations or source
downloads were repeated. One collection now indexes the compatible converted
bundles, preserving every original run's revision.

A separate copy of the local source exercised the real raw loader and
player-game composition. Its first 2026 refresh performed the legacy weekly
schema replacement using all 28 years. Each historical play season was then
refreshed and composed individually from its captured inputs. PBP/weekly network
fetches were forbidden; schedules/rosters came from read-only stored controls.

Results:

- All **84 receiving-count checks** (catches, yards and TDs for 28 seasons)
  passed with zero mismatches, including preserved zero-target production.
- The copy holds 482,180 identified weekly rows after the existing orphan filter,
  and 482,216 composed player-game rows. Extra player-game rows include PBP-derived
  activity; these totals are not required to be identical.
- 7,058 supplied REG games remain represented. The known three missing games
  in 1999–2000 remain explicit, and conversion does not repair target/context gaps.
- Canonical `player_splits` rows match the source in both directions. Other
  analytics and the new receiving materializer were not rebuilt for this control.
- The source SHA256 stayed unchanged. The copied DB closed without a WAL and
  was deliberately marked as a preview. The unchanged full gate rejects it:
  `Receiving-only preview is not a publishable snapshot`.
- The final backend suite passed **1,099 tests, two skipped**. Collection tests
  cover ambiguous seasons, mixed policies, changed index/bundles/source bytes,
  missing years, scoped loading, old-schema replacement, newer-year preservation
  during an older refresh, and the ordinary candidate worker/CLI path.

Final review also tightened split-definition compatibility. The existing real
28-season index passed that check, and all 88 focused input/collection/ingestion
and candidate checks passed afterward. This review did not change data or calculations.

This proves the core-input migration, not full receiving integration or release
readiness. It does not certify fresh schedule/roster/vendor sources, derived
ratings/comparables, API/UI scope handling or a complete publishable candidate.

Ignored evidence:

- `api/data/receiving-core-history-conversions-20261025.{json,log}`: all 28
  conversion outcomes and original bundle hashes.
- `api/data/receiving-core-history-collection-20261025/run.json`: completed
  collection index, SHA256
  `237f23f204f7a85ef0a1ef70a92807d6e805f5e4ba7d7500b128a7dd4ef1c355`.
- `api/data/receiving-core-history-migration-preview-20261025.duckdb`: unpublishable
  core-only copy, with preview marker and per-season migration proof.
- `api/data/receiving-core-history-migration-proof-20261025.{json,log}`: source
  safety, per-season outcomes, missing-game references and zero-mismatch checks.
- `api/data/receiving-core-collection-final-tests-20261025.{xml,log}`: final suite.
