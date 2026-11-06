# Receiving build integration

The [all-history receiving audit](RECEIVING_HISTORY_VALIDATION.md) validated the
official calculator's available-data results for 1999–2026. The ordinary offline
build now accepts its captured inputs and official receiving exports. Its player
split materializer replaces receiving rows and saves whole-reference, per-view
and metric-availability records. Passing/rushing keep their existing SQL.

This is an **offline integration**, not a publishable snapshot. The full gate
rejects the new receiving marker until integration and receiving-aware release
validation are ready. API/UI handling and a coordinated offline rebuild are now
connected locally; complete receiving-aware release checks remain outstanding.
No serving database was replaced.

The latest [complete snapshot diagnostic](RECEIVING_RELEASE_VALIDATION.md) now
composes the source-bound receiving checks with the other release checks.
Receiving passes, but a 2004 passing attribution case still fails; the official
publication guard remains in place.

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
                          analytics / player split materializer
                                       │
                  official receiving exports + coverage/reference records
                                       │
                          full candidate gates (still reject integration)
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
candidate and season arguments. This now aligns inputs **and selects the official
receiving path**. The existing local source has a legacy weekly
table, so a 2026-only bundle cannot migrate that source: the full historical
weekly range is required. Do not bypass that check or the full candidate gate.
For the first official receiving migration, refresh the full intended play history
as well: copied older plays must match their captured source before receiving
rows can be replaced. The command still removes candidates rejected by its full
gate, so it cannot publish or retain an accepted receiving integration yet.
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

## Coordinated refresh, October 26, 2026

The previous development copy mixed 94 captured 2026 games with analytics from
two games. A new owned copy refreshes current-season inputs before rebuilding
analytics. It does not replace that copy or the original serving database.

The pinned R environment produced a fresh 2026 capture and all 17 receiving
views. Conversion reused those captured RDS files without downloading core data
again. The new collection combines this bundle with the unchanged 1999–2025
bundles. The normal adapters refresh 2026 schedules and rosters alongside it.
The stored schedule and captured PBP now agree on **106 completed REG games**,
with no current-season missing or unconfirmed game IDs. This describes the
captured revision, not a promise that an upstream feed is permanently current.

`--rebuild-all-analytics` is an explicit preparation option forwarded through
`jobs.prepare`, its snapshot wrapper and the isolated worker. It refreshes
advanced inputs and rebuilds seasonal analytics for every stored REG season;
global ratings, O-line calibration and career comparables run once per batch.
Only requested core seasons are downloaded. Supplemental seasonal feeds keep
that requested scope. Unchanged historical player-game rows are not rebuilt
automatically; ordinary play/weekly replacement still owns their rebuild trigger.

For a captured full rebuild, `receiving_inputs.verify_stored_ftn` checks the
stored feed against every bound receiving capture before analytics run. It
compares game/play keys, play-action flags and pass-rusher counts, including
empty expected feeds. Extra full-feed fields remain available to other
calculations. Conflicting retained charting after an outage fails preparation.
This makes shared charting agreement explicit without replacing the full feed
with the receiving producer's five-column projection.

The broader HTTP proof found a historical source-name bug: the weekly composer
selected the display-name column whenever it existed, even when an individual
row only had an abbreviated name. It now chooses the first nonblank display/
abbreviated name, then the player ID when neither is supplied. The affected
1999–2000 player-game rows were rebuilt offline; every key and non-name statistic
was checked for exact preservation before rebuilding dependent analytics.

The development rebuild uses the internal worker so evidence can be retained
while publication remains intentionally blocked. It is not a supported way to
promote a snapshot: the outer `jobs.prepare` still validates and deletes failed
candidates, and `jobs.validate` still rejects the official integration marker.
The release validator must adopt the receiving source-bound rules and complete
the broader release checks before that guard can be removed.

Ignored local artifacts:

