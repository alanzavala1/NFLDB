# Completing the receiving preview catalog

October 22, 2026. This checkpoint implements the ten remaining existing receiving
views in the isolated offline preview. It does not integrate or publish them.
The full inventory/release checklist is [receiving migration](../../docs/RECEIVING_MIGRATION.md).

## One shared flow

All 17 dimensions use the official nflfastR calculator on explicitly selected
play IDs. The same adapter, global admission, metric masks, whole-weekly gate,
classified/excluded conservation checks and safe copied-DB lifecycle apply.

`pipeline/receiving_context_rules.py` supplies contextual rules and policy text;
`receiving_dimensions.py` remains the public classifier/catalog entry point.
Python generates one JSON catalog consumed by R. The worker verifies its exact
contents and digest, then independently derives expected play membership from
the bound context. R no longer carries a second manually maintained bucket list.

Pure franchise constants moved to `team_definitions.py`, with compatibility
exports from `config.py`. Reading team aliases from an offline classifier no
longer imports configuration's schedule/database lookup.

## Definitions retained or made explicit

| View | Definition |
|---|---|
| `game_state` | Recorded `wp` 0.05–0.95 inclusive competitive; otherwise garbage. Finite range 0–1 required. |
| `roof` | dome/closed versus outdoors/open; unknown excluded. |
| `surface` | Exact grass versus reviewed non-grass aliases. Preserves the legacy grouping of hybrids such as dessograss in turf; blanks/unreviewed labels excluded. |
| `opponent` | Era-sensitive franchise aliases, canonical JAX, NULL sort order. |
| `opp_division` | Current-franchise divisions, including before 2002. This is explicitly not historical division alignment. |
| `target_depth` | Original pass short/deep, inherited by all credited recipients. |
| `target_direction` | Original pass left/middle/right, inherited by all credited recipients. |
| `pressure` | Recorded QB hit versus no recorded hit, with existing keys. Not all pressure or clean-pocket detection. Before 2006 this view is unavailable. |
| `play_action` | FTN recorded true/false; false differs from uncharted. Supported from 2022. |
| `blitz` | FTN `n_pass_rushers`: 1–4 standard, 5–11 blitz; missing/out-of-range excluded. Does not substitute `n_blitzers`. |

Historical targets/rates remain unavailable for 2003–08; pre-2006 YAC and
unsupported/incomplete air retain independent masks. Excluding a play from one
view cannot remove its verified receiving production from the whole reference
or another usable view. No lateral route or missing pass context is inferred.

## Revision-bound charting

`pipeline/receiving_inputs.py` downloads/normalizes FTN through the existing
vendor source owner. It emits per-season CSVs and an outcome JSON with source,
season, status, row count, detail and URL. Unsupported, missing, empty or expected
failed feeds remain explicit unavailable inputs. Schema/type faults fail.

The job binds those inputs, shared definitions and the frozen R producer into
the completion manifest. R left-joins on season/game/play and asserts uniqueness
and unchanged row count. Python independently verifies the matched population
and every exported charting value against the same input bytes. A row in a
charting table does not certify either individual field's completeness.

## Immutable producer and failure handling

Rscript can read source progressively. Executing directly from a checkout can
therefore fail if an editor changes that file while the build is running. The
first trial exposed that race after calculations completed; the job rejected
the nonzero exit and removed its owned candidate. It did not accept the marker
or change the source DB.

The job now exclusively creates `producer.R` before launching R, executes that
captured copy and binds its SHA256. The worker verifies those bytes. A regression
test changes the original source during process startup and proves the invocation
still uses the original captured script. Existing stop-tree/wait/cleanup logic
remains intact.

## Validation boundary

Tests cover probability boundaries, missing and invalid context, reviewed
environment aliases, relocation cutoffs/current-division policy, original-pass
and lateral attribution, early pressure and unsupported FTN, known-false versus
uncharted, rush-count outliers, malformed/duplicate charting keys, wrong outcomes,
wrong definitions, changed bytes, partial and wholly unavailable views, wrong
per-dimension totals, all 17 preview gate exclusions and the producer race.

The full-history source/qualification refresh, complete R lock/portable builder,
main-build migration, API/UI NULL/partial-total handling and full candidate/HTTP
acceptance remain separate required work. The preview must stay unservable until
that integration. Nothing is pushed, published, or deployed by this checkpoint.

## Executed results

Successful copied candidate: `data/receiving-preview-remaining-rerun-20261022.duckdb`.
Completed exports: `data/upstream-r-trial/preview-export-v13-rerun/`, schema 13.
The three seasons retain 152/210/220 globally admitted receivers respectively.
All **231** bound files verify, including producer, definitions and charting inputs.

| View | 2004 rows / availability | 2009 rows / availability | 2024 rows / availability |
|---|---|---|---|
| `game_state` | 303 / partial | 419 / partial | 437 / partial |
| `roof` | 282 / complete | 399 / complete | 437 / complete |
| `surface` | 302 / complete | 419 / complete | 439 / partial |
| `opponent` | 1707 / partial | 2408 / partial | 2625 / partial |
| `opp_division` | 705 / partial | 988 / partial | 1207 / partial |
| `target_depth` | 0 / unavailable | 395 / partial | 418 / partial |
| `target_direction` | 2 / partial | 629 / partial | 660 / partial |
| `pressure` | 0 / unavailable | 415 / partial | 434 / partial |
| `play_action` | 0 / unavailable | 0 / unavailable | 439 / partial |
| `blitz` | 0 / unavailable | 0 / unavailable | 440 / partial |

Availability above describes the entire stated REG nonconversion play population.
Unknown context on a nonreceiving play does not itself imply lost receiving
production. Empty views are explicit unavailable scopes, not invented zero rows.

Notable excluded production below is for the **globally admitted receiver set**:

- 2004 depth is unavailable; direction has only two admitted-player rows. Early
  QB-hit context is unavailable by policy. FTN is unsupported in 2004 and 2009.
- 2009 depth and direction each exclude 26 catches / 268 yards.
- 2024 surface excludes 64 catches / 788 yards / 5 TD.
- 2024 rush-count grouping excludes 120 catches / 1,450 yards / 13 TD, including
  missing/out-of-range counts under the 1�11 rule. Zero rushers may be a real
  observation outside that rule, not necessarily a provider error.

Those counts remain in the whole receiving reference and other usable views.
They are not deleted or silently assigned to a confident context bucket.

Every dimension passes exact membership and per-player classified/excluded
conservation before admission filtering. A separate raw-credit replay matches
all seven observed count fields for every identified player/bucket, including
below-admission players. Bound context matches captured full PBP. Available
EPA/success/air values match their original-target play populations; masks and
unknown air coverage remain independent. FTN matched/unmatched rows and values
are also independently verified against the bound fresh charting input.

Canonical `player_splits` is identical to the source by bidirectional EXCEPT ALL.
The prior seven preview tables are identical for the shared 2009/2024 seasons
versus v12; 2004 is an additional historical control. The actual candidate still
fails the unchanged full-publication gate because it is a receiving-only preview.

Final backend suite: **1,022 passed, 2 skipped** (194.49s), including the frozen
producer test. The source SHA256 remains
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`;
source and candidate have no WAL. No active jobs remain.

Ignored evidence under `data/upstream-r-trial/`: `preview-job-v13-rerun.log`,
`verify_remaining_inputs.R`, `verify_remaining_views.py`,
`remaining-views-verification.json`, `remaining-views-verification.log`,
`remaining-views-tests-final.xml` and `remaining-views-tests-final.log`.
The failed first trial's exports/logs remain separate for diagnosis; its candidate
was removed and was never accepted.
