# Receiving build integration: shared core inputs

The [all-history receiving audit](RECEIVING_HISTORY_VALIDATION.md) validated the
official calculator's available-data results for 1999–2026. The first integration
checkpoint connects its captured **inputs** to the ordinary offline build.
Replacing the canonical receiving split rows is still pending.

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
A bundle currently belongs to one receiving run, which may contain multiple
seasons; combining the existing separate per-season audit runs is not yet supported.

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

Integrate the validated official receiving rows and their whole-season,
per-view and per-field coverage records into candidate preparation, preserving
passing/rushing behavior. Plan for the legacy full-history migration and its
bound inputs. Carry source gaps and NULLs through API/UI aggregation before
exposing new rows, then pass full real-data candidate/HTTP and downstream checks.
The preview rejection guard stays until that replacement is ready. No source
replacement, serving change, push or deployment is part of this checkpoint.
