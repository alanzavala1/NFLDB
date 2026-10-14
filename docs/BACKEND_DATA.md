# Backend data ownership

Standings, search, league leaders, WPA leaders, power rankings and team depth
charts use services. This establishes a small pattern for the remaining backend
work; other assistant tools still import route functions and will move one
domain at a time.

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

## Power rankings

`api/routers/power_rankings.py` delegates to `api/services/power_rankings.py`.
The route retains its configured season default, optional week constrained to
1–22, and `PowerRankingRow` response model. The assistant imports the same
service directly. Its tool still uses week zero to mean the latest available
ranking; the HTTP endpoint uses an omitted week for that choice.

The existing builder owns EPA computation and stored weekly rankings. The
service calls it, then adds team records through the week returned by the
builder. These records count completed regular-season games only, including
ties, and exclude future weeks and other seasons. A team with no counted games
gets `0-0`. Rank, net EPA and movement come from the builder; nullable fields
remain nullable in the HTTP response. An empty builder result returns an empty
list without querying schedule records.

The assistant keeps its existing compact projection, omits null fields, caps
results at 25 and records provenance. Its tool definitions and execution are
unchanged. Existing DB-backed coverage now calls the service for comparison.

`power_rankings_builder.read_or_materialize` can still prepare missing rankings
on demand. Its locks, computation, persistence and existing empty/error behavior
are preserved. This extraction does not make serving read-only or change model
definitions; those are separate pipeline/error-handling tasks. Errors from the
service's schedule-record query continue to propagate.

## Team depth charts

The team depth-chart route delegates to `api/services/team_depth_chart.py`.
The route retains its path, optional integer season/week parameters, description
and `DepthChartEntry` response validation. The assistant's team-overview tool
imports the service directly and preserves its current-season starter projection.

The feed stores daily snapshots rather than weekly history. The query uses the
newest timestamp across the entire feed, then filters that snapshot to the
requested team. A team with only older rows stays empty; it does not silently
fall back to its own older chart. Omitting the season accepts the snapshot's
season without a calendar guess. Supplying a different season returns an empty
list. The accepted week argument remains ignored, including integers outside
the normal season-week range.

The existing shared `DEPTH_CHART_SEL` projects vendor columns into the public
shape. September–December dates use their calendar year; January–August dates
use the previous year. Week and jersey number stay null, and depth rank becomes
a string. Rows remain ordered offense, defense, special teams, then slot/rank.
The player-profile depth query continues to use that same projection; its
separate player selection is unchanged in this checkpoint.

The team-overview tool selects eligible offensive starters only for the current
season. Its arguments, five-starter cap, output and provenance are unchanged.
The query retains `safe_query`'s logged empty fallback for database failures;
distinguishing such failures from valid missing data remains a follow-up.

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

Power rankings' focused checks are `uv run --locked pytest
tests/test_power_rankings_service.py tests/test_ratings_power.py
tests/test_ask_coverage.py`. Controlled ranking snapshots and in-memory schedules
check selected-week records, ties/unfinished games, season/game-type filtering,
null fields, empty results, defaults, HTTP week validation, assistant projection
and provenance, and record-query failures. Existing builder tests still verify
ranking computation and movement; local snapshot checks remain separate from
production freshness and model-answer quality.

Team depth-chart checks are `uv run --locked pytest
tests/test_team_depth_chart_service.py tests/test_depth_charts.py`. They cover
service/HTTP parity, snapshot scope, ordering/projection, January and September
season boundaries, ignored weeks, empty/mismatched data, input validation,
assistant current-versus-historical behavior and the retained logged fallback.
Existing tests also verify player badges and selection among multiple slots.

These extractions compared the complete OpenAPI document before and after,
and compared the moved logic's Python syntax tree. These were unchanged. No
frontend types needed regeneration. Data rebuilding, database write ownership,
other domains and assistant execution remain separate milestones.
