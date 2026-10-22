# Official nflfastR receiving split trial

This experiment executes the installed **official R calculator**, then checks
its receiving counts in Python. Production ingestion, API requests and the
serving database do not import either runner. It is a feasibility trial, not a
production adapter or a completed receiving migration.

## Observed environment

October 21, 2026: Windows x64, R 4.6.1, nflfastR 6.0.0, nflreadr 1.5.1.
The trial installed 43 R packages (about 114 MB) in a separate ignored library.
The website's Python dependencies and Docker image were unchanged. R was
installed for the current user under `api/data/upstream-r-trial/R-4.6.1`, with
optional shortcuts/file associations disabled; it was not added to PATH.

The R runner checks the two nflverse package versions. Transitive package
versions, runtime details, calculator body, input snapshots and fingerprints
are recorded in ignored output. This is not a locked production R environment.

## Running

Install R and the CRAN binary packages `nflfastR` and `jsonlite` in an isolated
library. The observed package versions above are required by the runner; if
installing later versions, evaluate them explicitly before changing the checks.
The R calculation needs network access to nflverse's published feeds. It saves
input snapshots for inspection; it does not replace the official function's
internal loader with a custom implementation.

From `api/`, using the local trial installation in PowerShell:

```powershell
$env:R_LIBS_USER = Join-Path (Get-Location) 'data/upstream-r-trial/library'
$env:LC_ALL = 'C'
& data/upstream-r-trial/R-4.6.1/bin/Rscript.exe --vanilla `
  experiments/upstream_receiving_splits.R data/upstream-r-trial/results 2024 2004

uv run --locked python -m experiments.evaluate_upstream_receiving_splits `
  data/upstream-r-trial/results --database data/nfl.duckdb
```

Python evaluation can be repeated from saved exports without R or network.
The optional database is opened read-only and compared only for players already
stored; this does not evaluate or change production qualification/admission.
Keep large outputs and runtime installations in ignored `data/`.

New runs emit a structured `receiving_export` contract in `run.json`:
schema version 3, REG, season summaries, Down dimension, two-point attempts
excluded. The adapter refuses earlier versions. The completion manifest now
records R/loaded package versions and SHA256 hashes of the source snapshots and
CSV exports. The loader parses only bytes matching the recorded hash. These
digests detect changed files; they do not authenticate the producer or lock the
complete R dependency environment. Earlier unbound trial results remain useful
research evidence but are not accepted by the current adapter. Version 3 also
requires official receiving YAC and first-down counts in Down and weekly CSVs.

## What was checked

Select regular-season plays excluding two-point attempts, then call official
`calculate_stats(pbp=...)` for the whole season and separately for downs 1–4.
Player selection happens after calculation so lateral recipients are retained.
No fabricated `fixed_drive` column is needed: the full upstream PBP is loaded.

The evaluator checks targets, receptions, receiving yards and receiving TDs:

- All identified players' season totals versus published weekly summaries.
- All identified players' season totals and each down bucket versus our existing
  isolated credit prototype, using the captured upstream input records.
- Down partition sums versus full-season totals. Neither sample had receiving
  credit rows missing down context.
- Independently stated Gibbs/Jefferson season and down expectations. Gibbs's
  first-down result includes the 20-yard lateral TD; fourth down includes the
  21-yard lateral. Neither adds catches or targets.
- 2004 retains the historical target gap; matching observed targets is not a
  completeness check.

The evaluator also rejected altered yardage, a missing nonzero bucket row, and
a missing metric in manual negative checks. The existing credit prototype's
52 fixture/guard tests passed.

## Measured results

| REG season | Players with a nonzero receiving measure | Targets | Catches | Yards | TD |
|---|---:|---:|---:|---:|---:|
| 2024 | 500 | 17,013 | 11,629 | 127,024 | 809 |
| 2004 | 442 | 5 | 9,773 | 115,343 | 732 |

Zero disagreements for every measure in the comparisons above. These are
consistency checks between related nflverse products, not independent proof of
NFL accuracy. Zero-stat output players are excluded from the displayed count.

Gibbs: 63 targets, 52 catches, **517 yards, 4 TD**. Existing stored Down splits
sum to 476 yards, 3 TD. Jefferson: 154 targets, 103 catches, **1,533 yards, 10 TD**,
matching the existing Down splits.

Local elapsed times: 2024 full calculation 7.34 seconds, repeated warm full
calculation 6.01 seconds, all four down calls 9.15 seconds combined. 2004 down
calls took 8.15 seconds combined. These are one-machine measurements, not a
full-history or production throughput benchmark.

Against the 220 players already stored in 2024 Down splits, changed bucket
counts are: targets 3, catches 0, yards 18, TD 5. For 152 stored players in 2004:
targets 521, catches 0, yards 5, TD 0. These diagnostic differences are not all
classified as lateral fixes; the three modern target differences were reviewed
below. Historical stored targets were derived from incomplete PBP;
the new raw zero counts must remain unavailable in user-facing historical views.

## Target difference review (October 21)

All three changed 2024 target buckets among stored split players come from two
plays with updated receiver IDs and descriptions in the trial PBP snapshot:

| Game / play | Original stored PBP receiver | Trial PBP receiver | Individual target credit |
|---|---|---|---|
| `2024_05_MIA_NE` / `1975` | Odell Beckham | Tyreek Hill | Tyreek Hill |
| `2024_05_NYJ_MIN` / `2914` | Allen Lazard | Garrett Wilson | Garrett Wilson |

