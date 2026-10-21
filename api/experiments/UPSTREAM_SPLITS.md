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
supported receiving counts. The next implementation checkpoint is a small
offline adapter. Before production: lock the R environment/build, define input
and output contracts, preserve qualification and historical null policies, and
evaluate other dimensions and full history.
Receiving EPA, success rates and target-specific dimensions still need explicit
definitions. No metric/rating/comparables correctness is established here.

Source DB SHA256 before and after:
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`.
No WAL, push, deployment or serving-data replacement.

References: [calculator documentation](https://nflfastr.com/reference/calculate_stats.html),
[upstream subset feature](https://github.com/nflverse/nflfastR/pull/524).
