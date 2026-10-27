# Native passing split integration

The ordinary offline split builder can consume source-bound nflfastR passing
exports alongside the captured receiving inputs. Serving reads the prepared
`player_splits` table; neither the builder's replay validator nor the API runs R
or downloads source data.

## One calculation and acceptance path

1. Capture the original PBP, weekly statistics, detailed credits and charting.
2. The pinned native calculator computes whole, classified, excluded and bucket
   statistics for each requested passing view. It reuses the captured receiving
   membership files: the same source play belongs to the same situation in both
   categories. Python independently verifies those assignments. Passing's
   `pass_depth`/`pass_location` names map to receiving's depth/direction names.
3. The adapter checks counts and first downs against weekly/whole references
   before applying the existing 50-dropback admission rule. It verifies the
   play-level credit projection and each metric's PBP population. Unsupported
   values remain NULL with individual reasons; excluded production stays in
   the whole reference and per-player coverage records.
4. A complete, immutable export index is supplied to the ordinary offline job.
   A partial diagnostic export cannot enter a build. Every loaded season must
   have matching captured inputs and native rows.
5. Passing, receiving and rushing replacements share the existing season
   transaction. A late insert or metadata failure rolls back every category.
   An official passing snapshot cannot fall back to an input-free legacy build.
6. Read-only validation replays the same adapter against the captured exports
   and compares every stored row and coverage record. It replaces the legacy
   passing subtotal/rate reconstruction only after that exact replay succeeds.
   The source-PBP versus weekly EPA check retains the existing 0.005
   per-attempt tolerance, including conversion EPA in the weekly population.

The native producer memoizes identical play subsets within an export run. It
does not patch the calculator, namespace or transport. Its source, R dependency
lock, request, inputs and output bytes are checked. Fresh detailed credits must
match the capture on every consumed game/play key, including duplicate records;
newer plays outside that subset do not invalidate a historical replay.

Exports bind to their own season's source manifest and consumed values. The
outer collection can change when another season refreshes, and the same capture
can move into a CI workspace. Neither change requires rerunning unchanged
historical R exports. The original export collection revision and current build
revision are both recorded; changed source bytes or calculation policy fail.

Situations describe recorded source plays. When a play contains multiple throws,
its depth/direction labels are shared by all credited passers; the source does
not provide separate labels for every throw. Count attribution is checked
separately from those definitions. See [the Down metric checks](RECEIVING_RELEASE_VALIDATION.md)
for first-down, EPA, success, CPOE and air/YAC policies.

## Commands

Run from `api/` with the locked Python environment. Each output path must be new.
The export defaults to all 17 views; `--dimensions down quarter` selects a
diagnostic subset that the main build will reject.

```powershell
uv run --locked python -m jobs.passing_preview `
  --core-inputs data/captured-core --exports data/passing-2024 --season 2024 `
  --rscript PATH_TO_RSCRIPT --r-library PATH_TO_LOCKED_LIBRARY

uv run --locked python -m jobs.passing_inputs `
  --core-inputs data/captured-core --exports data/passing-2024 data/passing-2025 `
  --output data/passing-inputs

uv run --locked python -m jobs.prepare `
  --source data/closed-source.duckdb --candidate data/new-candidate.duckdb `
  --seasons 2025 --core-inputs data/captured-core `
  --passing-inputs data/passing-inputs --rebuild-all-analytics

uv run --locked python -m jobs.validate `
  --database data/new-candidate.duckdb --core-inputs data/captured-core `
  --passing-inputs data/passing-inputs
```

The index must cover every loaded season that the job rebuilds or validates;
the two-season index above is only appropriate to a two-season database.
Source outcome records, game coverage, schema/index checks, other categories
and representative HTTP checks remain part of the complete release process.

The official publication guard remains during this checkpoint. `jobs.prepare`
continues to reject and clean up candidates that do not pass the complete
release boundary. A separately owned diagnostic build can be inspected and
validated without replacing the source or publishing its result. The legacy
profile/leaders/game availability audit and offline publication migration are
still separate remaining work.

## Executed proof, October 27, 2026

All **28 captured seasons (1999-2026)** passed the native export and replay
checks for **17 views each (476 season/views)**. The immutable index is
`api/data/passing-allviews-inputs-20261027/`, SHA256
`ef98cbf7d64066da8c871ffe2052d80bb0f9cd0d11cfe53cd0a7e6ae5669d09d`.
Each year remains bound to its captured receiving source run and typed inputs.

The ordinary builder rebuilt a separate candidate,
`api/data/passing-integrated-20261027.duckdb`, with:

| Category | Prepared split rows |
|---|---:|
| Passing | 64,953 |
| Receiving | 266,762 |
| Rushing | 147,719 |

Receiving and rushing are exactly equal to the previous coordinated database
in both directions, including every stored field. Passing previously had
65,537 rows. Sparse, unsupported or unclassified populations are now represented
by source-checked coverage and excluded references rather than invented labels
or stat-empty rows. This row-count reduction does not discard the independently
checked whole passing counts. Identified-player count conservation and
availability policies apply before admission, including low-volume players.
Unidentified model aggregates are checked without admitting a player.

The candidate passed source/preparation/FTN checks, schemas, keys, lookup indexes,
awards/rating bounds, supplied-game analytics coverage, all 28 receiving and
passing replays, and the remaining historical statistical checks under their
existing policies and tolerances. Passing source-EPA mismatches are zero in
every year. The previous Testaverde passing-count failure is resolved without
an override or larger tolerance. The only terminal rejection is the retained
official publication guard.

A separate read-only HTTP pass verified **102 requests**: the existing 73
representative checks plus 29 passing samples across every season, including
the flagged Testaverde row selected from its diagnostic record. Passing payloads
match the candidate's canonical rows, including NULL fields. This does not
claim the remaining legacy receiving availability audit is complete.

Final backend verification: **1,369 passed, two skipped** (1,371 tests, 625.68s).
Controls cover all views, missing context, source/manifest corruption, per-play
credit populations, unchanged-leaf reuse after collection changes or relocation,
atomic rollback after a late insert, exact row/metadata replay, input-free build
rejection and passing-input propagation through the offline subprocesses.

Ignored evidence:

- `api/data/passing-allviews-YEAR-20261027/` and adjacent logs; 2004 uses
  `passing-allviews-2004-20261027-pilot-v2/`.
- `passing-allviews-index-20261027.log` and `passing-allviews-source-coherence-20261027.json`.
- `passing-integrated-build-20261027.{json,log}` and
  `passing-integrated-validation-20261027.{json,log}`.
- `passing-allviews-backend-final-20261027.{xml,log}`.
- `passing-integration-proof-20261027.json`, combining the data/API proof,
  policy hashes, regression result and exact unchanged-category comparison.

The candidate SHA256 is
`9c7da96b871b37b6a68b9028eb8ee80b86e458406c37e27f7003da193aa61556`.
Its hash stayed unchanged during read-only verification. The serving database,
earlier receiving API proof and original coordinated development database all
retain their previous hashes, with no WALs. No push, deployment, source database
replacement or publication-guard removal occurred. Current-season results cover
the recorded supplied games; they are not a freshness certificate.
