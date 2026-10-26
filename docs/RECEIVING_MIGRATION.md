# Receiving migration checklist

Inventory checked October 21, 2026 against the receiving builder, frontend
configuration, updated October 23 for locked R and fresh-input qualification;
the preview uses isolated export schema 14. This is the completion contract for the receiving
migration; it does not authorize deployment or feature removal.

## Current boundary

There are **17 existing receiving split views, all implemented in the new preview**.
The main builder and website still use the existing path.
Preview success does not mean the source database has been migrated.

The existing category builder exposes 15 PBP views and two additional FTN
charting views when that table exists. The frontend lists all 17. No existing
view is silently dropped or marked complete merely by deferring its implementation.
Unavailable means an evidenced source/season/context gap, not unfinished code.

Definitions and labels below are the current code's behavior, not certification
that every historical value is complete. The dimension inventory is finite;
additional views are separate scope.

## Original seven preview views

| State | Key | Grouping | Remaining release obligation |
|---|---|---|---|
| [x] | `down` | Downs 1–4 | Expand history/source checks; integrate |
| [x] | `quarter` | Quarters 1–4, all later periods as OT | Expand history/source checks; integrate |
| [x] | `home_away` | Designated game side, including neutral games | Expand history/source checks; integrate |
| [x] | `shotgun` | Provider flag 1/0; unknown is not under center | Expand history/source checks; integrate |
| [x] | `field_zone` | Pre-play own territory, opponent territory, red zone | Expand history/source checks; integrate |
| [x] | `game_script` | Pre-play leading/tied/trailing from the offense's perspective | Expand history/source checks; integrate |
| [x] | `no_huddle` | Recorded 0 huddle / 1 no-huddle flag | Expand history/source checks; integrate |

The final preview exercises 2004, 2009 and 2024, including natural historical
pass-context gaps, early QB-hit exclusions and supported/unsupported FTN inputs.
Earlier trials also checked 2002/2006/2007/2008 in bounded scopes. These are
representative controls, not a full-history acceptance gate. Main build, API/UI
integration and publication remain separate finish lines below.

Final validation: **1,022 backend tests passed, 2 skipped** (194.49s). All 231
bound files and all 51 season/view conservation checks verify. Independent
raw-credit replay matches every identified player/bucket; the source/canonical
rows remain unchanged. The original seven outputs match v12 for shared
2009/2024 seasons. The actual candidate remains rejected by the publication gate.
See [executed context results](../api/experiments/RECEIVING_CONTEXT_VIEWS.md).

## Additional ordinary play-context views: implemented

Each uses the selected play's context before calculating individual credits.
Lateral recipients retain their credits and the same play-context label.

| State | Key | Source and current grouping | Implemented rule / release condition |
|---|---|---|---|
| [x] | `game_state` | `wp`: 0.05–0.95 inclusive competitive, otherwise garbage | Finite 0–1 validation and missing coverage; existing thresholds preserved |
| [x] | `roof` | `roof`: dome/closed → dome, outdoors/open → outdoors | Explicit alias map; unknown stays unclassified, not outdoors |
| [x] | `surface` | Exact grass versus reviewed non-grass aliases | Known legacy aliases preserved; blanks/unreviewed labels excluded and reported |
| [x] | `opponent` | `defteam`, with season-sensitive franchise abbreviations | Reuse team aliases/relocation mapping; preserve NULL sort order and frontend volume sorting; validate team IDs |
| [x] | `opp_division` | Division lookup from opponent | Validated aliases and explicitly current-franchise division membership; not historical alignment |

These views share the same official calculator, adapter and coverage gate.
Roof uses explicit aliases. Surface preserves the legacy exact-grass grouping
for reviewed observed labels, including hybrid-looking `dessograss` in turf;
blank or unreviewed labels are excluded. Opponent uses season-sensitive franchise
aliases and NULL sort order. Division deliberately preserves current-franchise
membership, including before 2002; it is not historical division alignment.