- `api/data/receiving-current-refresh-exports-20261026/`
- `api/data/receiving-current-refresh-core-20261026/`
- `api/data/receiving-refreshed-history-collection-20261026/`
- `api/data/coordinated-analytics-refresh-20261026.duckdb`
- `api/data/coordinated-analytics-refresh-20261026.log`
- `api/data/coordinated-refresh-name-repair-20261026.log`

The captured manifest SHA256 is
`4f5c86f5ddb4859ebc4dddb64b7cda4f4048096220ba212c1f982758280173b2`;
the current core bundle is
`be3bc34bfb963b9da79c120618bd473fdce1a7563ed5dc1b00f26c057373f0a8`;
the full collection is
`5f3256729f31ec39d80143fd47eaf488725d58d97ee004a783e9dec53bc211e9`.

### Coordinated rebuild checks

The read-only development proof passed prepared-table schemas and lookup keys,
finite/bounded ratings and grades, split-rate sanity, and game coverage for all
28 stored REG seasons. All **106** current supplied games appear in player-game
stats, player ratings and O-line grades. Current team analytics have 32 teams,
power rankings have 224 team/week rows, team splits have 2,238 rows, and defensive
splits have 12,989 rows. These tables were rebuilt together; coverage counts
alone would not establish that provenance.

All **73 representative HTTP requests** passed, including the 56 receiving
requests. Every historical receiving split row and every historical player-game
key/statistic matched the earlier verified copy exactly, excluding the intended
player-name repair. Source/previous-development/candidate hashes stayed unchanged
during the read-only proof, and all three closed files had no pending WAL.
The original and previous development hashes above are unchanged. The new
candidate SHA256 after rebuilding is
`9de964a9e17597e8ba8383cec86eb96b25466bea7ce3517fab26aa1ba086641f`.

The recorded optional gaps are empty 2026 PFR passing, season/weekly QBR feeds
and 2012 snap counts. Existing rows are retained under the normal optional-feed
policy; this rebuild does not certify those feeds as fresh. The publication
guard still rejects this candidate as expected.

Complete game coverage does not imply complete context for every view. For
qualified 2026 receivers, the capture lacks surface labels for 1,066 catches /
12,166 yards / 68 TDs, play-action classification for 295 / 3,368 / 17, and blitz
classification for 300 / 3,408 / 18. Those counts stay in the independent whole
totals and other supported views; affected views retain explicit exclusions.
Other dimensions have partial play context without excluded receiving counts
(for example, Down excludes 2,921 source plays but zero receiving production).
No missing labels were inferred or redistributed.

Evidence is in the ignored `api/data/coordinated-refresh-proof-20261026.{json,log}`
and its read-only `verify_coordinated_refresh_20261026.py` runner.

The final `jobs.validate_receiving` rerun after the name repair also passed all
**28 seasons, 266,762 receiving rows, 5,633 qualified player-seasons and 476
views**, with exact source-bound metadata, all 84 player-game receiving-count
checks at zero mismatches, and 56 receiving HTTP checks. The known three missing
historical games remain explicit. Its report still says `publication_ready:
false`; the log is `api/data/coordinated-receiving-final-validation-20261026.log`.

The final backend suite passed **1,203 tests, two skipped** (335.40s), including
11 new full-rebuild/charting-coherence controls and four name-selection cases.
Results are in `api/data/coordinated-refresh-final-backend-20261026.{xml,log}`.
The final focused run passed 23 tests. Final source/previous-copy/candidate hashes
were rechecked after all jobs closed; all matched the values recorded above and
no WAL remained. No frontend files, deployment configuration or live data changed.

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

The captured-input and official-row paths are connected. Carry their stored
source gaps and NULLs through API/UI aggregation before
exposing new rows, then pass full real-data candidate/HTTP and downstream checks.
The preview and integration rejection guards stay until that work is ready.
Retire the legacy receiving compatibility path together with serving writes.
No source replacement, serving change, push or deployment is part of this checkpoint.