Both plays are incompletions. The changed stored buckets are Hill third down
+1 target, Lazard second down -1, Wilson second down +1. Beckham is outside the
existing stored split-player population, explaining why two corrections produce
three changes in that comparison rather than four. No catches, receiving yards
or touchdowns change on these plays.

Across **all identified players** in 2024 REG nonconversion plays with down 1–4,
target credits agree with targets inferred from the trial PBP at player/play
level: zero differences. This explains these changes as source snapshot updates,
not special target mathematics in R. It does not establish target availability
in other seasons or independently verify the NFL's original intended receiver.

Ignored evidence: `data/upstream-r-trial/results/target-review-2024.json`,
`target-context-2024.csv`, `player-names-2024.csv`, and the read-only diagnostic
`data/upstream-r-trial/review_targets.py`. Original source DB remains unchanged.

## Boundary before integration

The integration direction is to use the maintained official calculator for
supported receiving counts. `pipeline/receiving_splits.py` now provides the first
offline adapter: validated R Down exports become the existing `player_splits`
column layout. It receives an explicit qualified-player collection, masks
known historical targets and unsupported pre-2006 YAC, retains receiving
production and negative yardage/YAC, and imports official receiving first downs.
Unsupported advanced columns stay NULL. It does not execute R or write a database.
Serving and the main analytics rebuild do not call it yet. These partial rows
must not replace complete production rows and erase their remaining fields.

A second official run produced versioned inputs under ignored
`data/upstream-r-trial/adapter-input/`. The read-only dry run used the existing
`qualification_ctes` against stored PBP, then inserted converted rows into an
in-memory instance of the actual `player_splits` schema:

| Season | Qualified players retained | Converted rows | Historical targets |
|---|---:|---:|---|
| 2024 | 220 / 220 | 813 | Existing coverage policy passes values through |
| 2004 | 152 / 152 | 522 | NULL |

Every player/down catch, yard and TD count survived conversion. Modern target
counts also survived; historical targets became NULL, including positive raw
credits. Gonzalez's 2004 output retains 102 catches, 1,258 yards and 7 TD.
The dry run preserves the original admission policy for comparison; production
must coordinate qualification and calculator inputs from the prepared sources.

38 network-free adapter tests cover the real Gibbs/Jefferson/Gonzalez rows,
actual SQL schema insertion, null handling, negative/lateral counts, explicit
admission, unknown players, invalid counts, duplicate rows, incomplete exports,
package versions, scope drift and changed/missing file hashes. Evidence for the
earlier v1 conversion is `adapter-check.json` alongside
the fresh trial inputs. Run `uv run --locked pytest tests/test_upstream_receiving_splits.py`.

## End-to-end preview (October 21)

`python -m jobs.receiving_preview` now copies a closed source, invokes official
R in isolation and writes the converted rows into `receiving_down_preview` in
the separate DB. Existing `player_splits` rows remain intact. A recorded
invocation ID, copied-baseline hash and export-manifest hash tie the preview to
its inputs and observed R environment. All eligible players and their receiving
production are checked against bound weekly exports. Failures remove only the
new candidate and retain exports/logs. The full snapshot validator rejects this
preview, even when its scoped receiving checks pass.

Actual output is ignored `data/receiving-preview-20261021.duckdb`, with exports
under `data/upstream-r-trial/preview-export-v2b/`. Results remain 152 players / 522
rows in 2004, 220 / 813 in 2024. All production comparisons pass; historical
targets remain NULL and modern targets match weekly. Sixteen file hashes were
independently verified in Python, and 38 loaded namespaces were recorded.
A bidirectional SQL comparison found zero differences in the complete existing
`player_splits` table versus the source. Both DBs closed without WALs.

The first preview attempt correctly failed because weekly CSVs lacked the
season_type field required by reference validation. The producer now exports
that field; the failed candidate was removed, and its logs remain at
`data/upstream-r-trial/preview-export-v2/`. Lifecycle tests cover that case,
changed bytes, stale invocation IDs, reference mismatches, missing players,
runtime mismatches, existing paths, original-file preservation, missing R,
pending WALs, interrupted process-tree cleanup and full-gate preview rejection.
Focused adapter/preview/candidate/validation checks: 108 passed. Full backend:
755 passed, 2 skipped. The actual preview was also opened read-only and rejected
by the full snapshot validator as expected.

Before production: lock the complete R environment/build, coordinate source
refresh and remaining metrics, and evaluate other dimensions and full history.
Receiving EPA, success rates and target-specific dimensions still need explicit
definitions. No metric/rating/comparables correctness is established here.
The [receiving metric review](RECEIVING_METRIC_REVIEW.md) records the definitions
and availability evidence used by the v3 extension below.

## YAC and receiving first-down extension (October 21)

Version 3 adds official `receiving_yards_after_catch` and
`receiving_first_downs`, mapped to existing `yac` and `first_downs` columns.
Negative YAC and YAC greater than receiving yards are accepted. Nonfinite,
fractional, missing values, negative first-down counts and first downs exceeding
catches fail. The preview checks supported YAC and receiving first downs against
weekly totals, independently of target availability.

Actual ignored output: `data/receiving-preview-yac-20261021.duckdb`; source
exports: `data/upstream-r-trial/preview-export-v3/`.

