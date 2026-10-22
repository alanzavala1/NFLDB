# Receiving migration checklist

Inventory checked October 21, 2026 against the receiving builder, frontend
configuration; the coverage integration uses isolated export schema 10. This is
the completion contract for the receiving migration; it does not authorize
deployment or feature removal.

## Current boundary

There are **17 existing receiving split views: 5 implemented in the new preview,
12 remaining**. The main builder and website still use the existing path.
Preview success does not mean the source database has been migrated.

The existing category builder exposes 15 PBP views and two additional FTN
charting views when that table exists. The frontend lists all 17. No existing
view is silently dropped or marked complete merely by deferring its implementation.
Unavailable means an evidenced source/season/context gap, not unfinished code.

Definitions and labels below are the current code's behavior, not certification
that every historical value is complete. The dimension inventory is finite;
additional views are separate scope.

## Implemented in the preview

| State | Key | Grouping | Remaining release obligation |
|---|---|---|---|
| [x] | `down` | Downs 1–4 | Expand history/source checks; integrate |
| [x] | `quarter` | Quarters 1–4, all later periods as OT | Expand history/source checks; integrate |
| [x] | `home_away` | Designated game side, including neutral games | Expand history/source checks; integrate |
| [x] | `shotgun` | Provider flag 1/0; unknown is not under center | Expand history/source checks; integrate |
| [x] | `field_zone` | Pre-play own territory, opponent territory, red zone | Expand history/source checks; integrate |

Latest field-position preview checked 2006, 2009 and 2024, preserving earlier
Down/quarter/home-away/shotgun outputs. Earlier trials also examined 2002,
2004, 2007 and 2008 in specific scopes. These samples are not a full-history gate.
Latest backend checkpoint: 922 passed, 2 skipped. The schema 10 integration was
run for 2006/2009/2024: all 81 bound files verify; the five preview tables match
the prior schema 9 preview exactly; canonical/source data remain unchanged.

## Remaining ordinary play-context views: 7

Each uses the selected play's context before calculating individual credits.
Lateral recipients retain their credits and the same play-context label.

| State | Key | Source and current grouping | Required work |
|---|---|---|---|
| [ ] | `game_script` | `score_differential`: positive leading, zero tied, negative trailing; offense perspective | Validate finite pre-play values and missing coverage; preserve label order |
| [ ] | `no_huddle` | `no_huddle`: 0 huddle, 1 no-huddle | Validate binary values; never turn missing into huddle; audit history |
| [ ] | `game_state` | `wp`: 0.05–0.95 inclusive competitive, otherwise garbage | Validate 0–1 range and coverage; use the existing probability field and thresholds |
| [ ] | `roof` | `roof`: dome/closed → dome, outdoors/open → outdoors | Explicit alias map; unknown stays unclassified, not outdoors |
| [ ] | `surface` | `surface`: currently exact grass → grass, every other nonempty label → turf | Review and document known aliases, including hybrid-looking labels; audit blanks/unrecognized values; do not silently introduce a new classification |
| [ ] | `opponent` | `defteam`, with season-sensitive franchise abbreviations | Reuse team aliases/relocation mapping; preserve NULL sort order and frontend volume sorting; validate team IDs |
| [ ] | `opp_division` | Division lookup from opponent | Validate aliases; explicitly document current-franchise versus historical division membership before full-history claims—the existing lookup is static, not season-aware |

Recommended implementation order after the coverage foundation below:
game situation/tempo/state, stadium/surface, then opponent/division. These are
small work packages using the same shared flow, not seven separate architectures.

## Pass-context views requiring definition/coverage review: 3

| State | Key | Source and current grouping | Required work |
|---|---|---|---|
| [ ] | `target_depth` | `pass_length`: short/deep | Define this as the original pass's depth, not each lateral recipient's route; preserve credited production on classified plays; report missing classification |
| [ ] | `target_direction` | `pass_location`: left/middle/right | Same original-pass context rule; keep missing direction unclassified; preserve receiving totals outside classified views |
| [ ] | `pressure` | `qb_hit`: 0 clean, 1 pressured in existing code | State QB hit versus no QB hit accurately; a no-hit play is not proof of a clean pocket. Audit early zeros and availability; do not call this full pressure charting |