## Official receiving materialization

`ingest.run_ingest` forwards the captured input owner to `prepare_analytics`,
which passes it only to `splits_builder.materialize`. That builder first calls
`pipeline.receiving_build.prepare_receiving` to verify the stored PBP projection,
REG weekly receiving fields and admission counts against their bound inputs.
`pipeline.receiving_exports.load_receiving_season` is the shared acceptance path
for both the original preview worker and the ordinary materializer: the full
weekly reference and all 17 classified/excluded partition checks run before writes.

The materializer retains passing/rushing SQL and bypasses the old receiving SQL.
It replaces a season's split rows and writes the following records in one SQL
transaction; failures roll back both data and metadata:

| Table | Meaning |
|---|---|
| `player_splits` | Existing long-format rows; official receiving counts and field-specific NULLs for qualified players |
| `receiving_build_preparation` | One record per season: runtime/input revisions, qualification, whole reference checks, all view checks, exclusions, metric policies and candidate schedule coverage |
| `receiving_whole_reference` | Qualified-player whole REG nonconversion reference; raw observed source values, explicitly not serving-ready |
| `receiving_season_totals` | Independently prepared whole receiving rows with historical/population masks, correct per-target rates and verified per-player exclusions for all 17 views |

The whole reference is separate from Down or other classified views. It is not
safe to derive complete season totals from a view that excludes production.
Raw reference targets/EPA are not automatically suitable for display; consumers
must apply the recorded metric policies and covered-game scope.

The builder now performs that preparation separately in `receiving_season_totals`.
`adapt_receiving_overall` uses the same count adapter and original-target
EPA/success/air completeness checks as the 17 views, with all supplied REG
nonconversion plays in one internal group. It does not classify by Down, add an
18th public export dimension or treat official EPA sums as per-target rates.
Whole rows and per-player excluded counts are written in the same transaction
as the split rows and preparation/reference records. The excluded counts come
from hash-verified official excluded exports, not from missing database rows.

Game coverage compares supplied REG game IDs with the candidate schedule's
recorded completed games. It distinguishes missing PBP games from supplied games
whose final scores are not yet recorded in that candidate. Neither is silently
treated as certified complete. Missing games can also affect player admission.

Once an official preparation marker exists, an input-free legacy materialization
attempt raises before changing rows, including when it requests a different season.
This prevents lazy/admin/maintenance paths from overwriting official receiving
with the old calculation. The legacy SQL remains for compatibility with existing
unmigrated databases until the serving-write migration is complete.
`run_ingest` applies the same rule before loading any raw sources, so an input-free
refresh cannot partially update the core tables before the split guard is reached.

The full validator retains preview rejection and adds a separate rejection for
`receiving_build_preparation`: API/UI and release validation remain unfinished.
No existing reconciliation allowance was increased to admit the new rows.

### Captured-play schema preservation

The stored-input check found two preexisting storage problems: `ydstogo` was
absent from the old plays table and silently omitted during refresh; the rare
`tackle_for_loss_2_player_id` column was numeric, causing three supplied 2001 IDs
to become NULL under `TRY_CAST`.

Captured PBP loading now explicitly opts into adding missing typed columns,
promoting common types using DuckDB's union rules, and strict `CAST` on insert.
This preserves new columns, string IDs and fractional numeric values. Other
feeds and the default compatibility storage path retain their existing policy.
The receiving builder checks stored values after loading; it does not waive a
mismatch because its counts happen to agree.

## Historical collection and migration check, October 25, 2026

This earlier control covers core loading/player-game composition, before the
official receiving replacement described in the following section.

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

## Executed official receiving integration, October 25, 2026

The actual main player-split materializer rebuilt all **28 seasons / 476 views**
in a new copy of the core-migration preview. Each receiving view was compared
in both directions with its original independently audited preview table:

- **266,157 canonical receiving rows** matched those audited rows exactly,
  including NULLs, metrics, membership and 5,622 qualified player-seasons.
- **212,466 passing/rushing rows** matched the previous builder's calculations
  on the same refreshed inputs. That control ran frozen code from `3af678b`;
  it does not claim the older serving data was equally fresh.
- Each season has a preparation record and a separate qualified-player whole
  reference. The three missing 1999–2000 games remain explicit.
- Current 2026 surface exclusions remain 721 catches, 8,174 yards and 45 TDs
  in that view. Those values survive other views and the whole reference.
- The stored schedule control only records final scores for two of the 94
  supplied 2026 games. The new game-coverage record therefore marks 92 supplied
  games as unconfirmed by that schedule; these are **not** 92 missing PBP games.
  Fresh schedule/vendor loading remains a separate release requirement.
- Both the source core preview and original serving DB kept their exact bytes.
  The new copy closed without a WAL. The full validator rejects it with
  `Official receiving integration awaits coverage-aware API/UI and complete release validation`.
- The final backend suite passed **1,122 tests, two skipped**. Receiving build
  controls cover coherence failures, historical masks, partial/unavailable views,
  whole-reference retention, zero eligible receivers, transactional rollback of
  rows and new/existing metadata, repeatability, old table column order and
  refusal of legacy overwrites. Schema controls cover missing-column retention
  and numeric-to-string ID/numeric-fraction promotion.
  An additional early-ingestion guard verifies that legacy refreshes cannot
  change raw sources before encountering the official-snapshot restriction.

The proof refreshed stored PBP/weekly inputs from the same captured collection,
with core network downloads forbidden. Schedules/rosters used read-only stored
controls. It did not rebuild team analytics, ratings, grades, defense/team splits
or comparables, and it did not pass complete candidate/HTTP publication gates.
It establishes the receiving replacement and unchanged passing/rushing math,
not general release readiness.

The first comparison run exposed a bug in the verification script's positional
insert into an older table column order. The corrected name-based comparison
then caught the real 2001 ID storage issue described above. Both failed copies
and logs were retained; the final v3 proof ran after the storage correction.
Neither failed run modified its source or the serving database.

Ignored final evidence:

- `api/data/official-receiving-build-20261025-v3.duckdb`: integrated, explicitly
  unpublishable copy, with all season coverage/reference records and proof.
- `api/data/official-receiving-build-proof-20261025-v3.{json,log}`: 28-season
  comparisons, scope/coverage, source hashes and full-gate rejection.
- `api/data/official-receiving-previous-builder-20261025.py`: frozen prior SQL
  owner, SHA256 `7d2598067aec19591470d83ec6fb89d380e5474a05d7678c6f435bcf7dea94e5`.
- `api/data/official-receiving-release-guard-tests-20261025.{xml,log}`: final backend run.