| REG season | Eligible players retained | Preview rows | Targets | YAC |
|---|---:|---:|---|---|
| 2004 | 152 | 522 | Unavailable | Unavailable |
| 2006 | 141 | 492 | Unavailable | Matches weekly |
| 2007 | 159 | 549 | Unavailable | Matches weekly |
| 2008 | 149 | 514 | Unavailable | Matches weekly |
| 2024 | 220 | 813 | Matches weekly | Matches weekly |

Receiving first downs match weekly totals for all five samples. Independent
read-only diagnostics cover all identified players, including those below split
admission: catches, yards, TD, YAC and receiving first downs reconcile full
season to weekly and across the Down partition. Every individual YAC player/down
bucket matches raw stat-113 credits joined to the selected play context. These
checks establish consistency, not independent NFL correctness or all-year coverage.

Gonzalez 2006: targets NULL, 73 catches, 900 yards, 5 TD, **319 YAC, 54 receiving
first downs**. Gonzalez 2004 retains 102/1,258/7 and 69 first downs with YAC NULL.
Gibbs 2024 includes 593 YAC and 24 receiving first downs; Jefferson has 487/62.
All 40 recorded file hashes were verified, and full bidirectional comparison
found zero changes to original `player_splits`. Source DB hash remains unchanged;
both DBs closed without WALs. The artifact remains a preview rejected by the
full snapshot validator.

Validation: 769 backend tests passed, 2 skipped. The stronger real Gonzalez-2006
fixture was subsequently replayed with the complete 48-test adapter suite, all
passing. New cases cover the target-independent YAC boundary, missing new fields,
negative/oversized/fractional values, unavailable historical positive values,
YAC/first-down reference disagreement and the actual SQL/worker lifecycle.
Evidence: ignored `data/upstream-r-trial/yac-preview-verification.json`,
`verify_yac_preview.py` and `preview-job-v3.log`.

