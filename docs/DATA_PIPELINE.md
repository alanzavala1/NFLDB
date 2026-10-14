# Offline data preparation

The serving app reads a DuckDB database file containing source data and prepared
analytics. A **snapshot** means that complete file at a particular revision.
The goal is to build and verify a candidate snapshot offline, then ship it with
the app. Visitors should only read published data.

## Current preparation flow

```text
jobs.refresh → ingest.run_ingest
                    ├─ pipeline.sources downloads core seasonal feeds
                    ├─ ingest stores retrieved source data
                    ├─ build player_game_stats
                    ├─ load advanced and supplemental feeds
                    └─ pipeline.analytics.prepare_analytics
                           ├─ seasonal analytics
                           ├─ globally calibrated analytics
                           └─ persisted lookup indexes
```

`api/pipeline/analytics.py` owns the analytics preparation order. It calls the
existing builders; their SQL, formulas, missing-schema policies and locks are
unchanged. It does not download feeds. Source loading and player-game statistics
must be prepared before calling it. Unexpected builder failures propagate and
stop later steps; a known missing-schema fallback is still owned by each builder.
Completing this sequence alone does not establish snapshot completeness.

| Prepared data | Rebuild scope |
|---|---|
| Team season analytics | Each selected season |
| Weekly power rankings | Each selected season |
| Player game ratings | All loaded seasons, one global calibration |
| Offensive-line unit grades | All loaded seasons, one global calibration |
| Offensive player splits | Each selected season |
| Defensive player splits | Each selected season |
| Team offense/defense splits | Each selected season |
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
`ingest.py` still owns storage; optional vendors have separate adapters below.

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
preserving unavailable seasons' stored data. Failed required-feed downloads stop
the refresh before its upstream watermarks advance.

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

`run_ingest` returns the vendor outcomes, and logs show which source/year was
loaded, empty, unavailable or retained after failure. Refresh timestamps advance
only for observed `loaded`/`empty` vendor outcomes, allowing failed downloads to
be retried. A successful empty result records that this version was checked;
it does not claim that new rows were stored. This avoids rebuilding daily for a
valid bulk file that has not yet added the current season. Coverage limits are
also applied before upstream stamp lookups for unsupported years.

Outcomes currently exist in return values and job logs. A durable coverage
manifest belongs to candidate snapshot construction. Storage updates are not yet
a snapshot transaction: a later failure can leave an in-place working database
partially updated. A separate validated candidate file remains necessary before
publication can be treated as atomic.

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

1. Complete storage/player-stat normalization boundaries and the remaining
   schedule/roster adapter ownership; vendor download outcomes are now explicit.
2. Provide one offline command for source refresh, analytics rebuild and
   validation. Build a separate candidate file so a failed run leaves the
   published snapshot intact.
3. Prepare awards, indexes and every formerly lazy analytics table in that
   candidate. Validate historical and newest-season coverage, statistics and
   representative requests. Report allowed empty datasets explicitly.
4. Replace request-time materialization with reads, remove startup writes and
   retire the runtime ingestion queue/load/progress endpoints. Open serving
   connections read-only and check that requests cannot write.
5. Update refresh and deployment together so only validated candidates are
   published. Record the source coverage and snapshot revision being shipped.

Live scores remain a separate provider with their existing freshness behavior.
Assistant model execution and streaming are a later milestone.

## Verification

From `api`, run:

```sh
uv run --locked pytest tests/test_pipeline_analytics.py tests/test_refresh_watermarks.py tests/test_ratings_power.py
uv run --locked pytest tests/test_pipeline_sources.py tests/test_weekly_columns.py
uv run --locked pytest tests/test_vendor_sources.py tests/test_refresh_watermarks.py
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