Serving DB SHA256 remains
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`;
the source core preview remains
`a0a5e6ff2503bad4f08e3298145042b7ec024b2cd5d34362316df4fca558489f`.
Nothing was pushed, deployed or promoted.

## Coverage-aware receiving API

`GET /api/players/{player_id}/receiving-splits` is an additive, read-only path.
The existing `/splits` list and passing/rushing consumers retain their contracts.
The new schema is `schemas/receiving.py`; its database reader is
`services/receiving_splits.py`. Generated OpenAPI and TypeScript definitions
include the contract. The receiving lens now consumes it locally; see the
[frontend checkpoint](FRONTEND_DATA.md#prepared-receiving-splits-and-coverage).

Each prepared season contains:

- `overall`: the independent whole receiving row, with supported counts and
  separately checked target-based EPA/success/air values.
- `rows`: the 17 situational views. Each row and the whole row have an
  `unavailable_metrics` map explaining each NULL; NULL is never converted to zero.
- `views`: season-wide play-context status/definition/reason, plus **this
  player's** verified excluded counts. A season-wide partial status need not
  mean this particular player lost production. Raw unsupported target/YAC
  exclusions remain NULL under the same historical policies.
- `game_coverage`: supplied versus recorded completed games, with separate
  missing-play and unconfirmed-final-score IDs. These records do not certify
  that the sources are current or that a full season has finished.

The reader uses one independent cursor and a read transaction. It reads only
database records; it never starts a builder, runs R or opens source export files.
It verifies that each view's stored counts plus independently recorded excluded
counts conserve the whole counts. Corrupt prepared records or lost split rows
produce a controlled 503 instead of being relabelled as a source exclusion. Internal
runtime/package/hash/path records and other players' qualification data are
not exposed. EPA is a per-original-target rate, not the raw calculator sum.

Legacy seasons without prepared totals are explicitly `unverified` with no
new-path totals/rows. Their existing `/splits` response remains available;
the new endpoint never fabricates a whole line by adding legacy Down buckets.
Unknown/nonqualifying players have an empty `seasons` list. Below-threshold
production remains available through the existing player profile/game logs.

UI consumption and availability-aware career aggregation are connected locally.
Fresh source loading, downstream checks and complete receiving-aware release
validation remain outstanding.
Both preview and official-integration publication guards remain in force.

### Executed receiving API check, October 25, 2026

An owned copy of the prior verified integration database rebuilt all 28 years'
receiving rows through the shared export verifier and production storage function.
It added prepared whole rows and per-player exclusions for **5,622 qualified
player-seasons**. All original **478,623 canonical split rows**, preparation
records and raw reference records matched the original in both directions.
This check reused the prior source-coherence proof; it did not repeat main
ingestion or refresh schedules, rosters, vendors or other analytics.

Representative receiving HTTP requests passed for every year, 1999–2026, against
the closed copy reopened read-only. A final 28-request read-only check passed
after the public charting explanation was sanitized. Historical masks and
per-field explanations were retained; 2026 surface exclusions remained **721
catches / 8,174 yards / 45 TDs**, with that production preserved in whole rows.
The three missing historical games and 92 unconfirmed 2026 schedule scores remain
explicit. Both the original serving database and prior integration database
kept their bytes. HTTP reads left the new copy unchanged and without a WAL.
The full publication guard still rejected the copy as expected.

Validation passed: **1,144 backend tests, two skipped**; after final API
explanation review, all **21 receiving HTTP controls** passed. Controls cover
historical masks, partial/empty views, independent air/EPA availability,
legacy fallback refusal, malformed records, a lost row in a partial view,
schema validation rollback, sanitized provider diagnostics and read-only file
immutability. The frontend production build passed; OpenAPI/TypeScript changes
are generated contract additions only. No frontend consumer changed.

Ignored evidence:

- `api/data/receiving-api-proof-20261025.duckdb` and `.json`/`.log`: owned
  integration copy, all-year results, exact-row comparisons and source hashes.
- `api/data/receiving-api-final-http-proof-20261025.json`: final 28 read-only
  responses and unchanged candidate SHA256.
- `api/data/receiving-api-backend-tests-20261025.{xml,log}` and
  `receiving-api-final-review-tests-20261025.{xml,log}`: backend and final HTTP checks.

The API proof copy SHA256 is
`dca943c62551afb9a1340105687e044d548fbba8b0a9faaef74f1604b6bb95db`.
It remains an unpublishable development artifact. Nothing was pushed or deployed.

## Repeatable source-bound receiving validation

The receiving check can now be rerun against a closed candidate using the same
captured bundle/collection that prepared it. From `api/`:

```powershell
uv run --locked python -m jobs.validate_receiving `
  --database data/receiving-api-proof-20261025.duckdb `
  --core-inputs data/receiving-core-history-collection-20261025