Source DB SHA256 before and after:
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`.
No WAL, push, deployment or serving-data replacement.

References: [calculator documentation](https://nflfastr.com/reference/calculate_stats.html),
[upstream subset feature](https://github.com/nflverse/nflfastR/pull/524).

## Target-role EPA and success extension (October 21)

Version 4 exports official `receiving_epa` plus the original-receiver PBP
attempt flags and EPA in hash-bound context CSVs. A separate pure helper,
`pipeline/receiving_rates.py`, derives existing SQL columns:

- `epa`: official receiving EPA sum / targets, rounded to four decimals.
- `success_pct`: 100 × positive-EPA target plays / targets, rounded to one decimal.

Success is our explicit calculation, not an official calculator output. The
population includes completed passes, incompletions and interceptions with an
identified original receiver, REG only, excluding two-point attempts. Target
credits must match the original target-play count and every such play must
have EPA. EPA/tgt additionally requires the official numerator to agree with
that population. Missing coverage masks rates only; malformed context, duplicate
plays, changed bytes and nonfinite EPA fail the export. Zero EPA is a failure;
missing EPA is unknown. No targets means no target-based rates. Known 2003–08
target coverage gaps continue to mask both rates even if PBP is present.

These metrics describe the original target role; they do not divide EPA among
lateral recipients. A modern numerator disagreement hides EPA/tgt without
erasing independently verified Success% or receiving production. Air yards,
interceptions and CPOE remain NULL in the partial preview.

Executed preview: `data/receiving-preview-epa-20261021.duckdb`, exports
`data/upstream-r-trial/preview-export-v4/`. Samples: 2004 (152 players / 522
rows), 2006 (141 / 492), 2024 (220 / 813). All existing count reconciliations
pass. Historical rates are NULL. In 2024, 812 buckets have both rates and agree
with fresh PBP target-play EPA means and success flags. One admitted player's
fourth-down bucket has 10 lateral receiving yards and no targets: those yards
and YAC survive, with both rates NULL. Gibbs first-down EPA/tgt is 0.3850 and
Success% 65.2; Jefferson's are 0.3031 and 63.2.

Independent diagnostics read full saved RDS inputs, confirm positive EPA matches
the source success flags in all three samples, and reconcile whole-season EPA
to weekly after explicitly adding excluded two-point EPA. Weekly includes those
plays, so directly matching its EPA to the nonconversion preview would be wrong.
These related-provider comparisons establish consistency, not independent NFL
correctness or coverage beyond the samples. All 24 input/export hashes verify;
bidirectional SQL comparison finds zero changes to canonical `player_splits`.
Source SHA256 remains `b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`;
source and preview closed without WALs. The full validator still rejects previews.

Evidence is ignored `data/upstream-r-trial/epa-preview-verification.json`,
`verify_epa_preview.py`, `verify_epa_inputs.R` and `preview-job-v4.log`.
Real regression fixtures retain Gibbs, Jefferson, Gonzalez (2004/2006), and
the zero-target 10-yard bucket. No serving integration, push or deployment.
Validation: 789 backend tests passed, 2 skipped. Cases cover missing EPA,
denominator and numerator disagreement, historical masks, valid zero/negative
EPA, incompletions/interceptions, lateral-only buckets, malformed context and
the actual SQL/worker lifecycle.
Next: receiving air-yard coverage/mapping, then other split dimensions and
the coordinated source-refresh/full-history candidate checks.

## Receiving air-yard extension (October 21)

Version 5 adds official `receiving_air_yards` and PBP `air_yards` to the bound
exports. The shared target-context validation and aggregation now live in
`pipeline/receiving_target_metrics.py` (formerly `receiving_rates.py`), avoiding
separate target populations for each field. Air yards is the summed depth of
all targets relative to the line of scrimmage, including incompletions. It may
be negative and is not the air component of completed receiving yards alone.

The preview requires target credits to match the original target-play count,
air yards on every target, and agreement between that sum and the official
numerator. A missing input or population/numerator discrepancy masks only air
yards. Missing EPA does not erase complete air yards. Malformed, nonfinite,
fractional or out-of-SQL-range air yards fail. Valid negative and zero totals
survive. A zero-target lateral-only bucket has zero target air yards, while its
EPA/tgt and Success% remain NULL. Receiving production is preserved throughout.

`air_yards_unavailable` is preview-only: pre-2006 air records are unsupported and
2003–08 target attribution is incomplete. Thus the supported date boundary is
2009, subject to actual per-bucket checks. It does not certify complete coverage
after that date or change existing API responses. YAC retains its independent
2006 boundary. Weekly reconciliation checks players with complete air-yard
splits; reports explicitly count available/unavailable rows and complete players
matched. Partial player sums are never certified as complete weekly totals.

Actual ignored preview: `data/receiving-preview-air-20261021.duckdb`, exports
`data/upstream-r-trial/preview-export-v5/`:

| Season | Players | Down rows | Available air-yard rows | Unavailable rows | Complete players matched weekly |
|---|---:|---:|---:|---:|---:|
| 2002 | 217 | 781 | 0 | 781 | 0 |
| 2006 | 141 | 492 | 0 | 492 | 0 |
| 2009 | 210 | 766 | 756 | 10 | 201 |
| 2024 | 220 | 813 | 813 | 0 | 220 |

In 2009, 13 original target plays have missing air yards across all identified
players; 10 admitted player/down buckets across 9 players are affected. Their
receiving production and EPA remain. Gonzalez first-down targets include one
missing air-yard input: 44 targets, 27 catches, 268 yards, 1 TD, 61 YAC,
12 receiving first downs and 0.1491 EPA/tgt survive, with air yards NULL. The
upstream aggregate is 362; exposing that as a complete total would hide the gap.
Real frozen input/expected-output fixtures cover this example.

2024 totals: Gibbs **-11 air yards**, Jefferson **1,682**. The existing zero-target
10-yard lateral bucket keeps zero air yards and NULL target-based rates.
An independent read-only replay joins raw stat-115 target credits to stat-111/112
team/play air yards, preserving all raw records. It matches every identified
official Down bucket in all four seasons. Official whole-season air yards match
weekly and the Down partition, including below-admission players. That source
agreement does not establish coverage: the 2002 zeros are still unavailable.

All 32 bound file hashes verify. Canonical `player_splits` is unchanged by
bidirectional EXCEPT ALL; all existing 2024 preview metrics match v4 exactly.
Source SHA256 remains `b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`;
source and preview closed without WALs. Evidence: ignored
`data/upstream-r-trial/air-preview-verification.json`, `verify_air_inputs.R`,
`verify_air_preview.py`, `preview-job-v5.log` and test logs.
No full candidate acceptance, source/serving replacement, push or deployment.
Validation: full backend 809 passed, 2 skipped (78.50s). The final real
Gonzalez-2009 regression and updated frozen inputs were then replayed with the
complete 124-test receiving/coverage/worker suite, all passing. Cases cover
field-specific missingness, valid negative/zero air, malformed numbers,
historical boundaries, partial weekly reporting and unchanged SQL production.
Next small checkpoint: apply the validated receiving approach to another play
context, starting with quarters. Full environment locking, coordinated source
refresh/qualification and full-history/dimension validation remain outstanding.

## Quarter split extension (October 21)

Version 6 exports both `down` and `quarter` partitions from official
`calculate_stats`. Quarters use the existing SQL labels 1–4 and OT; all periods
above four share OT. The producer filters play context before calculation,
retaining lateral recipients, and skips empty buckets instead of inventing zero
rows. The manifest binds both CSVs and lists both dimensions explicitly.

The adapter and loader are now `adapt_receiving_splits` and
`load_receiving_split_export`; both accept the supported dimension. Shared
bucket definitions/period validation live in `pipeline/receiving_dimensions.py`.
The target-metric helper selects its population by that dimension: missing down
does not erase a usable quarter play; missing quarter never becomes OT. The
same historical masks and independent EPA/air-yard completeness checks apply.
Rates are evaluated within each bucket, not summed across quarters.

The worker writes separate `receiving_down_preview` and
`receiving_quarter_preview` tables in one transaction. Each is reconciled to
weekly counts with the same qualification list. Preparation format version 2
stores `seasons[year][dimension]` reports. Failure of either partition removes
the new candidate. The full snapshot validator rejects either preview table
or the preparation marker, including a standalone quarter-only fragment.

Actual ignored output: `data/receiving-preview-quarter-20261021.duckdb`, exports
`data/upstream-r-trial/preview-export-v6/`:

| Season | Eligible players | Quarter rows | OT rows | Available air-yard rows | Available EPA/tgt rows |
|---|---:|---:|---:|---:|---:|
| 2006 | 141 | 585 | 21 | 0 | 0 |
| 2009 | 210 | 886 | 46 | 877 | 886 |
| 2024 | 220 | 924 | 44 | 924 | 924 |

Independent raw-credit replay matches every identified official player/quarter
for targets, catches, yards, TDs, YAC, receiving first downs and air yards in
all three seasons, including below-admission players. Quarter sums match whole
season and weekly counts. Modern displayed EPA/success rates match PBP within
their rounding precision when weighted by targets. Each available rate and air
total also matches its fresh PBP bucket. The 2009 air gaps affect nine quarter
buckets; changing the grouping does not restore missing inputs.

Real regression fixtures retain Gibbs/Jefferson 2024 and Gonzalez 2006. Jefferson
2024 OT: 1 target, 1 catch, 20 yards, 11 air yards, 1.4133 EPA/tgt and 100%
Success. Gibbs's quarter counts still total 63 targets, 52 catches, 517 yards,
4 TD, 593 YAC and 24 receiving first downs. Gonzalez retains 73/900/5, 319 YAC,
54 receiving first downs and NULL targets/rates/air. Synthetic tests cover
multiple OT periods, no OT, missing down, missing/invalid periods, a separately
credited lateral player, changed/missing quarter exports and rollback cleanup.

All 27 bound hashes verify. Every original `player_splits` row is unchanged by
bidirectional EXCEPT ALL; all Down preview rows in the three samples are exactly
unchanged from v5. Source SHA256 remains
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`; no source or
preview WAL. These checks establish scoped provider consistency, not independent
NFL correctness or full historical coverage. Evidence is ignored
`data/upstream-r-trial/quarter-preview-verification.json`, `verify_quarter_inputs.R`,
`verify_quarter_preview.py`, `quarter-verification.log` and `preview-job-v6.log`.
No source replacement, serving/refresh integration, push, deployment or accepted
full candidate. Next small context: home/away receiving splits. Complete R
locking, coordinated fresh source/qualification, remaining dimensions and full
historical validation are still required before publication.

