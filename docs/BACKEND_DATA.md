# Backend data ownership

League queries, schedules, power rankings and several team views use services. This
establishes a small pattern for the remaining backend work; other assistant
tools still import route functions and will move one domain at a time.

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

## Team injury reports

The team injury-report route delegates to `api/services/team_injuries.py`.
Its path, optional integer season/week parameters, description and `InjuryStatus`
response model are unchanged. The assistant's team-overview tool imports this
service directly alongside the depth-chart service.

An omitted season uses the existing configured current season. An omitted week
selects the latest report for that team and season; newer reports for another
team or season cannot change it. An explicit week selects exactly that report.
Missing weeks, teams or seasons return an empty list without falling back.
Integer week parameters retain their existing unrestricted HTTP range.

Ordering remains Out, Doubtful, Questionable, Probable, then other/null statuses,
with names ordered within each group. The response preserves nullable report,
practice, position and player-ID fields. The query selects the supplied report
values.

The assistant includes reports only in current-season overviews. It preserves
the first 20 service rows, selects its existing compact fields, omits null
values and records provenance. Historical overviews do not request current
injuries. The separate player-profile injury selection is unchanged.
`safe_query`'s existing logged empty-list fallback on query failure is retained
and remains part of the later error-handling work.

## Team rosters

`api/services/team_roster.py` owns roster selection for an explicit team and
season. It returns ordinary player dictionaries or an empty list. It has no
HTTP parameter objects, status codes or default-season configuration.

The `/teams/{team}/roster` route resolves an omitted season through the existing
current-season configuration, then calls the service. Empty rows still produce
HTTP 404 with `No roster found for {team} in {season}`. The response uses the
unchanged `RosterPlayer` schema. Unexpected database errors propagate instead
of being relabeled as missing roster data. This endpoint has no assistant
consumer, and the extraction adds no tool.

Selection still filters team and season, keeps one row per player ID, and orders
by position then name. Nullable position, jersey number and headshot fields are
preserved. The existing deduplication orders by season inside an already fixed
season, so it does not specify which weekly entry wins when their projected
values differ. That ambiguity is preserved by this structural extraction and
is a later roster-consistency task.

## Pregame record annotations

`api/services/schedule_records.py` owns the `attach_records(games)` helper.
Schedule, team-profile and game-detail services import it directly;
the team route no longer imports a helper from the schedule route. It requires only the
supplied game dictionaries, without database or HTTP dependencies.

It groups rows by week and visits weeks in ascending order. All rows in a week
receive `away_record` and `home_record` before any of that week's results are
counted. Completed games update wins/losses/ties; either missing score leaves
the counts unchanged. Ties appear as a third number only when nonzero.

The input list and dictionaries are updated in place, and the same list is
returned with its original row order intact. This matters for game detail,
which passes a temporary list containing prior games and the current game,
then reads the updated current-game dictionary. Callers own the season,
game-type and history scope of the supplied rows. The helper's extraction
preserves that scope and the existing week-based calculation.

## Team profiles

`api/services/team_profile.py` owns profile assembly for an explicit team and
season. It reads that team's schedule, applies the shared pregame-record helper,
and returns regular and non-regular player-total lists with the existing roster
join and aggregation columns. It returns `None` when there are no games.

The `/teams/{team}` route supplies its configured season default, validates the
`TeamProfile` response and maps `None` to the unchanged 404 message. The
assistant imports the service directly and maps absence to its unchanged
no-profile message and provenance record. Its remaining normalization,
standing-based record, current supplemental data and output projection are
preserved. `llm.py` no longer imports team route functions.

Scheduled games with no player stats still form a valid profile with empty
leader lists. Unexpected query errors propagate through the service and its
callers instead of becoming missing profiles. The service has no HTTP exception
or parameter dependency.

The existing `playoff_leaders` field is computed from every non-`REG` game type,
including preseason. Pregame annotations use the supplied team schedule history,
also including those game types. Those scopes are preserved and remain part of
later definition review. Regular totals still use only `REG`; game counts are
distinct; the roster join uses the shared per-player/season selection; and
missing roster fields remain null. The leader queries have no row-order
guarantee, so the UI retains responsibility for their sorting.

Team splits and league-wide team analytics already delegate to their builder
modules; their preparation/write behavior remains pipeline work rather than
requiring an additional pass-through service in this extraction.

## Schedule listing

`api/services/schedule.py` owns season schedule selection, shared pregame-record
annotations and grouping into weeks. It takes an explicit integer season and
returns ordinary dictionaries. The `/api/schedule` route retains the configured
season default, input validation and `ScheduleWeek` response schema.

The query includes all game types and orders by week, then kickoff time. It
does not add date sorting or a regular-season filter. Missing seasons return an
empty list; nullable game fields remain nullable. Pregame records use the same
supplied season history and shared helper as before. Unexpected query failures
propagate through the service and its callers.

The assistant's `find_games` tool and team-overview game-type fallback now import
this service directly. Their behavior is unchanged: game search normalizes team
input, supports week filtering, caps results at 25, and records provenance. A
truncated preview prioritizes non-regular games, keeping postseason games
discoverable, and returns the existing compact fields. The team-overview fallback
uses the same schedule to identify game types missing from profile data.

## Weekly game listing

`api/services/schedule.py` also owns `get_games(week, season)`. This ordinary
function selects exactly the requested week and season, orders by kickoff time,
and returns game dictionaries or an empty list. It includes all game types and
preserves nullable fields. It does not attach pregame records; the HTTP `Game`
schema supplies null record fields, as before.