## Pass-context views: implemented with explicit definitions

| State | Key | Source and current grouping | Required work |
|---|---|---|---|
| [x] | `target_depth` | `pass_length`: short/deep | Define this as the original pass's depth, not each lateral recipient's route; preserve credited production on classified plays; report missing classification |
| [x] | `target_direction` | `pass_location`: left/middle/right | Same original-pass context rule; keep missing direction unclassified; preserve receiving totals outside classified views |
| [x] | `pressure` | `qb_hit`: 0 clean, 1 pressured in existing code | State QB hit versus no QB hit accurately; a no-hit play is not proof of a clean pocket. Audit early zeros and availability; do not call this full pressure charting |

Machine keys remain compatible. Review visible descriptions before
integration so users understand original-pass attribution and the QB-hit proxy.
Pressure is recorded QB hit versus no recorded hit, not a clean-pocket detector.
The preview marks that entire view unavailable before 2006 rather than certifying
early zero flags. Do not invent lateral route depth/direction or reconstruct
unknown targets from receiving production. In the 2003–08 gap, usable catches/yards/TD may survive a
classified view while targets and target-based rates remain unavailable.

## Optional charting views: implemented

FTN is a separate charting feed joined on **season, game ID and play ID**, with
a configured first supported season of 2022. The preview downloads it through
the existing vendor source owner and binds normalized CSVs, per-season source
outcomes and URLs into the completion manifest. Python independently verifies
the exported join against those exact charting bytes before calculation output
is accepted. Duplicate keys, malformed fields, changed bytes and inconsistent
outcomes fail. Expected outages create explicit unavailable views. Presence of
the table is not proof that a particular season or play is covered.

| State | Key | Source and current grouping | Required work |
|---|---|---|---|
| [x] | `play_action` | `is_play_action`: true play-action, false no_pa | Bind charting inputs to the build; require unique join keys; distinguish false from uncharted; report classified/excluded scope |
| [x] | `blitz` | `n_pass_rushers`: 1–4 standard_rush, 5–11 blitz | Validate integral counts; preserve the current five-plus-rushers definition; do not substitute `n_blitzers`; unknown/out-of-range rush counts are not standard rush |

Validate these against the charted subset, then separately account for uncharted
receiving production. Missing optional feeds must have an explicit unavailable
status; they cannot produce confident zero totals or drop ordinary receiving stats.

## Findings from the bounded source audit

Cached PBP/credit inputs were hash-verified against their completed export
manifests before reading: five seasons, ten files. The receiving-credit scope
contains REG nonconversion plays with an identified player's stat 21–24 or 115
record. The second scope contains original-receiver completed/incomplete/
intercepted passes. Neither scope establishes historical target completeness.

| Season | Receiving-credit plays | Unclassified depth / direction on those plays | Blank surface on those plays |
|---|---:|---:|---:|
| 2002 | 16,854 | 16,854 / 16,846 | 0 |
| 2004 | 9,773 | 9,773 / 9,769 | 0 |
| 2006 | 9,826 | 574 / 574 | 0 |
| 2009 | 16,809 | 55 / 55 | 0 |
| 2024 | 17,013 | 0 / 0 | 118 |

The 2009 original-receiver target scope has 16,803 plays and 52 missing
depth/direction classifications. Its difference from the credit-play scope is
another reason to define populations explicitly. Target depth cannot be inferred
from populated receiving yards or target counts.

Score difference, roof, tempo, win probability and opponent had usable values
on all receiving-credit plays in these samples. That supports the next pilots;
it does not certify every season or prove a recorded zero means fully measured.
In particular, every audited original-receiver target has `qb_hit=0` in 2002
and 2004, versus nonzero hit records in 2006/2009/2024. Existing code comments
also flag early pressure coverage. Early no-hit totals need an explicit coverage
policy rather than being described as clean pockets.

Read-only FTN inspection of the existing DB found unique game/play keys, stored
2022–2025 rows, and these original-receiver REG nonconversion target counts:

| Season | Target rows | Charting match / known play-action | Rush counts within 1–11 |
|---|---:|---:|---:|
| 2022 | 17,306 | 17,306 | 17,223 |
| 2023 | 17,483 | 17,483 | 17,425 |
| 2024 | 17,013 | 17,013 | 16,806 |
| 2025 | 16,609 | 16,609 | 16,572 |

These are properties of the stored snapshot, not proof of current upstream
availability, semantic correctness or complete charting of individual credits.
Each field needs its own coverage check even when a charting row exists.

## Coverage-aware validation: integrated into the preview

The preview worker now separately checks whole-season counts against weekly
references and each dimension against its exact classified population. Excluded
receiving production must account for the difference from the full total.

`api/pipeline/receiving_partition_validation.py` now provides the pure acceptance
rule. It verifies independently derived versus exported game/play membership,
unique keys and disjoint buckets; compares official bucket counts to an official
calculation over the classified union; and compares classified plus excluded
counts to the whole official reference, by player before admission filtering.
It retains unidentified credits in the comparison. The result records exact
input hashes, play counts, exclusion reason and qualified production on both
sides. A globally admitted player may legitimately have no classified production.
Observed-count equality does not certify targets, air coverage or rates.

Two frozen official-calculator controls exercise natural gaps: a 2009 completion
with missing pass depth, and a 2024 touchdown with an unsupported 45-rusher FTN
value. The latter is an unusable field in an existing charting row, not a missing
join row. Complete and wholly unavailable populations, missing/duplicate keys,
per-player errors hidden by grand totals, lateral credits, negative yards and
historical masks also have regression coverage.

The R producer now emits hash-bound membership and classified/excluded references
for every implemented preview dimension (export schema 14). The Python worker
validates and records them before adapting rows. Format 3 reports distinguish
whole-weekly checks from classified-reference checks and describe excluded scope.
Partially or wholly missing context no longer forces a whole-season equality
claim for that particular view. Global admission, field-specific masks and the
strict nonpublishable-preview boundary remain.

The preceding schema 10 run preserved 141/210/220 qualified players respectively
in its five views. Down/home-away/field-zone exclude some REG nonconversion plays with
unknown context, but those excluded populations carry no qualified receiving
production in these samples. Quarter/shotgun classify every play. A partial
play-population status therefore does not automatically mean receiving totals
are incomplete. Synthetic worker cases separately prove that nonzero excluded
receiving production and wholly unavailable context are handled correctly.

Game script now uses the same contract. Its unknown-score play counts are
2,321/2,255/2,588 in the 2006/2009/2024 samples, with zero qualified receiving
production in those excluded populations. That is recorded as partial play
coverage even though the receiving totals reconcile fully. Missing-score worker
tests also exercise excluded catches/yards and wholly unavailable views.

Tempo also uses this contract: all REG nonconversion plays in the three pilot
samples have a recorded 0/1 flag, so no tempo production is excluded. Missing
and wholly unavailable flag cases remain covered by real-worker tests with a
deterministic producer. This records provider completeness for these samples,
not independent certification of every historical huddle flag.

**Next checkpoint:** finish the receiving migration outside the preview:
the [1999–2026 audit](RECEIVING_HISTORY_VALIDATION.md) has completed all 28 seasons
and 476 season/view checks, with three documented missing games in 1999–2000.
Integrate the main build with API/UI NULL and partial-scope handling and pass
the full candidate gates. No existing view remains unimplemented. Source unavailability
continues to mean an evidenced source/season/context gap, not unfinished code.

The shared catalog is generated from pure Python definitions and consumed by R;
the worker verifies its exact values/hash. `team_definitions.py` owns franchise
constants without importing the database; `config.py` preserves existing exports.
The official whole-season and exact classified/excluded calculations remain the
statistical authority. Python validates and adapts them, not a parallel serving
calculator. FTN and known early QB-hit limitations cannot erase usable counts in
other views or the whole receiving reference.