Validation: 827 backend tests passed, 2 skipped (80.10s), including real frozen
quarter/OT outputs, target-context edge cases, actual worker rollback and the
full-gate preview rejection. Source fingerprint and absence of source/preview
WALs were rechecked after the suite. No active jobs remain.

## Home/away split extension (October 21)

Version 7 adds `home_away` to the same producer, adapter and worker dimension
loop. It uses `posteam_type` from each play, with `home` then `away` sort order
matching `splits_core.HOME_AWAY_DIM`. Designated teams determine the side even
at a neutral site. A player's latest season team does not determine earlier
plays' buckets, so traded players retain production from every team.

Unknown side remains unknown; malformed nonmissing labels fail instead of
falling through to away. Missing down/quarter does not prevent usable home/away
metrics. The same REG/nonconversion scope, credit attribution, qualification,
historical masks and independent EPA/air-yard checks apply. Missing buckets
do not produce invented zero rows. Bound context CSVs now include offensive,
home and away team IDs plus location for independent designation checks.

The worker adds `receiving_home_away_preview` in the same transaction and
records it under preparation format 2's `seasons[year][home_away]`. Counts
reconcile to weekly independently of the other dimensions. Missing, changed or
incorrect home/away exports reject the candidate and preserve the source.
The full validator also rejects a standalone home/away preview table.

Actual ignored output: `data/receiving-preview-home-away-20261021.duckdb`,
exports `data/upstream-r-trial/preview-export-v7/`:

| Season | Eligible players | Home rows | Away rows | Available air-yard rows | Available EPA/tgt rows |
|---|---:|---:|---:|---:|---:|
| 2006 | 141 | 141 | 141 | 0 | 0 |
| 2009 | 210 | 210 | 210 | 410 of 420 | 420 |
| 2024 | 220 | 220 | 220 | 440 | 440 |

Independent raw-credit replay matches all identified official home/away rows
for targets, catches, yards, TD, YAC, receiving first downs and air yards,
including below-admission players. Both sides sum to whole-season and weekly
counts. Available target metrics match fresh PBP; weighted displayed rates
reproduce whole-target rates within rounding precision. Each known offensive
side matches the designated team in PBP; no disagreements in any sample.
Neutral-location inputs include one game in 2009 and five in 2024.

Frozen real fixtures cover Gonzalez 2006 and Gibbs, Jefferson and Amari Cooper
2024. Cooper's target plays span CLE and BUF, yet his split totals remain
85 targets, 44 catches, 547 yards, 4 TD, 111 YAC and 25 receiving first downs.
Home: 22 catches / 301 yards / 4 TD; away: 22 / 246 / 0. The Jefferson input
includes 2024_05_NYJ_MIN, a neutral-location game whose MIN offensive plays
retain the designated home side. Gonzalez preserves 73 catches / 900 yards /
5 TD, 319 YAC and 54 first downs with historical targets/rates/air NULL.

The shared fixture is now named `upstream_receiving_context.csv`, reflecting
its use by all supported dimensions rather than only rates. Synthetic cases
cover trades, neutral designation, a lateral-only recipient, missing side,
invalid labels, missing down/quarter, SQL round trip and absent-side handling.

All 30 bound file hashes verify. Canonical `player_splits` and both prior Down
and quarter previews are unchanged by bidirectional EXCEPT ALL. Source SHA256
remains `b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`;
source and candidate have no WAL. Evidence is ignored
`data/upstream-r-trial/home-away-preview-verification.json`,
`verify_home_away_inputs.R`, `verify_home_away_preview.py`,
`home-away-verification.log` and `preview-job-v7.log`.
This is scoped provider consistency, not full historical certification or an
accepted publication candidate. Main ingestion, serving, refresh/deployment and
the source DB remain unchanged. No push or deployment. Next small context:
shotgun/under-center receiving splits. Full R locking, coordinated fresh sources
and qualification, remaining dimensions and full-history validation still precede
publication; assistant model/streaming work remains deferred.

