# Receiving history validation

Validation run: October 24–25, 2026. Scope: every season 1999–2026, regular season,
excluding two-point attempts, across all 17 existing receiving views. Each season
uses its own isolated preview candidate and captured fresh inputs. Nothing is
published or connected to serving by this exercise.

The official calculator runs with R 4.6.1, nflfastR 6.0.0, nflreadr 1.5.1 and the
49-package `api/r/renv.lock`. Qualification uses the same fresh play context and
existing minimum of 25 original-receiver attempt plays. Unknown historical
official target counts are not used to determine eligibility.

## Final result

All **28 seasons / 476 season-view combinations** passed the available-data
calculation checks. **26 seasons have complete game coverage** against the
captured completed-game schedules. The other two, 1999 and 2000, retain explicit
source gaps for three missing games; they are not full-season completeness
successes. There were **no calculation failures or skipped seasons**.

The audit covered **7,058 of 7,061 scheduled completed REG games**, **5,622
qualified player-seasons** and **266,157 preview rows**, verifying **2,268 bound
producer files** plus their independent source controls. Every run used the same
producer revision, R dependency lock, R 4.6.1 and 49-package version set. FTN inputs
loaded for every supported season, 2022–2026. No gate or numeric tolerance was
weakened. The consolidated command exits **2** because game completeness fails
in the two recorded seasons, not because a calculation crashed.

In this table, **Passed** means the available-data checks and completed-game
coverage passed. It does not mean every receiving field or split context exists.
Targets/rates in 2003–2008, pre-2006 YAC, early air/QB-hit data and pre-2022
charting keep their existing explicit availability policies. Other per-view gaps,
including the 2026 surface gap below, remain recorded.

| Season | Supplied / expected REG games | Qualified receivers | Audit result |
| --- | ---: | ---: | --- |
| 1999 | 247 / 248 | 208 | Source gap |
| 2000 | 246 / 248 | 202 | Source gap |
| 2001 | 248 / 248 | 201 | Passed |
| 2002 | 256 / 256 | 217 | Passed |
| 2003 | 256 / 256 | 149 | Passed |
| 2004 | 256 / 256 | 152 | Passed |
| 2005 | 256 / 256 | 151 | Passed |
| 2006 | 256 / 256 | 141 | Passed |
| 2007 | 256 / 256 | 159 | Passed |
| 2008 | 256 / 256 | 149 | Passed |
| 2009 | 256 / 256 | 210 | Passed |
| 2010 | 256 / 256 | 217 | Passed |
| 2011 | 256 / 256 | 224 | Passed |
| 2012 | 256 / 256 | 221 | Passed |
| 2013 | 256 / 256 | 220 | Passed |
| 2014 | 256 / 256 | 223 | Passed |
| 2015 | 256 / 256 | 240 | Passed |
| 2016 | 256 / 256 | 222 | Passed |
| 2017 | 256 / 256 | 230 | Passed |
| 2018 | 256 / 256 | 233 | Passed |
| 2019 | 256 / 256 | 215 | Passed |
| 2020 | 256 / 256 | 227 | Passed |
| 2021 | 272 / 272 | 238 | Passed |
| 2022 | 271 / 271 | 220 | Passed |
| 2023 | 272 / 272 | 222 | Passed |
| 2024 | 272 / 272 | 220 | Passed |
| 2025 | 272 / 272 | 223 | Passed |
| 2026 | 94 / 94 | 88 | Passed |

## What the checks establish

The preview worker validates whole-season counts against published weekly data;
independently classifies each supplied play; verifies exact bucket membership;
and reconciles bucket, classified, excluded and whole-reference production for
every player before admission filtering. Missing context never silently assigns
a play to a confident bucket. Field-specific NULL policies remain enforced.

The independent post-build audit additionally checks:

- All producer and audit file fingerprints, manifest links and candidate source.
- Exported context against the captured full PBP snapshot, including the exact
  original-receiver eligibility counts, calculated separately in R.
- Supplied game IDs against a separately downloaded schedule of completed REG
  games. A matching weekly reference is not sufficient to certify game coverage.
- Seven observed receiving count fields against a separate replay of captured
  stat-credit records for every identified player/bucket, including players below
  the admission threshold. The worker separately retains unidentified credit
  groups in its conservation checks.
- Available target-role EPA, positive-EPA success and air yards against the
  underlying target-play populations. Success rounding uses exact rational counts
  so a binary mean cannot turn 51/80 = 63.75% into an incorrect 63.7% audit value.
- Canonical `player_splits` equality with the source and rejection of every
  receiving-only candidate by the unchanged full snapshot gate.

These checks prove consistency and stated coverage of captured provider data.
They do not independently certify every NFL stat correction or reconstruct
unpublished play context. Weekly data and stat credits share upstream sources;
agreeing numbers can still omit a whole game.

## Confirmed upstream game gaps

| Season | Supplied REG games | Completed schedule games | Missing game IDs |
| --- | ---: | ---: | --- |
| 1999 | 247 | 248 | `1999_01_BAL_STL` |
| 2000 | 246 | 248 | `2000_03_SD_KC`, `2000_06_BUF_MIA` |

