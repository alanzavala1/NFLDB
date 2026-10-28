# Read-only serving and offline preparation

The web process reads an existing DuckDB snapshot. It does not create a missing
database, seed awards, create indexes, rebuild analytics or ingest seasons.
`NFL_DB_READ_ONLY` defaults to read-only, and the production image explicitly
sets it to `1`. The app rejects the offline writer setting `0` before config can
open a database and again during startup.

All eight former `read_or_materialize` entry points were removed. HTTP and
assistant consumers use the builders' existing `read` functions. A missing row
does not trigger a scan or rebuild. Optional/absent prepared analytics retain
their existing empty-result behavior. A missing relation needed by a required
join returns a readable 503, without exposing database details or trying to
repair the snapshot. Unknown SQL/storage errors still propagate.

The old HTTP load and progress URLs return 410, including with an admin token.
The background ingest queue was removed. The obsolete direct `ingest.py` CLI
now points callers to candidate preparation rather than routing through a web
server or editing the serving database.

## Offline writer boundary

Use the candidate command from `api/`:

```powershell
uv run --locked python -m jobs.prepare `
  --source data/published.duckdb `
  --candidate data/new-candidate.duckdb `
  --seasons 2026 `
  --core-inputs PATH_TO_CORE_COLLECTION `
  --passing-inputs PATH_TO_PASSING_COLLECTION
```

The source must be closed with no WAL. The command exclusively creates a new
candidate, runs its writable worker in a separate process, prepares analytics,
awards and indexes, closes/checkpoints it, then validates in a read-only process.
It never overwrites the source. Failure removes only the newly owned candidate.
Native passing/receiving preparation requires the matching captured inputs;
historical analytics must be rebuilt when their input revisions change.

`NFL_DB_READ_ONLY=0` belongs to that offline worker. The legacy scheduled refresh
step also opts into it explicitly, and its CLI refuses an implicit writable
connection. This preserves the older offline path while its publication flow
is migrated; it does not make that path ready to publish native snapshots.

## Current checkpoint

This completes the serving boundary. The official snapshot publication guard
remains unchanged. Remaining work is to connect native input capture/reuse,
candidate validation, publication and acknowledged watermarks in the scheduled
refresh/deployment flow. The existing workflow must not be described as migrated
or a native snapshot as published yet.

The existing 28-season summary candidate passed **111 HTTP reads** through real
app startup while all eight builders, index creation and awards preparation were
forbidden. DuckDB rejected an attempted write, its SHA256 stayed unchanged and
no WAL appeared. File-backed tests additionally cover missing databases, missing
prepared tables, retired admin URLs and rejecting writable app startup.
Evidence: ignored `api/data/readonly-serving-proof-20261028.{json,log}` and
`verify_readonly_serving_20261028.py`.

The full backend run checked 1,397 cases. Two tests still expected lazy ratings
creation; their fixtures now prepare ratings before HTTP, and both passed in the
60-case focused recheck. Together with the explicit writer-mode tests, the latest
results cover **1,396 passing cases, two skips and no unresolved failures**.
The original full-run XML and passing rechecks remain available separately in
`api/data/readonly-serving-{full,final-controls}-20261028.xml` and
`readonly-boundary-final-20261028.xml`; failures were not removed from that evidence.
Generated API types, frontend build and lint also passed.

No production database, environment configuration, publication guard or deployed
service was changed. The Docker/workflow updates are local code changes only.