Validation: 843 backend tests passed, 2 skipped (79.47s). Source fingerprint and
absence of source/candidate WALs were rechecked after the suite. No active jobs
remain. Private simplification notes remain excluded from Git.

## Shotgun split extension (October 21)

Version 8 adds `shotgun` through the existing dimension loop. Provider flag 1
maps to `shotgun` and 0 to `under_center`, sorted in that order, matching the
existing labels in `splits_core.SHOTGUN_DIM`. Missing flags stay unknown and
invalid nonmissing values fail; the preview does not reuse the legacy SQL's
ELSE-under-center treatment of NULL. These are recorded provider flags, not
new formation charting. Other dimensions' fields are not required to classify
a formation. The same credits, qualification, REG/nonconversion scope and
field-specific coverage rules apply.

The R dimension catalog now also drives bound export filenames and the
manifest's dimension list, reducing bookkeeping drift. The worker automatically
creates `receiving_shotgun_preview` in its existing transaction and records
`seasons[year][shotgun]`. Missing, changed or incorrect formation exports reject
the candidate. The full gate now rejects every `receiving_*_preview` table or
the preparation marker, including a synthetic future dimension, so adding a
new context cannot omit that publication guard.

Actual ignored output: `data/receiving-preview-shotgun-20261021.duckdb`, exports
`data/upstream-r-trial/preview-export-v8/`:

| Season | Eligible players | Shotgun rows | Under-center rows | Available air-yard rows | Available EPA/tgt rows |
|---|---:|---:|---:|---:|---:|
| 2006 | 141 | 129 | 141 | 0 | 0 |
| 2009 | 210 | 208 | 210 | 408 of 418 | 418 |
| 2024 | 220 | 220 | 216 | 436 | 436 |

Absent formation buckets are not invented. Every eligible player remains in at
least one bucket. Independent raw-credit replay matches all identified official
player/formation rows for targets, catches, yards, TD, YAC, receiving first
downs and air yards, including below-admission players. Both formations sum to
whole-season and weekly counts. Available target metrics match fresh PBP; their
weighted displayed rates match whole-target rates within rounding precision.
Exported formation flags also match the full saved PBP inputs. All target plays
in the three samples have 0/1 flags; this does not certify all historical years.

Frozen real cases cover Gonzalez 2006/2009 and Gibbs/Jefferson 2024. Gonzalez
2006 preserves 73 catches, 900 yards, 5 TD, 319 YAC and 54 first downs with
targets/rates/air NULL. In 2009, the incomplete air-yard input masks one of his
formation air totals; all receiving counts and both EPA/success rates survive.
Jefferson 2024: shotgun 77 catches / 1,041 yards / 7 TD, under center 26 / 492 /
3, totaling the reviewed 103 / 1,533 / 10. His shotgun EPA/tgt is 0.3666.
Synthetic cases cover binary/nullable/bad flags, absent buckets, missing unrelated
context, lateral production, field-specific masks and the actual SQL schema.

All 33 bound hashes verify. Canonical `player_splits` and all three previous
Down/quarter/home-away preview tables are unchanged by bidirectional EXCEPT ALL.
Source SHA256 remains
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`; source and
candidate have no WAL. Evidence is ignored
`data/upstream-r-trial/shotgun-preview-verification.json`,
`verify_shotgun_inputs.R`, `verify_shotgun_preview.py`,
`shotgun-verification.log` and `preview-job-v8.log`. Preliminary coverage was
reviewed from bound v7 PBP with `review_shotgun.R`.

This is scoped provider consistency, not independent charting correctness or a
publishable full candidate. Main ingestion, serving, source DB and deployment
remain unchanged; no push or deployment. Next small context: field-position
receiving splits. Full R locking/build, coordinated fresh sources/qualification,
remaining dimensions and full historical validation still precede publication.
Assistant model/streaming work remains deferred.

Validation: 860 backend tests passed, 2 skipped (84.83s). Source fingerprint and
absence of source/candidate WALs were rechecked after the suite. No active jobs
remain; private simplification notes remain excluded from Git.

## Field-position split extension (October 21)

Version 9 adds `field_zone` to the shared producer/adapter/worker loop, using
the play's starting `yardline_100` (distance to the opponent's goal line):

- `own_territory`: greater than 50; sort order 1.
- `opp_territory`: greater than 20 through 50; sort order 2.
- `red_zone`: 20 or less; sort order 3.

This matches `splits_core.FIELD_ZONE_DIM`, including exactly midfield and the
opponent's 20-yard line. The zones are disjoint and describe the pre-play spot,
not where a catch or lateral ends. The accepted domain is finite 0–100; valid
fractional spots remain precise. Unknown stays unknown, while invalid/out-of-range
spots fail. Lateral recipients inherit the same play context before official
credit calculation. The historical masks, target-role rates, independent air
coverage, qualification and REG/nonconversion scope are unchanged.

The worker automatically creates `receiving_field_zone_preview` in the same
transaction and records `seasons[year][field_zone]`. Every admitted player must
survive and the zones must match weekly counts by player. Missing, changed or
incorrect field-zone exports reject the candidate. The generic preview gate
already rejects this table independently of its preparation marker.

Actual ignored output: `data/receiving-preview-field-zone-20261021.duckdb`,
exports `data/upstream-r-trial/preview-export-v9/`:

| Season | Eligible players | Own rows | Opponent rows | Red-zone rows | Available air-yard rows | Available EPA/tgt rows |
|---|---:|---:|---:|---:|---:|---:|
| 2006 | 141 | 141 | 141 | 137 | 0 | 0 |
| 2009 | 210 | 210 | 210 | 210 | 621 of 630 | 630 |
| 2024 | 220 | 220 | 220 | 219 | 659 | 659 |

Absent zones do not get invented zero rows. All eligible players remain in at
least one zone. Independent raw-credit replay matches every identified official
player/zone for targets, catches, yards, TD, YAC, receiving first downs and air,
including below-admission players. Zone sums match whole-season and weekly
counts. Available target metrics match fresh PBP, and weighted displayed rates
match whole-target rates within rounding precision. Exported field positions
match the bound full PBP inputs. No source target play lacks field position in
the three samples; this does not certify all historical seasons.

Real frozen fixtures cover Gonzalez 2006/2009 and Gibbs/Jefferson 2024. Reviewed
season totals survive each partition, with historical targets/rates/air NULL
in 2006. Gonzalez 2009 retains all counts/EPA while one incomplete air-yard
zone remains NULL. Synthetic cases check exact 20/50 boundaries, fractional
and endpoint spots, nullable unknowns, bad ranges, absent zones, unrelated
missing context and a 75-yard lateral TD whose entire production stays in
the play's starting own-territory bucket. SQL round trips exercise the actual
`player_splits` schema.

All 36 bound file hashes verify. Canonical `player_splits` and all four previous
Down/quarter/home-away/shotgun previews are unchanged by bidirectional EXCEPT
ALL. Source SHA256 remains
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`; source and
candidate have no WAL. Evidence is ignored
`data/upstream-r-trial/field-zone-preview-verification.json`,
`verify_field_zone_inputs.R`, `verify_field_zone_preview.py`,
`field-zone-verification.log` and `preview-job-v9.log`.

