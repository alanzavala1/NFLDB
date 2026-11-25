# Read-only serving

The API reads an existing DuckDB snapshot. It does not ingest seasons, create
indexes, seed reference data or prepare missing analytics.

`NFL_DB_READ_ONLY` defaults to read-only. The application rejects `0` during
import/startup; that value is reserved for the separate offline writer process.
Production also sets the variable explicitly to `1`.

HTTP routes and assistant tools call service/builder read functions. Missing
optional data can produce an empty result. Required missing relations return a
readable 503; unexpected query/storage errors propagate. Prepared records are
validated when read, not silently repaired.

The retired season load/progress endpoints return 410. There is no request-time
ingest queue.

## Preparing new data

Use the [offline release workflow](OFFLINE_RELEASES.md). It copies a closed source
into a new candidate, prepares analytics and indexes, then validates the result.
The source must have no pending WAL; candidate paths must be new.

Publication selects a versioned release. Deployment replaces the container and
its database together; it does not modify an open serving file. See
[refresh automation](NATIVE_REFRESH_AUTOMATION.md) and [deployment](../DEPLOY.md).

`tests/test_readonly_serving.py` covers read-only startup, missing data, rejected
writer mode and retired endpoints. Image checks also attempt a persistent write
and require DuckDB to reject it.