Keep machine keys compatible where practical. Review visible descriptions before
integration so users understand original-pass attribution and the QB-hit proxy.
Do not invent lateral route depth/direction or reconstruct unknown targets from
receiving production. In the 2003–08 gap, usable catches/yards/TD may survive a
classified view while targets and target-based rates remain unavailable.

## Optional charting views: 2

FTN is a separate charting feed joined on **game ID and play ID**, with a
configured first supported season of 2022. Presence of the table is not proof
that a particular season or play is covered.

| State | Key | Source and current grouping | Required work |
|---|---|---|---|
| [ ] | `play_action` | `is_play_action`: true play-action, false no_pa | Bind charting inputs to the build; require unique join keys; distinguish false from uncharted; report classified/excluded scope |
| [ ] | `blitz` | `n_pass_rushers`: 1–4 standard_rush, 5–11 blitz | Validate integral counts; preserve the current five-plus-rushers definition; do not substitute `n_blitzers`; unknown/out-of-range rush counts are not standard rush |

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
for all five existing preview dimensions (export schema 10). The Python worker
validates and records them before adapting rows. Format 3 reports distinguish
whole-weekly checks from classified-reference checks and describe excluded scope.
Partially or wholly missing context no longer forces a whole-season equality
claim for that particular view. Global admission, field-specific masks and the
strict nonpublishable-preview boundary remain.

The real run preserved 141/210/220 qualified players respectively in all five
views. Down/home-away/field-zone exclude some REG nonconversion plays with
unknown context, but those excluded populations carry no qualified receiving
production in these samples. Quarter/shotgun classify every play. A partial
play-population status therefore does not automatically mean receiving totals
are incomplete. Synthetic worker cases separately prove that nonzero excluded
receiving production and wholly unavailable context are handled correctly.

**Next checkpoint:** add `game_script` (leading/tied/trailing), using the same
export/validation flow. None of the 12 remaining views is marked implemented by
this integration; FTN source binding and feed-specific policy remain future work.

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

- [ ] Complete preview coverage for the 17 views and the receiving metric contract:
  catches, yards, TD, supported targets/YAC/first downs/air, target-role EPA and
  positive-EPA success; category-inapplicable interceptions/CPOE remain NULL.
- [ ] Retain known policies: targets/rates unavailable 2003–08, preview YAC before
  2006 unavailable, and air unavailable when either air or target coverage fails.
  Do not silently certify all other seasons solely from these date boundaries.
- [ ] Lock the complete R environment and provide a portable offline build path;
  R remains in data preparation, with the serving backend staying Python.
- [ ] Refresh all required sources and qualification together, preserving the
  existing admission policy. Replace the preview's copied-old-PBP qualification
  with a coherent fresh build; never use sparse raw target credits as eligibility.
- [ ] Validate every played season in the candidate, not only the pilot samples.
  The local DB currently has plays labeled 1999–2026; resolve the newest played
  season's required reference coverage rather than omitting it from checks.
- [ ] Integrate the official receiving path into the ordinary offline build,
  remove its replaced receiving calculation, and preserve passing/rushing paths.
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
  `frontend/src/features/splits/aggregation.ts`, `metricFormatting.ts`.
- Optional feed: `api/pipeline/vendor_sources.py`, `normalization.py`;
  opponent definitions: `api/config.py`.
- Ignored audit evidence: `api/data/upstream-r-trial/inventory_receiving_contexts.R`,
  `receiving-context-inventory.json`, `receiving-ftn-inventory.json` and the
  referenced export manifests. Cached source roots: v5/2002, v3/2004,
  v9/2006/2009/2024. No downloads or source DB writes were needed.

For executed preview history see
[the official calculator trials](../api/experiments/UPSTREAM_SPLITS.md).