Scope confirmed by the user: finish the field-position checkpoint only. The
remaining receiving contexts, complete R locking/build, coordinated fresh
source/qualification and full-history/full-candidate validation are later
work. No source replacement, main ingestion/serving integration, accepted
publication candidate, push or deployment. Assistant model/streaming remains
deferred. The results establish scoped provider consistency, not independent
NFL correctness or full historical certification.

Validation: 875 backend tests passed, 2 skipped (103.24s). Source fingerprint
and absence of source/candidate WALs were rechecked after the suite. No active
jobs remain. This completes the user-selected field-position checkpoint.

## Partial-context conservation controls (October 21, 2026)

The next bounded checkpoint implements a pure validation contract in
`pipeline/receiving_partition_validation.py`. It receives independently classified
play context, the producer's explicit membership, official per-bucket results and
three official reference calculations: classified union, excluded union and whole
population. It checks unique game/play keys and exact membership before comparing
all seven observed receiving count fields by player. Bucket sums must equal the
classified reference; classified plus excluded must equal the whole reference.
Checks include players outside admission and unidentified-player credits. Missing
classification cannot make a supplied globally qualified player disappear from
the whole reference. Players with only excluded production are reported explicitly.

This is validation, not a second receiving calculator. It does not infer unknown
context, turn missing metric values into zero, replace eligibility rules, certify
historical targets or validate target-role rates. Historical mask flags remain in
the coverage report. Input revisions are SHA256 records supplied by the verified
reader; this pure function checks their shape, not publisher authenticity.

`experiments/receiving_partition_controls.R` generated two frozen controls with
actual nflfastR 6.0.0/nflreadr 1.5.1 calls. The full PBP RDS inputs were checked
against the completed v9 manifest before reading. FTN was exported read-only from
the unchanged source DB to ignored `data/upstream-r-trial/partition-charting-2024.csv`
and hash-checked before the R join. Duplicate charting keys or a multiplying join
fail. The control records hashes for PBP, charting where used and the actual
official credit inputs captured in that R process.

Frozen output: `tests/fixtures/upstream_receiving_partitions.json`. Each control
contains **three selected real REG nonconversion completions**, not a whole game
or season. Supplied player lists select the sampled receivers for these controls;
they are not a new minimum-volume qualification rule.

| Control | Classified receiving production | Excluded receiving production | Whole sample |
|---|---|---|---|
| 2009 missing original-pass depth | 2 catches, 28 yards | 1 catch, 5 yards | 3 catches, 33 yards |
| 2024 unsupported rush count | 2 catches, 27 yards, 0 TD | 1 catch, 14 yards, 1 TD | 3 catches, 41 yards, 1 TD |

The 2009 unknown-depth play is `2009_01_PHI_CAR`, play 4173 (D. Williams).
The charting control is `2024_07_HOU_GB`, play 981 (T. Kraft touchdown), with
`n_pass_rushers=45`. The charting row exists, but that value is outside the existing
1–11 classification contract; it is neither a standard rush nor proof of a blitz.
The receiving catch/yards/TD survive in excluded and overall counts. Kraft has no
classified production in this three-play sample and remains globally represented.
This demonstrates provider consistency, not independent NFL correctness or a
claim that all charting gaps have this cause.

