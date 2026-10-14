# Backend data ownership

Standings is the first endpoint moved into a shared service. This establishes a
small pattern for the remaining backend work; other assistant tools still import
route functions and will move one domain at a time.

## Standings

The HTTP route and assistant call the same data function:

```text
Browser → GET /api/standings → route ───────────────┐
                                                  ↓
                                    services/standings.py → DuckDB
                                                  ↑
Ask → get_standings / get_team_overview tool ──────┘
```

`api/routers/leaders.py` owns the URL and FastAPI query parameter. FastAPI parses
the supplied season and rejects invalid values. The route calls the service and
uses `DivisionStandings` to validate and serialize its response.

`api/services/standings.py` owns `get_standings(season=None)`, an ordinary Python
function without HTTP parameter objects or route decorators. An omitted season
uses the existing configured current season. It reads schedule rows through
`database.query_to_dict` and builds wins, losses, ties, points, home/away/division
records, streaks and games behind. It returns ordinary dictionaries.

`api/llm.py` imports this service directly. The standings tool selects a compact
set of fields for the model and records its result as provenance. The team
overview tool uses the same standings record alongside its profile information.
The assistant does not need to make an HTTP request to its own server.

The calculation is preserved: only regular-season games with both scores count
toward records and points. Teams with unplayed regular-season fixtures remain
visible with zero records. All eight divisions are returned, including empty
ones. Teams are sorted by winning percentage and then point differential; this
is the existing display ordering, rather than the full NFL playoff tiebreaker
procedure. Explicit seasons without games are not replaced by another year.
Unexpected database errors propagate instead of becoming successful empty data.

## Verification

From `api`, run `uv run --locked pytest tests/test_standings_service.py
tests/test_invariants.py` for the focused checks, or `uv run --locked pytest` for
the full backend suite. The new checks cover matching HTTP/service/tool data,
tool provenance, default and invalid seasons, team-overview reuse, unfinished
games, playoff exclusion and query failures. They use controlled databases and
call tool functions without invoking a model.

The extraction also compared the complete OpenAPI document before and after,
and compared the calculation's Python syntax tree. Both were unchanged. No
frontend types needed regeneration. Data rebuilding, database write ownership,
other domains and assistant execution remain separate milestones.
