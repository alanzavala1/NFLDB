# Offline data preparation

The serving app reads a DuckDB database file containing source data and prepared
analytics. A **snapshot** means that complete file at a particular revision.
The goal is to build and verify a candidate snapshot offline, then ship it with
the app. Visitors should only read published data.

## Current preparation flow

The scheduled job still uses `jobs.refresh` and updates its downloaded database
in place. The new, opt-in candidate command wraps the same ingestion pipeline
in a separate working file; publication has not been migrated yet.

```text
jobs.refresh → ingest.run_ingest
                    ├─ pipeline.loading coordinates adapters and storage
                    ├─ pipeline.player_stats composes player_game_stats
                    │      └─ pipeline.play_stats computes play-derived lines
                    ├─ pipeline.loading loads advanced and supplemental feeds
                    └─ pipeline.analytics.prepare_analytics
                           ├─ seasonal analytics
                           ├─ globally calibrated analytics
                           └─ persisted lookup indexes
```

`api/pipeline/analytics.py` owns the analytics preparation order. It calls the
existing builders and their locks. It does not download feeds. Source loading and player-game statistics
must be prepared before calling it. Unexpected builder failures propagate and
stop later steps; a known missing-schema fallback is still owned by each builder.
Completing this sequence alone does not establish snapshot completeness.

| Prepared data | Rebuild scope |
|---|---|
| Team season analytics | Each refreshed play or official-weekly season with stored plays |
| Weekly power rankings | Each refreshed play or official-weekly season with stored plays |
| Player game ratings | All loaded seasons, one global calibration |
| Offensive-line unit grades | All loaded seasons, one global calibration |
| Offensive player splits | Each refreshed play or official-weekly season with stored plays |
| Defensive player splits | Each refreshed play or official-weekly season with stored plays |
| Team offense/defense splits | Each refreshed play or official-weekly season with stored plays |
| Career summaries and comparable players | All loaded careers, once per batch |
| Lookup indexes | After table preparation |

The order matters. Player-game statistics must exist before analytics consume
them. Global calibration means that loading a new season can change a game's
percentile compared with the wider history; rebuilding only that new season
would mix scales. Those global rebuilds therefore run once per ingest batch.

## Core seasonal downloads

`api/pipeline/sources.py` owns downloading play-by-play and official weekly
player statistics. It has no database dependency. Each result identifies the
seasons loaded, assets that returned HTTP 404, and the combined data frame.
Schedule and roster downloads live in `pipeline/context_sources.py`; optional
vendors have separate adapters below. The loading module coordinates their
validation and storage. It returns `RawLoad`, containing plays plus explicit core
source outcomes, and each subsequent phase adds its own outcomes.

The schedule adapter requires rows for every requested season and validates
the game/team/score keys. It shares its CSV location with upstream season
discovery and preserves the library's season filter. The roster adapter fetches each season independently,
retaining the installed library's identity renaming, birth-date parsing, existing
month-based age calculation and null-ID filtering. It reports a real 404
separately; missing rosters are allowed only for unplayed seasons without plays.
Unexpected provider errors retain source, season and original cause.

| Source outcome | Behavior |
|---|---|
| Valid seasonal asset | Validate, combine and report the loaded season |
| HTTP 404 | Report the missing asset separately |
| Timeout, HTTP 5xx, invalid file or unexpected exception | Raise `SourceError` with source, season and original cause |
| Empty published asset or invalid required schema | Raise `SourceError` |

The play adapter reads the same parquet assets directly with pandas. This avoids
the installed `nfl_data_py` play loader's broken exception handler, which masks
the actual error with `NameError`. The existing retained-column list, explicit
season labeling and float32 conversion are preserved. A full-file retry is
allowed only when fastparquet reports missing requested columns in an older
schema; arbitrary failures do not trigger that larger download.

The ingestion caller decides whether a missing asset is acceptable. Missing plays
with completed games in the downloaded schedule fail the refresh. If plays are
available, official weekly statistics are required, preventing a missing download
from silently choosing the less accurate play-derived offensive fallback. That
fallback remains available to separate historical repair code with no weekly
table; it is not the normal refresh policy.