Additional tests cover wholly unavailable optional context, complete partitions,
relabeled/missing/extra/duplicate play identities, duplicate summary rows, wrong
season/scope, changed counts, per-player errors concealed by equal grand totals,
unidentified credits, zero-target/catch lateral recipients, negative production
and invalid/unknown count values. Counts must be supplied; missing counts fail
rather than becoming zero. Empty references retain explicit schema.

Integration is the next checkpoint. No producer/worker schema change, preview DB
rebuild, serving/UI integration, source replacement or publication was performed.
The existing five preview dimensions and strict full-snapshot gate remain as-is.

Validation: 907 backend tests passed, 2 skipped, including 32 new conservation
tests. The source SHA256 remains
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`, with no
source WAL. Ignored regeneration artifacts are `partition-controls.log`,
`receiving-partition-controls.json`, the charting CSV and captured credit RDS
files in `data/upstream-r-trial/`. The private simplification plan stays excluded.

## Coverage-aware producer/worker integration (October 21, 2026)

The preview job now executes the conservation contract during preparation.
Export schema 10 adds three files per dimension/season:

- `membership-{dimension}-{year}.csv`: every REG nonconversion game/play key,
  with the selected label or a missing label for excluded plays.
- `classified-{dimension}-{year}.csv`: official calculation over the classified
  union, independently of the per-bucket calculations.
- `excluded-{dimension}-{year}.csv`: official calculation over the excluded union.

The producer assigns a label once per play, asserts disjoint assignment, and uses
that vector for membership and official subset calls. The Python classifier then
derives its own expected labels from the verified context export. Whole-result
reuse is allowed only when the subset is exactly the full play set. Empty
populations retain headers and generate no invented zero player rows. New files
are SHA256-bound before the completion marker is written last.

`pipeline/receiving_preview_validation.py` owns verified partition loading and
adapted/whole-reference checks. The worker now delegates those checks rather
than carrying its former inline whole-weekly comparison for every dimension.
It reads the shared whole/context/weekly frames once from verified bytes. The
strict official whole-season versus weekly gate remains separate; weekly keys
must be unique by player/week. Applicable targets, catches, yards, TD, YAC,
receiving first downs and observed air sums are compared for globally admitted
players. Historical target/YAC/air policies and target-role rate gates remain.
Equal raw air sums still do not establish per-target completeness.

Every dimension validates exact membership, bucket/classified count equality
and classified-plus-excluded/whole equality before admission filtering, including
unidentified credits. Adapted rows then reconcile to the classified reference.
A player whose entire production is excluded may have no row in this view,
while remaining globally admitted and represented by the whole reference and
other usable views. Opposing lateral yards in different buckets may cancel in
the union; observed nonzero bucket rows still survive. Nullable string/empty
export handling was corrected for genuine empty classified/excluded populations.

Preparation record format 3 separates `whole_references[year]` from
`seasons[year][dimension]`, with per-dimension coverage statuses, reasons, play
counts, verified input hashes, classified/excluded/overall qualified production
and players without classified production. Count statuses are `matched_classified`
rather than a misleading weekly-match claim for a potentially partial view.
The available-air player count likewise describes classified-reference matching.

Actual run: ignored `data/receiving-preview-coverage-20261021.duckdb`, with
`data/upstream-r-trial/preview-export-v10/`:

| Season | Qualified players in each view | Down rows | Quarter rows | Home/away rows | Shotgun rows | Field-zone rows |
|---|---:|---:|---:|---:|---:|---:|
| 2006 | 141 | 492 | 585 | 282 | 270 | 419 |
| 2009 | 210 | 766 | 886 | 420 | 418 | 630 |
| 2024 | 220 | 813 | 924 | 440 | 436 | 659 |

All 81 bound file hashes verify. The strict whole-weekly and all 15 partition
checks pass. Each of the five preview tables is identical by bidirectional
EXCEPT ALL to the prior field-zone preview, and canonical `player_splits` is
identical to the source. Down/home-away/field-zone have excluded play populations
but zero qualified receiving production on those excluded plays in these samples;
quarter/shotgun classify every play. Coverage status refers to the stated play
population, not an automatic claim of incomplete receiving totals.

The earlier real missing-depth and unusable-charting controls remain pure
conservation controls. New real-worker lifecycle tests use a deterministic
producer to exercise partial context with nonzero excluded receiving production
and wholly unavailable context, preserving unrelated views, masks and canonical
rows. Faults cover wrong membership, duplicate keys, changed/missing reference
bytes/hashes, empty-but-required bucket output, wrong classified/excluded totals,
duplicate weekly rows and self-consistent wrong subset/whole counts that must
still fail against the independent weekly reference. All existing cleanup,
path-binding and nonpublishable-preview checks remain in force.

Validation: 922 backend tests passed, 2 skipped (118.95s). The source SHA256 is
unchanged at `b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`;
source/candidate have no WAL. The unchanged full snapshot gate explicitly rejects
this actual preview. Ignored evidence: `verify_coverage_preview.py`,
`coverage-preview-verification.json`, `coverage-verification.log`,
`coverage-integration-tests.xml`, `coverage-integration-tests.log` and
`preview-job-v10.log` under `data/upstream-r-trial/`.

The 12 remaining dimensions, FTN build input binding, full R locking/portable
build, coordinated fresh qualification, complete historical checks and main
pipeline/API/UI integration remain. Next bounded view is `game_script`
(leading/tied/trailing). No source replacement, publication, push or deployment.