The preview freezes the producer script before starting R and binds its SHA256
to the manifest. A build therefore executes one captured script even if the
checkout is edited concurrently. Full tests cover that race as well as wrong
definitions, corrupted charting bytes, false/unknown flags and duplicate joins.

- [x] Define a per-season/dimension coverage record: supported/unavailable reason,
  source revision, classified/unclassified play scope and credited production.
- [x] Reconcile classified buckets to official calculation on **the exact same
  classified play IDs**, preserving individual recipient credits.
- [x] Separately reconcile classified plus excluded production to the whole
  reference population (the full season for a season build). Prove bucket
  membership is disjoint and the join does not multiply records. Whole-season
  equality remains required for complete partitions.
- [x] Keep admission independent of context availability: a missing optional
  view must not make an otherwise eligible player disappear globally.
- [x] Preserve per-field NULLs and actual zeroes through supported partial preview
  dimensions, with explicit unsupported historical metrics and empty populations.
  Optional-feed policies remain with the future charting views. Do not relax the
  full candidate acceptance gate to get a pass.
- [x] Add a real missing-context example and an unusable-charting example to verify
  the rule before adding the remaining views. A wholly missing optional feed is
  additionally covered by a synthetic unavailable-population test.
- [x] Wire the validated contract into hash-bound producer exports and worker
  reports, retaining whole-season reference/weekly checks and safe DB lifecycle.

Checked items above describe the isolated preview integration and controls,
not the main offline rebuild or a publishable receiving build.

## Before exposing new receiving rows to users

- [ ] Extend missing-data handling through API, per-season views, career totals,
  comparisons and derived rates. `aggregatePlayerSplitRows` currently sums
  missing air/YAC as zero and treats missing rate values as zero when target
  counts are known. `per`/`pct` also default a missing numerator to zero.
  These paths must not turn newly explicit gaps into fabricated totals/rates.
- [ ] Specify complete versus partial totals and covered-season ranges. A partial
  total may only be shown with a clear scope; do not present it as a full career.
- [ ] Preserve usable counts when another field/context is unavailable, and show
  an understandable reason. Keep existing category/season/REG and sorting
  contracts, with deliberate reviewed changes to inaccurate descriptions.
- [ ] Check the frontend's Down-derived overall rows, target-dependent ratios,
  attribution notices, cached responses and generated API types against the
  integrated source. Offline preview tables remain unservable until integration.

## Finish lines

**Receiving previews complete:** all 17 existing keys are implemented for their
supported scopes; source-unavailable cases are explicit; coverage checks above
pass on missing-context/charting cases as well as ordinary and lateral controls.
Every existing view is accounted for. Unfinished implementations do not count as
source-unavailable. Any intentional feature retirement is a separate user decision.

**Receiving migration ready for a publication review:**

- [x] Implement preview coverage for the 17 views and the receiving metric contract:
  catches, yards, TD, supported targets/YAC/first downs/air, target-role EPA and
  positive-EPA success; category-inapplicable interceptions/CPOE remain NULL.
- [ ] Retain known policies: targets/rates unavailable 2003–08, preview YAC before
  2006 unavailable, and air unavailable when either air or target coverage fails.
  Do not silently certify all other seasons solely from these date boundaries.
- [x] Lock the complete R dependency graph and provide repeatable setup for the
  existing offline preview build. `api/r/renv.lock` pins R 4.6.1 and 49 packages;
  `restore.R` restores them and the build checks the frozen lock before downloads.
  A fresh Windows x64 library with cache reuse disabled was exercised with the
  real calculator. R remains in preparation; serving stays Python.
- [ ] Verify the chosen production build platform and its system dependencies.
  Linux/macOS restoration has not been executed; this R package lock does not
  pin operating system libraries or guarantee permanent artifact availability.