Weekly schema and season values are checked on each asset before concatenation.
Otherwise one year's valid columns could conceal another year's broken schema
by filling it with nulls. Downloads and validation finish before weekly storage
changes. A legacy-schema replacement requires the entire requested historical
range; an incomplete download leaves the old table intact.

For an unplayed season whose plays return 404, ingestion still stores schedules
and rosters, then stops before player statistics and analytics. Mixed requests
replace plays and rebuild downstream statistics only for downloaded seasons,
preserving unavailable seasons' stored data. A legacy weekly schema migration
downloads official history too: rebuild player-game statistics for every updated
weekly season with stored plays, then prepare seasonal analytics for that expanded
scope. Historical plays are read one season at a time to bound memory; vendor
downloads remain scoped to the requested play seasons. Failed required-feed downloads stop
the refresh before its upstream watermarks advance. Required weekly data must
also contain identified players in each played season after orphan filtering.

## Optional vendor downloads and outcomes

`pipeline/vendor_sources.py` owns PFR advanced statistics, NGS tracking, snap
counts, FTN charting, injuries, depth charts, QBR, draft/combine data and the ID
map. Its catalog declares asset locations, first supported seasons, minimum
schema and replacement scope. Refresh tracking imports the same catalog, so the
watched files and downloaded files cannot drift independently.