The `/api/games` route owns the required week parameter constrained to 1–22,
configured season default, response validation and missing-data status. An empty
service result becomes the unchanged HTTP 404 message:
`No games found for week {week}, season {season}`. Unexpected database failures
propagate rather than being relabeled as missing games. This endpoint has no
assistant consumer; season game search continues using `get_schedule`.

## Game detail

`api/services/game_detail.py` owns `get_game_detail(game_id)`: schedule metadata,
pregame records, player box scores, quarter scores, win-probability plays, team
statistics and scoring summary. It returns ordinary dictionaries, or `None` if
the initial schedule lookup finds no game. Missing games stop before subsequent
queries; scheduled games without stats or plays still form valid responses.

The `/api/games/{game_id}` route maps `None` to the same HTTP 404 message,
`Game {game_id} not found`, and validates the unchanged `GameDetail` schema.
The assistant imports the service directly and maps absence to its existing
no-game text and provenance. It retains selected metadata, at most five quarter
rows and the top five players per team ranked by combined passing/rushing/
receiving yards. Zero-volume players and zero statistic fields remain omitted;
the full play chart, scoring summary and team box score stay outside its compact
projection. `llm.py` no longer imports schedule route functions.

The existing record query supplies earlier weeks of the same season, requiring
an away score and retaining all game types. The record helper still requires
both scores to count a result. Player selection keeps the existing roster join,
team correction and one-row-per-player ranking; it does not introduce new stat
aggregation. Quarter totals remain cumulative score differences. Scoring keeps
defensive touchdown/safety attribution and folds extra-point/two-point score
updates into the preceding scoring entry, preserving its description.

Required schedule/history/player query failures propagate through both callers.
Play-derived queries retain `safe_query`'s logged empty fallback; quarter assembly
also retains its broad exception guard, including any rows already assembled.
This structural move preserves those policies. Distinguishing genuine optional
data gaps from unexpected query failures remains separate error-handling work.

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

Team injury-report checks are `uv run --locked pytest
tests/test_team_injuries_service.py tests/test_team_depth_chart_service.py
tests/test_ask_coverage.py`. Isolated injury tables check latest team/season
selection, explicit/missing weeks, default seasons, ordering and nullable
response fields, service/HTTP parity, input validation, assistant current versus
historical behavior, projection/provenance, its 20-entry cap, and logged query
failure fallback.

Team roster checks are `uv run --locked pytest tests/test_team_roster_service.py
tests/test_endpoints.py`. They cover seeded and isolated service/HTTP parity,
deduplication, ordering/projection, nullable fields, team/season isolation,
explicit and default-season 404 messages, malformed season validation and
database-failure propagation through both service and route. Duplicate test rows
have identical projected values; the tests do not claim a latest-week rule.

Record checks are `uv run --locked pytest tests/test_schedule_records.py
tests/test_helpers.py tests/test_endpoints.py tests/test_invariants.py`. The five
existing record tests now live beside two additional checks for unsorted input,
list/row identity, partial scores and same-week entry records. Existing route
checks exercise the helper through schedule, game-detail and team endpoints.

Team-profile checks are `uv run --locked pytest tests/test_team_profile_service.py
tests/test_endpoints.py tests/test_ask_coverage.py`. They cover service/HTTP
parity, schedule scope/order, regular/non-regular totals, distinct games,
roster joins and nulls, assistant record/provenance, missing-profile mappings,
scheduled-only profiles, defaults/validation, short-circuiting and failures at
each query stage. Leader rows are compared by player ID; schedule order remains
checked. Existing local-snapshot coverage verifies a historical team overview.

Schedule checks are `uv run --locked pytest tests/test_schedule_service.py
tests/test_schedule_records.py tests/test_endpoints.py tests/test_ask_coverage.py`.
They cover service/HTTP parity, week grouping and kickoff ordering, all game
types, pregame records, nullable fields, assistant filters/projection/provenance
and its 25-game preview, team-overview fallback, defaults, invalid/empty seasons
and failure propagation. Tool functions run without a model; existing historical
snapshot checks do not establish production freshness or answer quality.

Weekly game checks are `uv run --locked pytest tests/test_weekly_games_service.py
tests/test_schedule_service.py tests/test_endpoints.py tests/test_invariants.py`.
They cover seeded and isolated service/HTTP parity, exact week/season filtering,
kickoff ordering across different dates, game types and nullable fields, absent
domain records versus HTTP null records, week 22, exact empty-result 404 messages,
configured defaults, required/range/type validation before SQL and database error
propagation. These run entirely offline with controlled data.

Game-detail checks are `uv run --locked pytest tests/test_game_detail_service.py
tests/test_schedule_records.py tests/test_lineup_endpoints.py
tests/test_ask_coverage.py`. Isolated mini-league fixtures check HTTP/service parity,
record scope, roster/team selection, quarter deltas, defensive scoring and PAT
folding, conversion rates/penalties/turnovers, win-probability filtering/rounding,
assistant projection/ranking/provenance, missing-game messages, valid unplayed
games, optional play-table fallback and failures at all three required queries.
Existing historical snapshot coverage also checks a known Super Bowl without
calling a model; it does not establish live freshness or model-answer quality.

These extractions compared the complete OpenAPI document before and after,
and compared the moved logic's Python syntax tree. These were unchanged. No
frontend types needed regeneration. Data rebuilding, database write ownership,
other domains and assistant execution remain separate milestones.