The upstream database helper explicitly excludes these same three broken games.
The nflfastR 6.0.0 release notes say the project no longer supports fixes for
1999–2000 because their source data is inconsistent, although `load_pbp()` still
provides those seasons. See the [upstream helper source](https://github.com/nflverse/nflfastR/blob/master/R/helper_database_functions.R)
and [release notes](https://nflfastr.com/news/index.html).

The audit retains and validates the supplied games and returns `source_gap` for
these seasons. The CLI exits **2**, preserving a failed season-completeness check.
There is no exception that quietly treats them as full-season successes. Their
stats, context splits and eligibility can be affected by the absent games; those
limitations need an explicit user-visible scope before publication. Known-good
observed production does not need to be erased.
The captured raw stat-credit files also contain zero records for those three
game IDs, so rerunning the calculator against these same inputs cannot recover
the missing production.

## Current-season freshness

The original local snapshot contains only 323 plays from two 2026 games. The
fresh 2026 input contains 16,551 play rows, including 16,508 REG nonconversion
plays from **94 completed games through October 22**, matching all 94 completed
REG games in the independently captured schedule. It admits **88 receivers**.
The independent audit of all 17 current-season views passed.

This identifies a stale stored snapshot, rather than a requirement to omit the
current season. The main build must refresh its other inputs and analytics
coherently; receiving previews do not update those copied tables.

Current-season surface metadata is separately incomplete: **29 of the 94 games**
have blank surface in both captured PBP and the independent schedule. These are
the 2026 weeks 5–6 games and the supplied week 7 game. The surface view excludes
**721 catches / 8,174 receiving yards / 45 receiving TDs** for the admitted
receiver set. Those counts remain in other views and the whole reference.
The blitz view separately excludes 4 catches / 35 yards / 1 TD under its charting
coverage/rush-count policy. These overlapping view scopes are not lost season
production and must not be added together.

This is a missing-context issue despite complete game coverage. The schedule
does not supply a direct surface fallback for these games. Inferring surface
from the nominal home team would require separate verification, particularly
for neutral-site games; no such inference or data repair was made in this pass.

## Repeating a season audit

From `api/`, restore the [locked R environment](../api/r/README.md), then run the
existing `jobs.receiving_preview` command with a new candidate and exports folder
for the chosen season. Audit that candidate with:

```powershell
uv run --locked python -m experiments.receiving_history_audit `
  --source data/nfl.duckdb --candidate data/history-2001.duckdb `
  --exports data/history-2001-exports --season 2001 `
  --rscript data/upstream-r-trial/R-4.6.1/bin/Rscript.exe `
  --r-library data/receiving-r-clean-20261023
```

The first audit captures fresh schedule data and extracts source controls from
the bound RDS inputs using `experiments/receiving_history_sources.R`. Subsequent
audits reuse those fingerprinted controls for that input snapshot. Use a new
preview/export folder to obtain a new data and coverage snapshot.

Exit **0** means the independent checks and supplied/expected game coverage pass;
exit **2** means the checks on available data pass but game coverage is incomplete;
other nonzero exits indicate an audit/setup failure. Assertions cannot be disabled
with Python `-O`. A zero audit exit never authorizes snapshot publication.

The JSON `audit-result.json` beside each producer manifest records individual
view coverage, excluded production, game gaps and source/auditor fingerprints.
Excluded production is view-specific and can overlap across dimensions; do not
sum it across views as if those were separate lost plays.

## Evidence and remaining integration

Ignored local evidence:

- `api/data/receiving-history-20261024/final-summary.json`: consolidated outcome
  after re-auditing all 28 seasons with the finalized audit implementation.
- `api/data/receiving-history-20261024/YEAR/`: retained per-season candidate,
  producer exports, source controls, preparation record and logs, 1999–2025.
- `api/data/receiving-history-current-20261024.duckdb` and corresponding export
  folder: current-season candidate and evidence.
- `api/data/receiving-history-20261024/final-audit-YEAR.log`: final independent
  checks; earlier development audit logs are retained separately for diagnosis.
- `api/data/receiving-history-backend-tests.xml` and `.log`: **1,060 passed,
  2 skipped**, including eight new independent-audit controls.

All candidates remain receiving-only previews and are rejected by the unchanged
full snapshot gate. Original canonical split rows are unchanged in every
candidate. The source SHA256 remains
`b09f8e13743d912d9da9de24f2002ab258a144f49aa9ed33d5033e8633ed9daf`.
The source and candidates closed without WAL files. No source replacement,
push, deployment, main-build integration or serving change occurred.

Next implementation must integrate the official receiving path with coherent
fresh core inputs, retain game/context/field coverage in candidate metadata and
API/UI responses, and fix NULL/partial-scope aggregation before exposing these
rows. In particular, 1999–2000 must not be presented as complete seasons and the
2026 surface view must show its covered scope. Production-platform restoration,
downstream ratings/comparables checks and the full snapshot/HTTP gates remain
required. This audit does not waive any of them.
