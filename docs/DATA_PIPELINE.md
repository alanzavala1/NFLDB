# Offline data preparation

The serving app reads a DuckDB database file containing source data and prepared
analytics. A **snapshot** means that complete file at a particular revision.
The goal is to build and verify a candidate snapshot offline, then ship it with
the app. Visitors should only read published data.

## Current preparation flow

```text
jobs.refresh → ingest.run_ingest
                    ├─ load source feeds
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

If no play-by-play is available, ingestion keeps its existing schedules/rosters
path and stops before player statistics, advanced/supplemental loading and
analytics preparation. Properly distinguishing an unpublished feed from a
network failure is part of the remaining source-adapter work.

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

1. Separate feed fetching, normalization and orchestration. Report required
   source failures separately from expected optional gaps or unpublished data.
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
```

The new checks cover seasonal scope, one global rebuild per batch, ordering,
reported row counts, stopping on unexpected failure, and the no-play-by-play
short circuit. Existing checks exercise actual ratings/rankings mathematics and
upstream-change detection. No network refresh or publication is needed for them.