```

This command opens DuckDB read-only and validates **every loaded REG season**;
it has no selected-year shortcut. `pipeline/receiving_validation.py` uses the
same source acceptance boundary as preparation to verify stored full PBP/weekly
inputs, fresh-source admission, captured hashes/dependency lock/definitions,
independent whole-versus-weekly counts, exact classified membership and excluded
credits, historical NULL policies and original-target rate/air populations.
It compares every canonical receiving row and all three stored receiving records
with that source-bound replay. No mismatch allowance is used. Metadata comparison
also preserves NULL/zero and Boolean/numeric distinctions.

`receiving_build.receiving_records` is the shared pure record serializer; the
validator does not write the replay results. Independent official whole/classified/
excluded references remain the statistical authority. This is not another credit
calculator, an R execution or a new source download. An internally consistent
edit to stored splits, whole totals and coverage still fails against the bound
exports. Missing/extra seasons, duplicate records, wrong schemas, changed bytes,
lost rows, unsupported fields changed to zero and altered rates all fail.

The existing zero-mismatch player-game receiving checks run for all identified
player/week counts, including players below split admission. Catches, yards and
TDs must match the stored weekly source. The full source replay separately binds
those weekly fields to the captured inputs.

`pipeline/receiving_api_checks.py` exercises receiving HTTP for every season using
an ordinary player and a player with the largest recorded view exclusion. Empty
admission has its own request. Responses must match whole/canonical rows,
player-specific exclusions and missing/unconfirmed game records; every NULL
metric needs an individual explanation. The general API checker also includes
these requests when an official receiving preparation table is present.

The standalone command intentionally reports `publication_ready: false`.
It validates the receiving component, not complete snapshot freshness or other
analytics. `jobs.validate` and its preview/official-integration rejection remain
in force. Replacing the old Down-based receiving release checks, coordinating
fresh schedules/vendors and verifying rebuilt downstream analytics are subsequent
release work. This scoped command cannot promote a snapshot or change watermarks.

### Executed validation, October 26, 2026

The actual CLI passed against the previous verified development copy using all
28 captured source seasons, **1999–2026**:

- **266,157 receiving rows, 5,622 qualified player-seasons and 476 views** matched
  the source-bound replay exactly, including all coverage/whole/reference records.
- All **84 player-game count checks** had zero mismatches.
- All **56 receiving HTTP requests** passed whole/row/explanation/coverage checks.
- The known three missing 1999–2000 games and 92 unconfirmed stored 2026 final
  scores remained explicit. They were not reclassified as complete coverage.
- The development copy and original serving DB kept their exact bytes and had
  no WALs. The unchanged full publication gate still rejected the copy.

A read-only coverage inventory also confirms why this copy needs the coordinated
analytics rebuild: its 2026 PBP and player-game rows cover 94 REG games, while
player ratings and O-line grades cover only two. Team analytics have four rows,
and 2026 defensive splits have none. These counts identify incomplete downstream
preparation; matching historical row counts would not by itself prove freshness.
The inventory is `api/data/receiving-validation-readiness-inventory-20261026.json`.

The complete backend suite passed **1,188 tests, two skipped** (345.86s).
The 43 new receiving-validation controls include deliberate corruption, changed
source bytes/core rows, missing/extra season coverage, NULLs replaced with zero,
false rate values, internally conserved wrong totals, changed HTTP output,
below-admission game-log preservation and read-only success/failure. Existing
builder, legacy snapshot and ordinary HTTP checks also passed. Backend results
are in `api/data/receiving-validation-backend-20261026.{xml,log}`; focused results
are in `receiving-validation-focused-20261026.{xml,log}`.

Ignored evidence: `api/data/receiving-validation-cli-20261026.{json,log}` and
`receiving-validation-proof-20261026.{json,log}`. The same copy remains at SHA256
`dca943c62551afb9a1340105687e044d548fbba8b0a9faaef74f1604b6bb95db`; serving remains
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`.
