# Backend data services

FastAPI routes and assistant tools call shared Python services. Statistical
queries and response assembly belong in those services, rather than in HTTP
handlers or model prompts.

```text
HTTP route ──────┐
                ├→ domain service → read-only DuckDB
Assistant tool ─┘
```

## Responsibilities

| Layer | Owns |
|---|---|
| `routers/` | Request validation, response schemas, HTTP status codes and defaults |
| `services/` | Domain queries, entity joins, record selection and response assembly |
| Analytics builders | Offline calculations and read functions for prepared tables |
| `database.py` | Connection lifecycle, read-only mode and independent request cursors |
| `sql_helpers.py` | Shared roster/stat projections and optional-data queries |

Routes include schedules/games, players, teams, leaders, live scores and the
assistant. See [the data map](DATA_MAP.md) for their service and table owners.
Some prepared analytics are read directly through builder modules; their
materialization functions run only in the offline worker.

## Query rules

Player/roster joins select the appropriate record before aggregation so repeated
roster rows cannot multiply totals. Cross-provider player IDs use shared mappings
and documented fallbacks. Game and team queries retain season-sensitive franchise
codes. Standings and pregame records use completed results within the requested
season/week, with regular-season scope where specified.

Prepared passing and receiving responses include independent totals, classified
rows, aggregation ingredients and coverage. Missing preparation is not rebuilt
during a request. Receiving masks preserve supported catches, yards and touchdowns
when historical targets or other dependent fields are unavailable.

Assistant tools may select a ranking or compact a result, but they use the same
service definitions. They do not call the HTTP routes internally. Granular play
queries use approved filters in `services/play_queries.py`.

## Errors and verification

`data_errors.py` recognizes specific missing relations/columns. `safe_query`
returns an empty optional result only for recognized missing data; unexpected SQL
and storage failures propagate. Required missing data can become a readable 503.
Prepared passing/receiving readers reject malformed records rather than returning
invented values or attempting repair.

Service tests use small in-memory databases. Route tests check schemas and HTTP
behavior; source/reconciliation checks validate prepared statistics. From `api/`,
run `uv run --locked pytest`. Real-data checks need a prepared snapshot, and
model evaluations are separately opt-in.

See [read-only serving](READ_ONLY_SERVING.md) and [offline preparation](DATA_PIPELINE.md).
