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

The [receiving migration checklist](RECEIVING_MIGRATION.md) inventories all 17
existing views, all 17 implemented previews, remaining data requirements and
the coverage/UI/full-build conditions for integration. Partial-context validation
now runs in the preview producer/worker, using hash-bound membership and official
classified/excluded references. The remaining views use this shared contract.

`pipeline/receiving_splits.py` is the offline integration boundary for official
nflfastR receiving counts. It reads completed, versioned per-dimension exports from
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
REG scope, dimension/bucket values, duplicate keys, finite integral counts, nonnegative
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
not replace complete live rows. The v14 manifest requires receiving EPA/air yards,
target context, per-dimension membership and classified/excluded references,
and records the R environment and SHA256 digests of
exports/source snapshots. Loaders parse the exact bytes they verified, using one
captured manifest in the preview worker. This detects changed exports; it does
not authenticate the publisher or independently establish source correctness.
See the [actual R trial and adapter results](../api/experiments/UPSTREAM_SPLITS.md).

All 17 views use `adapt_receiving_splits` and
`load_receiving_split_export` with an explicit dimension. The supported labels
live in `pipeline/receiving_dimensions.py`: downs 1–4, quarters 1–4 and OT,
designated `home`/`away` sides, `shotgun`/`under_center` formation labels,
the three field zones, `leading`/`tied`/`trailing` game-script labels and
`huddle`/`no_huddle` tempo labels.
Every period above four groups into OT, matching `splits_core.QUARTER_DIM`.
Missing periods remain unknown. Quarter target populations do not require a
known down; a usable quarter play must not disappear because down is missing.
The producer filters each play context before invoking the official calculator,
retaining all credited recipients. Absent buckets do not get invented zero rows.

Home/away uses each play's `posteam_type`, matching the existing split labels
and sort order. It follows the game's designated home/away team, including
neutral-site games; it does not use stadium geography or a player's latest
season team. Missing sides stay unknown and unexpected nonmissing labels fail
instead of defaulting to away. Home/away target metrics do not require down or
quarter fields. The export includes offensive/home/away team IDs and location
for independent checks of designations and neutral-site inputs.

Shotgun uses the provider's binary `shotgun` flag: 1 maps to `shotgun`, 0 to
`under_center`, with the existing label order. Missing flags remain unknown;
nonmissing values outside 0/1 fail. This preview does not inherit the legacy
SQL's NULL-to-under-center fallback. It uses the recorded flag rather than a
new formation classifier. The same target/air completeness rules and historical
masks apply, without requiring another dimension's context fields. Export
filenames and the manifest's dimension list now derive from one R catalog.

Field position uses pre-play `yardline_100`, the distance to the opponent's goal
line. More than 50 is own territory, more than 20 through 50 is opponent territory,
and 20 or less is red zone. Labels/order match `splits_core.FIELD_ZONE_DIM`.
Midfield therefore belongs to opponent territory and the opponent's 20 to red
zone. Every valid spot has exactly one label; the catch/end location does not
change it. Missing spots remain unknown, finite fractional spots are accepted,
and nonnumeric/nonfinite values or distances outside 0–100 fail. All credited
recipients, including lateral recipients, share the play's starting field zone.

Game script uses pre-play `score_differential`, the offense's score minus the
defense's score. Positive is `leading` (sort 1), zero is `tied` (2), negative is
`trailing` (3), matching `splits_core.game_script_dim`. A touchdown that changes
the lead remains under the state before that play. All credited recipients share
that context, including lateral recipients. Missing score is unclassified, never
tied or trailing; nonnumeric/nonfinite, fractional or out-of-storage-range values
fail. Classification does not require a known down, quarter or field position.
The existing classified/excluded references, eligibility and field-specific
target/YAC/air/rate policies apply unchanged.

Tempo uses the recorded `no_huddle` flag: 0 maps to `huddle` (sort 1), 1 to
`no_huddle` (2), matching `splits_core.NO_HUDDLE_DIM`. Unknown stays unclassified;
nonmissing values outside 0/1 fail. Shotgun and tempo share the same binary-flag
validation rule. This does not infer pace from elapsed clock time. All recipients
inherit their play's flag before official credit calculation; target-based
rates still describe the original target role. Classified/excluded conservation,
historical masks and independent air coverage apply without requiring another
dimension's context to be known.

## Receiving candidate preview

From `api/`, `python -m jobs.receiving_preview` provides one explicit path through
copy, official R export, conversion, scoped reconciliation and metadata storage.
It requires R 4.6.1 and a separate library restored from `api/r/renv.lock`.
See the [offline R setup](../api/r/README.md) for prerequisites, dependency checks
and the clean-library verification. From `api/`, for the local installation:

```powershell
$env:LC_ALL = 'C'
& data/upstream-r-trial/R-4.6.1/bin/Rscript.exe --vanilla `
  r/restore.R data/receiving-r-library
if ($LASTEXITCODE -ne 0) { throw 'R setup failed' }
uv run --locked python -m jobs.receiving_preview `
  --source data/nfl.duckdb --candidate data/receiving-preview-example.duckdb `
  --exports data/receiving-preview-example-exports --seasons 2004 2024 `
  --rscript data/upstream-r-trial/R-4.6.1/bin/Rscript.exe `
  --r-library data/receiving-r-library
```

Source must be closed with no WAL; candidate and export paths must be new. The
job reuses the existing snapshot copy and worker path binding. R runs with a new
invocation ID and writes its completion marker last. Its log and exports remain
available on failure; only the job's newly created candidate/WAL are removed.
Interrupting R stops its process tree before cleanup. The worker refuses the
source/default serving database, verifies the copied baseline and invocation,
checks runtime records, and loads hash-verified dimension, context, whole/weekly,
membership and classified/excluded CSV bytes.

The Python job freezes `producer.R`, `environment.R` and `renv.lock` into the new
export directory. Before downloading inputs it checks the exact R version,
all 49 locked package versions, recursive import coverage and compiled package
loading, excluding user/site libraries. R rechecks the environment during the
export. The manifest binds these files and records the verified package set;
the worker verifies the frozen bytes and runtime/lock agreement along with
shared definitions and charting inputs. Concurrent edits to the checkout cannot
alter the running producer or its dependency specification. Failures retain
`R-environment.log` or `R-job.log`. The restore path has been exercised on Windows
x64; Linux/macOS system dependencies and portability remain unverified.

The candidate contains `receiving_down_preview`, `receiving_quarter_preview`,
`receiving_home_away_preview`, `receiving_shotgun_preview`,
`receiving_field_zone_preview`, `receiving_game_script_preview`,
`receiving_no_huddle_preview` and one JSON record in
`receiving_preview_preparation`. Format version 4 records whole-season versus
weekly count checks under `whole_references[year]` and dimension checks under
`seasons[year][dimension]`, binding the copied source hash, export manifest hash,
invocation ID and observed R/package versions. `qualifications[year]` records
admitted IDs and their qualifying-play counts, the bound context revision and
the canonical eligibility SQL fingerprint.

`pipeline/receiving_preview_validation.py` verifies the official whole-season
counts against weekly data for qualified players, including supported targets,
YAC, first downs and observed air sums. Weekly player/week keys must be unique.
For each dimension it independently derives labels from context, checks the R
producer's exact game/play membership, and validates official bucket sums against
the official classified union. Classified plus excluded counts must equal the
whole official reference **for every player, before admission filtering**.
Unidentified credits remain in that comparison. These checks use the pure
`receiving_partition_validation.py` contract, not another credit calculator.

The producer assigns each play once and uses those same labels to select all
official calculations. It exports complete membership, including unknown labels,
and header-only references for empty populations. A classified reference may reuse
the full official result only when the selected play set is exactly the full set.
Each subset file is bound to the completion manifest and read from verified bytes.
Missing files/hashes, changed bytes, invalid counts, duplicate/join-multiplied keys
or failed conservation reject the preview and trigger the existing safe cleanup.

A dimension's `coverage` record describes all REG nonconversion play counts,
input revisions, exclusion reason and qualified classified/excluded/whole receiving
production. Missing context may occur on nonreceiving plays, so partial play
coverage does not by itself imply missing receiving production. Globally qualified
players may have no production in one classified view; their absence is reported
explicitly and does not remove them from other views or the whole reference.
A verified empty classified population produces no invented zero rows.

Adapted counts reconcile to the classified reference, with `matched_classified`
statuses. Known-gap targets and unsupported pre-2006 YAC stay NULL. The report
records available/unavailable rate and air-yard rows, and players whose complete
available air sums match the classified reference. Agreement between raw air sums
does not establish per-target completeness or unmask a missing metric. Weekly EPA
includes conversions; the preview's EPA does not, so these numerators cannot be
compared directly. Existing target-role rate and independent air gates remain.
Qualification now uses the same bound fresh PBP context as the official
calculations. `receiving_qualification.py` validates scope, unique game/play keys,
attempt flags and receiver IDs, then registers the context as `plays` in an
isolated in-memory DuckDB connection. It calls the existing
`splits_builder.qualification_ctes(..., minimal=True)`: at least 25 original-
receiver attempt plays in the REG season, excluding two-point attempts. Minimal
and normal modes share the source predicate, season filters and volume threshold;
the minimal mode avoids requiring metric/context columns unrelated to admission.
No official-target totals or optional charting fields decide eligibility. Copied
database `plays` cannot influence admission and remain unchanged. This aligns
receiving preview inputs; other candidate analytics still use the copied database
until the main fresh-source build is integrated.

October 23 verification rebuilt 2004 and 2024 with the locked R library and
fresh inputs. Independent R counts from captured full PBP snapshots matched
every admitted ID and qualifying-play count: 152 and 220 players respectively,
with no additions/removals versus the copied baseline in these samples. Every
one of the 34 season/view outputs matched the prior audited preview exactly;
all 157 bound input/export files verified. Source/canonical split rows stayed
unchanged and the full gate still rejected the preview. Boundary, duplicate,
historical/optional-context and stale/absent-copied-play tests passed; the full
backend suite passed 1,052 tests with 2 skips. Ignored evidence is under
`api/data/upstream-r-trial/`: `fresh-qualification-build.log`,
`audit_fresh_qualification.R`, `verify_fresh_qualification.py`,
`fresh-qualification-verification.json` and `fresh-qualification-backend.xml`.

Original `player_splits` rows remain intact. The main snapshot validator rejects
any `receiving_*_preview` table or preparation marker, including unknown future
preview dimensions: a receiving preview is not an accepted publication
candidate. `jobs.prepare`, serving, refresh/deploy workflows and snapshot
promotion are unchanged. Main-build coordinated source refresh, API/UI integration,
full-history reconciliation and verification on other build platforms remain
outstanding. The dependency lock does not freeze changing NFL feeds.

For a completed per-season preview, `experiments.receiving_history_audit` adds
independent captured-PBP/credit/rate checks and a completed-schedule game check.
It returns a nonzero completeness result for missing games while retaining the
verified available-game output. See the [history validation report](RECEIVING_HISTORY_VALIDATION.md)
for the 1999–2026 sweep, known upstream game gaps, commands and evidence.

### Complete preview context catalog

The remaining views now share the same calculation and acceptance flow:

- `game_state` uses recorded `wp`, with 0.05–0.95 inclusive competitive;
  otherwise garbage time. Nonmissing probability must be finite and within 0–1.
- `roof` maps dome/closed and outdoors/open explicitly. `surface` preserves
  exact grass versus reviewed non-grass aliases, including hybrids, with blank
  and unreviewed labels excluded. This is the existing grouping, not a new
  assertion about surface materials.
- `opponent` uses era-sensitive franchise aliases and NULL sort order;
  `opp_division` preserves current-franchise alignment, including old seasons.
  The latter is explicitly not historical division membership.
- `target_depth` and `target_direction` describe the original pass. Every
  credited recipient inherits that play context; a lateral route is not inferred.
- `pressure` keeps existing keys but means recorded QB hit, not every pressure
  or a clean-pocket detector. Coverage before 2006 is unavailable in the preview.
- `play_action` and `blitz` use FTN, supported from 2022. Blitz preserves the
  1–4 versus 5–11 pass-rusher rule, with missing/out-of-range counts excluded.

`receiving_context_rules.py` owns these definitions and classification policies.
The Python job writes a shared definitions JSON for R; the worker verifies it
against the current builder. Pure franchise constants live in `team_definitions.py`,
with compatible exports from `config.py`, so offline classifiers do not open
the database simply to read team aliases.

`receiving_inputs.py` uses the existing vendor-source owner to download and
normalize FTN inputs. Each season has a bound CSV and explicit source outcome/
URL. Expected missing/failed feeds become unavailable charting views; malformed
schemas, duplicate keys or invalid flags fail. R left-joins on season/game/play,
and Python independently verifies every joined value and matched/unmatched key
against the same input bytes. False play action is distinct from an uncharted
play. FTN metadata/revisions accompany those views' coverage records.

This completes view implementation in the isolated preview. It does not replace
the main snapshot build, source DB or live API/UI. All-history checks, integration
of the fresh receiving path and the existing release gates still apply. The R
dependency lock and same-input receiving qualification are implemented above.

## Remaining serving writes

The main-build receiving integration now supports reusing the
calculator's captured full plays/weekly inputs in `jobs.prepare --core-inputs`.
See [shared receiving inputs](RECEIVING_BUILD_INTEGRATION.md) for the frozen
conversion, revision records and current limits. This also selects official
receiving materialization and persists coverage/whole-reference records.
An additive read-only receiving API now returns prepared independent whole
totals, NULL reasons, player-specific exclusions and game coverage together.
The receiving UI now consumes that contract and preserves missing metrics through
season/career comparisons, with per-view exclusions and game-coverage notes.
Full release validation remains pending; the full gate
rejects the integration marker, and the existing preview rejection remains.
Separate captured runs can be assembled into one compatible historical input
collection with `jobs.receiving_core_inputs --bundles ... --output ...`.

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