The former PFR path called `import_pfr_advstats`, which is absent from the locked
`nfl_data_py` package; a broad handler hid the error. The adapter now reads the
published [nflverse PFR assets](https://github.com/nflverse/nflverse-data/releases/tag/pfr_advstats)
directly with pandas, as the other adapters do.

Each optional source reports a source/year outcome:

| Outcome | Storage and refresh behavior |
|---|---|
| `loaded` | Store validated rows; acknowledge the observed source version |
| `empty` | Retain stored rows; acknowledge a successfully examined version with no matching data |
| `not_found` | Retain stored rows and the old refresh stamp |
| `unsupported` | Skip years before the source's coverage; no download |
| `unsupported_format` | Retain stored depth charts when a historical file lacks daily timestamps |
| `failed` | Retain stored rows and the old stamp after a known remote outage; allow other optional feeds to continue |

A known optional outage is an HTTP failure, URL/network error, timeout or
connection failure. Invalid schema, parsing errors and unexpected programming
exceptions fail the refresh with their source and original cause. Database
writes run outside download exception handling. Unexpected upsert storage faults
propagate instead of creating a replacement table or continuing after a failed
delete. Static awards preparation also fails the pipeline on error; it is a
local preparation step, not an optional network download.

Bulk PFR/NGS/QBR files are read once and filtered to the exact requested seasons.
Seasonal assets are read separately so a missing year cannot erase its old data
or prevent a supported year from loading. Draft/combine data retain the existing
1980–2029 reference window even when an old season triggered the job. FTN's
column selection, join-ID conversion and float precision are preserved in the
pure `pipeline/normalization.py` helpers. Depth charts retain the latest daily
snapshot across fetched frames; older formats do not overwrite it.

`run_ingest` returns core and vendor outcomes, and logs show which source/year was
loaded, empty, unavailable or retained after failure. Refresh timestamps advance
only for observed `loaded`/`empty` vendor outcomes, allowing failed downloads to
be retried. A successful empty result records that this version was checked;
it does not claim that new rows were stored. This avoids rebuilding daily for a
valid bulk file that has not yet added the current season. Coverage limits are
also applied before upstream stamp lookups for unsupported years.

Core play/weekly stamps now require a corresponding observed loaded outcome,
even if upstream metadata advertises an asset. A schedules-only marker requires
actual downloaded schedule rows and no loaded plays. Thus a missing asset or
inconsistent upstream metadata cannot itself acknowledge a successful download.

## Calculations, normalization and storage

The orchestration entry point `ingest.py` now only runs pipeline phases and
retains the legacy CLI pending its replacement. The focused owners are:

| Module | Responsibility |
|---|---|
| `loading.py` | Source validation, replacement scope and coordination |
| `player_stats.py` | Official weekly offensive selection and player-game composition |
| `play_stats.py` | Play-derived offensive fallback, defensive slots and special teams |
| `normalization.py` | Frame merging, historical team mapping, FTN and depth cleanup |
| `storage.py` | Core seasonal upserts, reference replacement and player/weekly writes |
| `awards.py` | Static award preparation with its existing roster identity join |

These moves preserve the football calculations, SQL, row selection and scoring
weights. Seventeen moved functions match their previous syntax trees after
renaming, and player composition before storage is unchanged. The shared common-
column/TRY_CAST compatibility behavior in seasonal upserts also remains; a future
candidate's schema and coverage still need validation before publication.

Player-game storage now creates a table only when its initial existence query
finds a known missing table. Later delete, describe and insert faults propagate.
Previously a broad handler tried CREATE after any failure, masking an insertion
error with a misleading table-already-exists error. Static award writes have also
moved out of ingestion; startup still calls that same preparation function until
the serving-write migration is complete.

Seasonal upserts now use the same exact-target missing-table classification as
player-game storage. A first download can create a new PFR/QBR table even if the
optional-read fallback registry does not list it. A missing dependency inside an
existing view, or a later storage failure, remains an error; it cannot trigger
table creation or broaden what read queries may silently treat as unavailable.

### Passing EPA correction found by the real candidate

The full weekly migration exposed a definition difference that the old 2023-only
legacy-feed test did not reveal. The modern provider sums `qb_epa` for play types
`pass` and `qb_spike`; our split base used `pass_attempt OR sack`, including some
penalty-nullified `no_play` rows. A fresh 1999 source comparison had 19 qualifying
QB mismatches with the old EPA selection and zero with the provider's selection, at the
same 0.005-per-attempt tolerance. See the provider's
[calculate_stats implementation](https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R).

`splits_core.PASSING_EPA_PLAY` now filters the split EPA numerator and
the modern feed's no-down reconciliation adjustment. Counting stats retain their
broader flag-based base: historical valid attempts can have NULL play_type, so
filtering the entire base would incorrectly drop those attempts. Sacks remain in
the passing EPA numerator; their rows do not become pass attempts. This is an intentional
metric correction, unlike the earlier structural moves. A weekly history
migration rebuilds historical player-game totals and splits before validation,
so leaders/profiles cannot retain old EPA beside newly loaded official values.

### First real candidate: still rejected

The October 14, 2026 local trial refreshed 2025/2026, migrated official weekly
history for 1999–2026, and rebuilt its historical dependents. The full candidate
still fails the unchanged gate: `targets[2001]` has three one-target differences.
The failed candidate was removed. The original 616 MB source file retained its
exact SHA256 across every attempt; nothing was published or uploaded.

Fresh 2001 play-by-play reproduces those differences. The provider's underlying
`play_stats_2001.rds` has no target credit (`stat_id=115`) for three plays whose
play-by-play rows contain a completed pass and receiver: Wycheck in MIA–TEN,
Smith in DEN–OAK, and Gadsden in MIA–BUF. The current weekly feed follows those
credits. This is a source-attribution disagreement, not grounds to subtract one
from arbitrary player totals or raise a global tolerance.

A separate read-only audit compared the existing split counts with fresh weekly
data for 1999–2025 (162 metric/year comparisons). It also found differences in
2004 passing and 2024 targets, and receiving-yardage differences beyond the old
2023-derived six-player bound in multiple years. Except the independently
refetched 1999/2001 samples, that audit used stored historical plays/splits; those
other cases still need investigation before assigning causes.

The subsequent eligibility correction makes counting/yardage comparisons use
the split builder's existing admission rules. In a read-only comparison of
stored splits against cached fresh weekly feeds, 2006 receiving-yardage
mismatches fall from 17 to 5; 2004 falls from 12 to 4. The three 2024 target
differences and twelve receiving-yardage differences remain. These are scoped
diagnostics, not a passing full candidate. The correction changes no football
calculations, admission thresholds, reconciliation cutoffs or tolerances.
Regression checks cover below-minimum players with high official volumes,
incorrect/absent eligible output, and season/conversion exclusions.

An [isolated receiving-credit pilot](../api/experiments/README.md) now exercises
twelve real play fixtures and cached full-season data for 2001, 2004, 2006 and
2024. Receiving yards, catches and TDs match the provider's player/game and
player/season summaries; down/quarter totals are preserved. This is evidence
for the proposed attribution model, not a production builder change or an
accepted full-history candidate. Observed target credits also reproduce the
provider's incomplete historical totals; they cannot establish target coverage.
Source/storage integration, target policy, other situational metrics and full
candidate validation remain outstanding. The RDS reader used for research was an isolated,
temporary `uv --with pyreadr` environment; no application dependency or lockfile
was added. Logs, detailed audit JSON and diagnostic data remain ignored locally
under `api/data/`, rather than being committed as production data.

The legacy refresh records outcomes in return values and job logs. Candidate
preparation also persists them in a `snapshot_preparation` table, with requested
seasons, preparation time and record format version. It describes this run's
downloads, including optional failures and retained data; it is not a full
historical source inventory or a release certificate. Storage updates remain
in-place within whichever working file the process owns.

## Candidate preparation

From `api`, with the source database closed:

```sh
uv run --locked python -m jobs.prepare --source data/nfl.duckdb --candidate data/candidate.duckdb --seasons 2026
```

The source must already exist; bootstrap from an empty database is outside this
checkpoint. Both paths and seasons are explicit so there is no default serving
database target. Existing candidate files are refused rather than overwritten.

1. Open the source read-only and copy it into a newly created file, preserving
   other seasons. DuckDB's file lock excludes another writer process during the
   copy. Refuse a source with a pending write-ahead log (`.wal`): committed writes
   in that companion file might not yet be included in the main database file.
2. Start a separate Python process with `NFL_DB_PATH` set to the candidate before
   importing ingestion, configuration or builders. Their shared connection and
   existing locks therefore target the candidate throughout preparation.
3. Run existing source loading, player statistics and analytics preparation.
   Record source outcomes only after that sequence returns. Checkpoint the
   database (merge committed writes into the main file) and close the connection
   on success or failure.
4. Reopen the candidate read-only and check the preparation record and core
   per-season counts against downloaded counts. Played seasons require schedules,
   plays, rosters, official weekly rows and prepared player-game rows. A genuinely
   unplayed season can contain schedules without plays; an existing played season
   cannot be relabeled unplayed after its upstream asset disappears.
5. Run the analytics/statistical/API gate in another process with writes blocked
   (see below). Keep a successful candidate for publication. On a copy, build or check
   failure, remove only this run's candidate and its WAL, after its worker exits.
   The source is never replaced by this command.

Candidate finalization also prepares static awards for a schedules-only refresh
and strictly ensures applicable lookup indexes. Failure stops the candidate
instead of relying on startup to repair those serving prerequisites.

Preparation never promotes a candidate, uploads data, advances refresh watermarks
or changes the running site's database. The scheduled workflow, runtime ingestion
and startup/lazy writes are unchanged until the publication/serving migration.

## Read-only candidate validation

The preparation command runs this gate automatically after core source checks.
An existing closed database can also be inspected without refreshing it:

```sh
uv run --locked python -m jobs.validate --database data/candidate.duckdb
```

The command sets `NFL_DB_PATH` and `NFL_DB_READ_ONLY=1` before app/config imports.
DuckDB enforces the write prohibition for the shared connection and its cursors;
a request attempting lazy materialization fails validation. Normal serving still
defaults to writable during this migration.

- Schema and key checks use the analytics builders' existing DDL in a scratch
  in-memory database as the contract. Candidate tables must have those column
  types and unique, non-null lookup keys; validation never creates missing ones.
- Every loaded regular season must have schedules, rosters, official weekly
  stats, player-game stats, team analytics/rankings/splits, ratings and O-line
  grades. Qualifying offensive/defensive players require split output. Below-
  threshold player splits and career comparable pools may legitimately be empty.
  Those allowances and per-table season counts appear in the JSON report.
  Offensive eligibility shares the builder's `qualification_ctes` directly,
  including its two-point conversion exclusion; table presence alone cannot hide
  an individual qualifying player missing from the output.
- Lookup indexes and a nonempty awards seed must already exist. Ratings/grades
  must stay finite and within 3–10; split rates must be finite and within bounds.
- Receiving production has its own exact preservation check: prepared
  `player_game_stats` catches, receiving yards and receiving TDs must match
  `weekly_player_stats` for every identified player/regular-season week. It has
  no target requirement, split admission or volume cutoff. Missing low-volume
  players, altered/extra production, nonfinite totals and moving production to
  another week fail. Weekly keys support source schemas without `game_id`;
  prepared rows are REG-filtered through schedules. This checks preservation
  of source totals, not independent source correctness or historical target
  completeness. Missing targets must not cause otherwise usable production to
  be dropped. Frontend receiving views now retain recorded production without
  requiring targets (see [frontend data boundaries](FRONTEND_DATA.md#receiving-production-and-visibility)).
  Read-time coverage policy now masks known 2003–08 target gaps as unavailable
  in serving responses, with corresponding UI rate/aggregation handling. This
  does not repair stored source attribution, model calibration or split admission;
  the preservation gate continues to compare the unchanged source counts.
- The accuracy gate runs shared reconciliation functions for **every loaded
  regular season**, rather than the old deploy test's fixed 2023 alone. Counting
  stats and passing yards are exact at the established qualifying volumes;
  rushing/receiving yardage retain the existing limits of two/six differing
  players per season. Passing EPA includes the modern feed's no-down adjustment.
  Offensive counting/yardage comparisons also require the builder's source-play
  admission rules: high official yardage alone does not imply eligibility for
  splits. Eligible players are selected from plays before a left join to output,
  so missing qualified output still fails; the separate coverage check requires
  output even below the reconciliation volume cutoffs. No volume cutoff or
  yardage tolerance was increased. Missing qualified QBs/defenders cannot
  disappear through inner joins. Players outside these admission/volume checks
  are not a claim of exhaustive per-player reconciliation.
- ASGI HTTP checks exercise actual routes, services and response models for the
  oldest/newest played seasons: schedules, standings, leaders, power rankings,
  team analytics, a covered game's ratings, a team split request and a player
  split request when an admitted player exists. They require nonempty HTTP 200
  responses. Lifespan is deliberately excluded because it still writes. These
  are representative requests, not exhaustive endpoint or UI validation; live
  providers and billed model calls are excluded.

The legacy deploy reconciliation tests call the same statistical functions,
retaining their current 2023 fixture until the workflow adopts this gate.
Optional-source freshness and individual page coverage still depend on recorded
source outcomes, and the gate does not invent missing optional data. A copied
snapshot with an old season's required stats missing fails even if the requested
new season refreshed successfully. Refresh all missing years into a candidate
before attempting publication.

## Official receiving split adapter

`pipeline/receiving_splits.py` is the offline integration boundary for official
nflfastR receiving counts. It reads a completed, versioned Down export from
`experiments/upstream_receiving_splits.R` and returns the existing `player_splits`
column layout. The adapter has no R execution, network, database write or
request-time dependency. The main rebuild does not call it yet; the separate
preview job below now connects the producer and adapter.

The caller must supply qualified player IDs using the existing admission policy.
The adapter never re-qualifies players using raw upstream target counts: doing
that would drop historical receivers whose target source is incomplete. It maps
targets/receptions/yards/TD to `att`/`cmp`/`yards`/`td`, and official YAC/receiving
first downs to `yac`/`first_downs`. It masks targets in the known 2003–08 gap
through the shared coverage policy, and preserves production.
This is not a claim of complete target coverage in every other season.

All source rows are checked before admission filtering: required fields, season,
REG scope, down values, duplicate keys, finite integral counts, nonnegative
target/catch/TD/first-down counts and SQL integer range. Receiving first downs
cannot exceed catches. Negative receiving yards, negative YAC, YAC greater than
receiving yards and TD credits without catches/targets remain valid. Unidentified players and wholly
zero receiving lines are excluded. Partial exports, unexpected package versions
and scope/schema changes fail rather than silently falling back to old math.

YAC has an independent coverage policy: `yac_unavailable` masks pre-2006 values
only in this preview. It does not reuse the target-gap mask: 2006–08 YAC remains
usable after reconciliation while targets stay NULL. This helper does not
change serving responses. First downs follow upstream's receiving definition,
excluding first downs supplied by penalties; this is distinct from generic
play first downs. First-down counts remain available without targets, while a
first-downs-per-target rate still requires a supported target denominator.

`pipeline/receiving_target_metrics.py` adds target-role EPA/tgt (four decimals) and
Success% (one decimal) in the v4 preview. Success means EPA > 0; the official
calculator does not supply this rate. The adapter reads the hash-bound PBP
context, excludes conversions, and requires original-receiver completed,
incomplete or intercepted target-play counts to equal target credits. Every
target must have EPA. EPA/tgt additionally requires the official EPA sum to
match that target population. Missing coverage, the 2003–08 target gap and
zero-target lateral-only buckets produce NULL rates, preserving other fields.
EPA describes the original target role, not individual lateral attribution.

Version 5 also maps official receiving air yards after independently checking
per-target air-yard completeness, matching target counts and the summed air-yard
numerator. Air yards includes incompletions and can be negative. Missing air
yards masks only that field; missing EPA does not erase usable air yards.
Pre-2006 air records and the 2003–08 target gap make receiving air yards
unavailable before 2009 in this preview. Later years still require bucket checks.
A verified zero-target lateral-only bucket has zero target air yards and NULL
target-based rates. The existing serving mask is unchanged.

Category-inapplicable interceptions and CPOE remain NULL. These partial rows must
not replace complete live rows. The v5 manifest requires receiving EPA/air yards
and target context, and records the R environment and SHA256 digests of
exports/source snapshots. Loaders parse the exact bytes they verified, using one
captured manifest in the preview worker. This detects changed exports; it does
not authenticate the publisher or independently establish source correctness.
See the [actual R trial and adapter results](../api/experiments/UPSTREAM_SPLITS.md).

## Receiving candidate preview

From `api/`, `python -m jobs.receiving_preview` provides one explicit path through
copy, official R export, conversion, scoped reconciliation and metadata storage.
It requires an installed Rscript and separate R library. For the local trial:

```powershell
uv run --locked python -m jobs.receiving_preview `
  --source data/nfl.duckdb --candidate data/receiving-preview-example.duckdb `
  --exports data/receiving-preview-example-exports --seasons 2004 2024 `
  --rscript data/upstream-r-trial/R-4.6.1/bin/Rscript.exe `
  --r-library data/upstream-r-trial/library
```

Source must be closed with no WAL; candidate and export paths must be new. The
job reuses the existing snapshot copy and worker path binding. R runs with a new
invocation ID and writes its completion marker last. Its log and exports remain
available on failure; only the job's newly created candidate/WAL are removed.
Interrupting R stops its process tree before cleanup. The worker refuses the
source/default serving database, verifies the copied baseline and invocation,
checks runtime records, and loads hash-verified Down, context and weekly CSV bytes.

The candidate contains `receiving_down_preview` and one JSON record in
`receiving_preview_preparation`. That record binds the copied source hash,
export manifest hash, invocation ID, observed R/package versions and per-season
checks. Every existing qualifying player must remain, and catches/yards/TD must
match the exported weekly reference by player; modern targets are checked too.
Known-gap targets and unsupported pre-2006 YAC must be NULL. Receiving first
downs match weekly totals, as does YAC when supported. The report records
available and unavailable rate-row counts. Weekly EPA includes conversions;
the preview's EPA does not, so these numerators cannot be compared directly.
It also records available/unavailable air-yard rows and how many players have
complete air-yard splits reconciled to weekly totals. A player's partial sum
is never reported as a complete weekly match.
Qualification still uses the copied stored PBP;
this preview is not a coordinated refresh of every source or dimension.

Original `player_splits` rows remain intact. The main snapshot validator rejects
either preview table: a receiving preview is not an accepted publication
candidate. `jobs.prepare`, serving, refresh/deploy workflows and snapshot
promotion are unchanged. Full R dependency locking, coordinated source refresh,
remaining dimensions/metrics and full-history reconciliation remain outstanding.

## Remaining serving writes

The app is not read-only yet. These paths must be retired together with verified
replacement preparation:

| Serving path | Current behavior |
|---|---|
| Startup in `main.py` | Creates lookup indexes and seeds missing player awards |
| Builder `read_or_materialize` functions | May rebuild missing analytics during page or assistant requests |
| Admin season load endpoint | Enqueues ingestion in a background thread |
| `database.get_connection` | Opens a writable DuckDB connection |

The current refresh workflow already runs ingestion outside the serving app.
However, the local `ingest` CLI still tries HTTP ingestion before falling back
to direct writes, and a separate splits maintenance script remains. These are
legacy entry points to consolidate into the offline command, not examples of
the intended final architecture.

## Next migration checkpoints

1. Resolve the real candidate's historical target/yardage credit disagreements;
   compare canonical per-play credits and fresh PBP before changing attribution.
   Rebuild and pass the unchanged gate before accepting a candidate.
2. Consolidate legacy entry points into the candidate command and persist/bind
   the validation report and source revision to the artifact being published.
3. Replace request-time materialization with reads, remove startup writes and
   retire the runtime ingestion queue/load/progress endpoints. Open serving
   connections read-only and check that requests cannot write.
4. Update refresh and deployment together so only validated candidates are
   published. Record the source coverage and snapshot revision being shipped.

Live scores remain a separate provider with their existing freshness behavior.
Assistant model execution and streaming are a later milestone.

## Verification

From `api`, run:

```sh
uv run --locked pytest tests/test_pipeline_analytics.py tests/test_refresh_watermarks.py tests/test_ratings_power.py
uv run --locked pytest tests/test_pipeline_sources.py tests/test_weekly_columns.py
uv run --locked pytest tests/test_vendor_sources.py tests/test_refresh_watermarks.py
uv run --locked pytest tests/test_context_sources.py tests/test_pipeline_storage.py
uv run --locked pytest tests/test_candidate_snapshots.py
uv run --locked pytest tests/test_snapshot_validation.py tests/test_reconciliation.py
uv run --locked pytest tests/test_receiving_credit_pilot.py
uv run --locked pytest tests/test_upstream_receiving_splits.py
uv run --locked pytest tests/test_receiving_preview.py
uv run --locked pytest tests/test_receiving_preservation.py tests/test_pipeline_storage.py
```

The new checks cover seasonal scope, one global rebuild per batch, ordering,
reported row counts, stopping on unexpected failure, and the no-play-by-play
short circuit. Existing checks exercise actual ratings/rankings mathematics and
upstream-change detection. Source checks include a real local parquet comparison
against the installed provider, strict error classification, per-season schema
validation, preserved stored history, required-feed failure, played/unplayed
coverage, mixed-season scope and unchanged watermarks after failure. No network
refresh or publication is needed for them. Vendor checks cover every catalog
adapter, expected outages versus unexpected faults, coverage/season filtering,
real snap storage preservation, FTN parquet parity with the installed provider,
depth snapshot selection, reference-history scope, storage/seed failures and
outcome-driven refresh stamps.
Context/storage checks use local CSV/parquet fixtures and in-memory DuckDB to
cover provider parity, required source coverage, table creation and scoped
replacement, original write errors, core refresh evidence, and actual official
offensive/special-team player composition while retaining another season.
Candidate checks use real temporary DuckDB files and worker processes with
synthetic ingestion (no downloads). They verify source bytes and older seasons
are preserved, coverage records survive connection closure, partial writes and
failed row-count validation remove the candidate, existing paths remain intact,
pending WALs are refused, inherited database overrides cannot redirect workers,
and interrupted workers stop before cleanup. They establish lifecycle safety;
they do not evaluate a full real-data candidate or certify publication.
Validation checks additionally build a small real historical/newest snapshot,
launch the actual read-only validation CLI, exercise HTTP responses, verify its
file bytes/WAL are unchanged, and reject deliberately broken schemas, keys,
coverage, indexes, rating ranges, counts, EPA and attempted lazy writes. The
existing local snapshot is also inspectable read-only; it currently fails the
new coverage gate because official weekly stats stop in 2024 while plays reach
2026. No automatic repair or live-site change follows from this inspection.

An October 15 isolated run used the actual player-game composition/storage
code with cached current weekly feeds and stored PBP for all six target-gap
seasons (2003–2008). All three receiving preservation checks passed for every
player/week in each season, including zero-target production rows; composing
later seasons retained earlier years. Only an in-memory database was written.
This scoped source-preservation result does not establish that a complete
candidate passes validation or that historical targets are usable.