- [x] Replace the preview's copied-old-PBP qualification with the same bound
  fresh play context used by the calculator, preserving the existing admission
  policy. Record admitted IDs/counts and context/SQL fingerprints. Sparse official
  target credits and optional split context do not determine eligibility.
- [ ] Integrate required-source refresh and qualification in the main candidate
  build. Receiving preview alignment does not refresh the copied database's other
  categories, analytics or source metadata.
  The [shared-input checkpoint](RECEIVING_BUILD_INTEGRATION.md) now lets the
  ordinary build consume captured plays/weekly feeds from single runs or a
  compatible historical collection, and persist their revisions. The real core
  loader/player-game migration passed all 28 years on an unpublishable copy,
  including replacement of the legacy weekly schema without redownloading inputs.
  Official receiving materialization now consumes those inputs and verifies
  stored-play/weekly/admission coherence before replacing canonical rows. Other
  source freshness/coherence and a full accepted real candidate remain pending;
  this item is intentionally not marked complete.
- [x] Run the receiving preview and independent checks for every played season,
  1999–2026, including 94 completed 2026 games through October 22. All 476
  season/view calculations pass; 26 seasons have complete game coverage.
- [ ] Carry the audit's source gaps into publication policy and API/UI scope.
  1999 is missing one game and 2000 two games; their observed data is validated,
  not certified complete. 2026 surface context is absent for 29 supplied games.
  Keep usable receiving production and expose these limits explicitly.
  The additive receiving API now carries masked whole totals, per-row NULL
  reasons, player-specific view exclusions and separate missing/unconfirmed
  game records. Legacy seasons are explicitly unverified on that path.
  Frontend consumption and career aggregation are still pending.
- [ ] Integrate the official receiving path into the ordinary offline build,
  remove its replaced receiving calculation, and preserve passing/rushing paths.
  The captured-input build now uses the official path and stores coverage and
  whole-reference records atomically. The old receiving SQL is bypassed in that
  mode; compatibility remains for unmigrated databases until serving writes are
  retired. Input-free rebuilds cannot overwrite an official receiving snapshot.
  All 476 main-materializer receiving outputs matched their audited previews;
  passing/rushing matched the previous builder on the same fresh inputs. This
  is an offline integration proof, not an accepted serving snapshot.
- [ ] Pass the unchanged full candidate/HTTP gates with revision-bound results,
  all historical/current coverage and receiving-total checks. Preview success is
  not a substitute. Ratings/comparables downstream effects must also be checked.
- [ ] Finish the UI/NULL/partial-scope checks above and a concrete release review.

Publishing the validated snapshot, retiring runtime rebuilding and opening the
serving DB read-only remain part of the wider offline-pipeline milestone.
Assistant model/streaming work is later. No publication or runtime migration
was performed by this inventory.

## Evidence and implementation owners

- Existing views: `api/splits_builder.py`, `api/splits_core.py`,
  `frontend/src/features/splits/playerConfig.ts`.
- Preview: `api/pipeline/receiving_dimensions.py`, `receiving_splits.py`,
  `receiving_target_metrics.py`; `api/jobs/receiving_preview_worker.py`;
  `api/experiments/upstream_receiving_splits.R`.
- Coverage/UI: `api/services/receiving_coverage.py`,
  `api/services/receiving_splits.py`, `api/schemas/receiving.py`,
  `frontend/src/features/splits/aggregation.ts`, `metricFormatting.ts`.
- Optional feed: `api/pipeline/vendor_sources.py`, `normalization.py`;
  opponent definitions: `api/config.py`.
- Ignored audit evidence: `api/data/upstream-r-trial/inventory_receiving_contexts.R`,
  `receiving-context-inventory.json`, `receiving-ftn-inventory.json` and the
  referenced export manifests. Cached source roots: v5/2002, v3/2004,
  v9/2006/2009/2024. No downloads or source DB writes were needed.

For executed preview history see
[the official calculator trials](../api/experiments/UPSTREAM_SPLITS.md).
