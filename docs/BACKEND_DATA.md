# Backend data ownership

Standings, search, league leaders and WPA leaders use services. This establishes
a small pattern for the remaining backend work; other assistant tools still
import route functions and will move one domain at a time.

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

## Search

`api/routers/leaders.py` retains `/api/search`, its required `q` parameter with
minimum length one, and the `SearchResult` response schema. It delegates to
`api/services/search.py`. The assistant's `resolve_entity` tool imports that
same service directly, and selects candidate IDs, names, types, positions and
teams for the model. Its arguments, result recording and no-match message are
unchanged.

The service trims input, normalizes case and punctuation, and resolves the
existing conservative nickname aliases such as CMC and Niners. Empty or
punctuation-only normalized input returns no matches without querying rosters.
Team matching uses the shared team names. Player matching selects the newest
season row per player ID, then ranks exact names ahead of prefixes, initial/last
name matches, substrings and compact spellings. Teams appear first; limits
remain three team candidates, eight player candidates and ten combined results.
Selection among roster rows tied on the newest season remains unchanged.

The existing roster query uses `safe_query`: any query failure is logged and
produces an empty player list, while team matches can still be returned. That
fallback was preserved during this structural move. Distinguishing expected
data gaps from unexpected failures remains a later error-handling task; search
does not yet have standings' error propagation behavior.

## League leaders

The `/api/leaders` route delegates to `api/services/leaders.py`. The route keeps
its optional season parameter and `LeagueLeader` response validation. The
assistant's `get_leaders` tool imports the same service directly; `llm.py` no
longer imports any functions from `routers/leaders.py`.

The service returns season totals from `player_game_stats` for games joined to
regular-season schedules. It counts distinct game IDs and sums the existing
passing, rushing, receiving, defensive, kicking and punting fields. The shared
`ROSTER_CTE` chooses one roster row per player and season by latest week, then
team, so the join does not multiply totals. Its left join keeps players without
roster details, returning null position, team and headshot. An omitted season
uses the existing current-season configuration; an explicit empty year stays
empty. Unexpected query failures propagate.

The service provides totals without choosing a ranking or qualification rule.
The UI owns its tab-specific qualification and display choices. The assistant
validates its stat name, sorts that stat descending, limits the result to between
one and 25 rows, and records its existing compact result. These caller policies
are preserved alongside the unchanged shared SQL. WPA leaders remain a separate
query based on play-level data.

## WPA leaders

The `/api/wpa-leaders` route now delegates to `api/services/wpa_leaders.py`.
It retains the optional season parameter and `WpaLeaders` response validation.
There is no assistant consumer for this endpoint; the extraction adds no tool.

The service keeps three separate regular-season play queries:

| List | Summed field | Qualification |
|---|---|---|
| Passing | `air_wpa` | At least 50 pass attempts |
| Rushing | `wpa` | At least 50 carries |
| Receiving | `yac_wpa` | At least 20 completed-pass receptions |

Each query excludes missing player IDs, treats null WPA contributions as zero,
rounds the sum to three decimals, counts distinct games and sorts descending
before limiting results to 30. The same-season roster join uses `ROSTER_CTE`
and preserves missing roster details. The HTTP schema still fills unused volume
fields with null: a passing row has attempts plus null carries/receptions.

Each category retains its existing `safe_query` fallback. A failed passing
query returns an empty passing list while successful rushing/receiving lists
remain available. Missing play data can produce three empty lists; failures are
logged and still return HTTP success. Distinguishing such failures from valid
empty results remains an explicit follow-up, as with search.

With this extraction, `api/routers/leaders.py` contains only four HTTP wrappers;
SQL and football-data assembly live in the services.

## Verification

From `api`, run `uv run --locked pytest tests/test_standings_service.py
tests/test_invariants.py` for the focused checks, or `uv run --locked pytest` for
the full backend suite. The standings checks cover matching HTTP/service/tool data,
tool provenance, default and invalid seasons, team-overview reuse, unfinished
games, playoff exclusion and query failures. They use controlled databases and
call tool functions without invoking a model. Search's focused checks are
`uv run --locked pytest tests/test_search_service.py tests/test_ask_vocabulary.py
tests/test_endpoints.py`; they cover service/HTTP/tool parity, normalized names
and aliases, ranking, newest roster rows, result caps, empty inputs, parameter
validation and the retained logged fallback. Existing vocabulary checks also
exercise search against the local database when that snapshot is present.

League leaders' focused checks are `uv run --locked pytest
tests/test_leaders_service.py tests/test_endpoints.py tests/test_reconciliation.py`.
They cover service/HTTP parity, expected totals, season/game-type filtering,
distinct game counting, duplicate/missing roster rows, deterministic roster
selection, assistant ranking/limits/provenance, default/empty/invalid inputs and
query failures. Reconciliation uses the local snapshot when available and does
not establish current production freshness.

WPA's focused checks are `uv run --locked pytest tests/test_wpa_leaders_service.py
tests/test_endpoints.py`. Isolated play/roster fixtures check metric selection,
rounding and null handling, inclusive thresholds, season/game-type filtering,
incomplete-pass exclusion, roster joins, all three 30-player caps, HTTP volume
fields, season defaults/validation and both whole/partial query fallbacks.

These extractions compared the complete OpenAPI document before and after,
and compared the moved logic's Python syntax tree. These were unchanged. No
frontend types needed regeneration. Data rebuilding, database write ownership,
other domains and assistant execution remain separate milestones.
