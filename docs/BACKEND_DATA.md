# Backend data ownership

Core league, team, player and game data now have domain service owners. HTTP
routes and assistant tools call the same ordinary Python functions. The assistant
imports neither HTTP routes nor database query functions. Analytics preparation
runs in a separate offline worker, and serving reads the prepared snapshot.

Offline analytics preparation now has one orchestration function in
`api/pipeline/analytics.py`, called after ingestion prepares its inputs. See
[read-only serving](READ_ONLY_SERVING.md), [native refresh](NATIVE_REFRESH_AUTOMATION.md)
and [deployment](../DEPLOY.md) for the completed preparation/publication boundary.
Core downloads live in `pipeline/sources.py`; optional vendors and their shared
refresh asset catalog live in `pipeline/vendor_sources.py`. Their explicit source
outcomes distinguish retained optional data from newly loaded rows. Pure vendor
normalization is separate from storage and model execution.

## Request flow and responsibilities

```text
React page → TanStack Query → typed HTTP client → FastAPI route
                                                    ↓
Assistant tool ──────────────────────────────→ domain service → read-only DuckDB
```

A page displays information. TanStack Query manages loading, cached responses,
refreshes and retries; the typed client sends the request. A route validates URL
arguments, turns domain absence into HTTP status codes, and validates the response
with Pydantic. A service chooses the football data and assembles plain dictionaries.
DuckDB executes the SQL against a local snapshot. The assistant calls these same
services inside the process, then selects a compact result and records its source.
Live scores use their separate provider; Ask's streaming transport and model loop
also retain their own responsibilities.

For an interview, a player profile is a concrete example: the browser requests
`/api/players/{id}`; the route calls `player_profile.get_player_profile`; that service
combines biography, game logs, snaps, tracking and supplemental queries. The route
returns a validated profile. The assistant's player tools reuse that composition
without making an HTTP call back to the server. One owner for data selection means
a fix can benefit both consumers, while their display choices remain independent.

## Optional data and errors

Required queries use `query_to_dict` and propagate database failures. Optional
feed queries use `safe_query`: only absent relations or source fields registered
in `api/data_errors.py` qualify for a logged empty result. The registry documents
which older/cold snapshot gaps the application accepts. Unknown tables/columns,
invalid SQL/functions/aliases, connection and I/O errors, and other unexpected
failures propagate. Even a registered missing field is an error for a required
query; the caller's contract determines whether a fallback is allowed.

Offline builders use the same classification at their fallback points.
Unexpected read/build/write failures stop preparation. Comparables rolls back
its transaction before rethrowing a write failure. The web process reads the
prepared results, with required missing relations mapped to a 503 response.

`services/seasons.py` reads played and scheduled coverage independently. Missing
optional play data cannot erase an available schedule; an unexpected storage
failure cannot masquerade as an unloaded season. Expected empty data and an absent
entity remain distinct from execution failures. HTTP routes still own the existing
404 responses; Ask's existing execution handler owns tool-failure reporting.

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

The optional roster query uses `safe_query`. Known missing roster schema produces
a logged empty player list while team matches remain available. Unexpected query
or storage errors propagate rather than becoming a successful search with no players.

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

Each category uses `safe_query`: known missing source fields can leave one category
empty while other categories remain available. A missing optional plays table can
produce three logged empty lists. Unexpected query or storage errors propagate.

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
on demand. Its locks, computation and persistence are preserved. Its fallback
points now accept only known missing schema; unexpected builder errors propagate.
Serving remains writable, and changing that is a separate pipeline milestone.
Errors from the required schedule-record query also propagate.

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
The optional query retains a logged empty fallback for known missing feed schema;
unexpected failures propagate.

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
Known missing optional injury schema produces a logged empty list through
`safe_query`; unexpected query and storage failures propagate.

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
Optional play-derived queries use the known-schema fallback described above.
Quarter assembly explicitly skips null quarter identifiers; unexpected query or
conversion failures propagate rather than silently returning a partial chart.

## Game ratings and shared player-game totals

`api/services/game_ratings.py` owns `get_game_ratings(game_id)`: checking whether
the game exists, asking the existing builder for ratings, then joining stored
ratings to player names and positions. An absent game returns `None`; an empty
builder result returns an empty list without running the enrichment query.
The `/api/games/{game_id}/ratings` route retains its `GamePlayerRating` schema
and maps only `None` to the unchanged `Game {game_id} not found` HTTP 404.
This endpoint has no assistant consumer.

Response rows retain the rating table's team and position group. Names prefer
player-game stats, then the same-season roster row selected by latest week and
team; positions come from that roster row. Left joins preserve missing metadata
and null ratings. Ordering remains rating descending with nulls last, then raw
score descending with nulls last, then player name. The builder's stored metric
values and qualification/calibration formulas are unchanged.

`PGS_GAME_CTE` now lives in `api/sql_helpers.py`, imported by the rating, lineup
and player-chart services. A CTE is a named intermediate SQL result;
this one filters to a supplied game ID, groups by player and game, sums all
shared numeric stat columns with nulls treated as zero, and uses the existing
`ANY_VALUE` metadata selections. Selection among differing metadata values
remains unspecified. Moving the fragment preserves its SQL and all consumers.

The builder still reads or materializes missing ratings with its existing lock,
global calibration and known-schema fallback policies. Serving is not yet
read-only. Unexpected service-query failures and builder failures
propagate rather than becoming 404 or successful empty ratings.

## Game player selection

`api/services/game_players.py` owns the existing lineup starter/rotation selection,
personnel labels and position-group fallback shared with player charts. These
functions use only supplied dictionaries: they have no database, HTTP or builder
dependency. The lineup and player-chart services import them; selection
bodies and the existing lineup/chart queries are unchanged.

Starters filter to the requested team and positive snaps in the selected unit,
then sort by snaps, rating and name descending before keeping 11. Rotation
excludes starter IDs, keeps players with snaps in any unit, and sorts rated
players first, then by rating and maximum unit snap count before keeping ten.
Its snap percentage remains the independent maximum across units. Selection
returns new output dictionaries without modifying input rows.

Player-name fallback, nullable metadata, jersey/snaps integer conversion and
touchdown flags are preserved. Offense personnel counts backs and tight ends;
defense labels preserve the existing Nickel/Dime and front-count rules. The
position fallback still normalizes case, maps backs to RB and supported
defenders to DEF, and leaves unsupported positions null. Its existing scope
differs from the wider defensive-personnel vocabulary (for example NB);
consolidating football definitions remains a separate step. Frontend placement
is a display concern and does not change these selected players or ratings.

## Game lineup assembly

`api/services/game_lineup.py` owns `get_game_lineup(game_id)`: schedule lookup,
snap-count identity joins, scoring events, O-line grades and team averages.
It returns ordinary dictionaries, or `None` for an absent game. The
`/api/games/{game_id}/lineup` route retains `GameLineup` response validation and
maps absence to the unchanged `Game {game_id} not found` HTTP 404. This endpoint
has no assistant consumer. The field UI and its placement rules are unchanged.

Snap selection retains the same game/season/team filters and historical
franchise mapping. Identity fields prefer a direct PFR roster match, then an
ID-map match, then normalized name/position matching. Each lookup retains its
existing team/week priorities. Unmatched snap rows keep their supplied name and
position, with nullable roster/rating fields. `join_match_rate` is the rounded
share of rows with a PFR ID that also resolved a player ID; rows without a PFR
ID are excluded from that denominator. No eligible rows produce a null rate.

The service uses shared starter/rotation helpers, keeps both team entries even
without snaps, and computes rounded averages from available ratings. Exact
rotation rating/snap ties retain unspecified ordering. Only known starter IDs
are excluded from rotation, so an unresolved starter can also appear there;
this existing identity behavior remains a separate consistency follow-up.

Scoring retains touchdowns and made field goals, chronological ordering,
defensive touchdown attribution and the existing player-name fallbacks. Its
query uses `safe_query`'s logged empty-list fallback. The required snap join
also reads plays for touchdown badges: a missing plays table therefore fails
that required query rather than merely removing scoring events. Unexpected
schedule/snap failures and uncaught builder failures propagate.

Player ratings and O-line grades still use the existing read-or-materialize
builders. Their writes, locks and formulas are preserved; known missing schema
retains the fallback while unexpected failures propagate. Moving preparation into
an offline pipeline remains separate work.

## Game player charts

`api/services/game_player_chart.py` owns chart profile/stat aggregation, role
selection, play events and optional snap percentage. It takes explicit game and
player IDs and returns ordinary dictionaries. Two plain Python lookup errors
distinguish an absent game from an absent player profile; the route translates
them into the same separate HTTP 404 messages and validates `PlayerChart`.
This endpoint has no assistant consumer, and its chart UI is unchanged.

The shared player-game CTE sums numeric stats before the profile joins. A full
outer join permits either same-season roster data or game statistics to form
the profile. Metadata prefers stats where present; roster position comes from
the latest week with the existing team tiebreaker. A roster-only player remains
valid even without participation in that game. Missing values become the same
zero stat totals; tackles still combine solo and assisted tackles. The existing
ratings builder retains on-demand preparation and known-schema fallback rules.

Role selection counts all matching passer, receiver and rusher plays. Ties
prefer passer, then receiver, then rusher. With no matching plays, the shared
position helper selects defender or kicker; other positions remain `player`.
Events retain their role/lane/yard/outcome rules, nullable fields and the first
80 rows ordered by seconds remaining descending (nulls last), then play ID.
The role comes from all plays, rather than just that capped event list.

Snap percentage retains the PFR/roster join, same-team preference before latest
week, and maximum percentage across units. Known missing optional snap schema is
logged and returns null snap percentage without discarding the chart. Schedule,
profile, role-count and event queries remain required; unexpected failures and
uncaught builder errors propagate instead of becoming a missing-game/player 404.

All six endpoints in `api/routers/schedule.py` now delegate data assembly to
services. The 68-line router owns HTTP parameters, schemas and missing-data
responses, with no database queries or builder calls.

## Player profiles

`services/player_profile.py` composes biography, game logs and regular-season
totals from shared queries. The route owns `PlayerProfile` validation and maps
domain `None` to the original missing-player 404. All three assistant profile
consumers use the service directly and retain their projections/messages.
The assistant no longer imports any HTTP route module.

The profile's supporting queries have focused owners: `player_snaps.py` owns
PFR/name identity, season snap totals and snap-first OL/kicker/punter game logs;
`player_tracking.py` owns NGS tracking and the play-derived CPOE fallback;
`player_advanced.py` owns play-derived statistic families and target shares;
`player_supplemental.py` owns draft/combine, injury, awards and depth lookups.
Their queries, sorting and qualification are preserved; optional-data failures
now use the shared classification above. Identity still uses independent MAX
values; roster/snap scope and
NGS precedence are unchanged. Regular totals exclude playoffs while logs retain
them. Comparables/splits already delegate builders and need no extra wrapper.

## Granular play queries

`services/play_queries.py` owns structured filter validation, schema/season
availability, whitelisted SQL identifiers, fixed measures and bounded grouping.
It returns a plain result containing normalized arguments, rows and a payload
or validation/no-match message. The assistant tool only applies its budget,
records provenance and serializes that result. It no longer owns SQL or imports
database query functions. Existing filter vocabulary, grouping limit and
small-sample note are preserved. Player-ID validation has the same shared owner.
A storage error during metadata discovery propagates without caching a false empty
schema. Team aliases come from `config.MODERN_TEAM_ALIASES`, derived from the
relocation definitions plus the JAC/JAX spelling alias. `era_team_case` retains
its separate season-sensitive reverse mapping for historical display.

Identity rules intentionally differ by data source: profile snaps use PFR/name
lookup, roster projections choose same-season rows, and game lineups constrain
identity to the relevant game/team. They are documented rather than collapsed
into one rule that would change existing football results. Completed regular-season
record calculation belongs to `services/schedule_records.py`; the assistant's
fallback record now imports that helper.

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
historical behavior, projection/provenance, its 20-entry cap, known-schema fallback
and unexpected-error propagation.

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

Rating-service checks are `uv run --locked pytest tests/test_game_ratings_service.py
tests/test_ratings_power.py tests/test_lineup_endpoints.py`. Controlled ratings
and fresh mini-league databases check sorting, projection and nulls, name/roster
fallbacks, one-row joins despite duplicate stats, shared stat sums, actual lazy
table creation, exact missing-game 404s, empty-builder short-circuiting and
query/builder failure propagation. Existing tests verify builder mathematics
and matching lineup/chart results. These checks run without a model.

Player-selection checks are `uv run --locked pytest tests/test_game_players.py
tests/test_lineup_endpoints.py tests/test_ratings_power.py`. They cover starter
filtering/order/caps, rotation exclusion and volume/proportion choices, input
immutability, personnel packages, nullable name/position projection, and the
existing endpoint/builder/chart integration. The helper move preserves function
bodies, and the complete OpenAPI schema is unchanged.

Lineup-service checks are `uv run --locked pytest tests/test_game_lineup_service.py
tests/test_lineup_endpoints.py tests/test_game_players.py tests/test_ratings_power.py`.
Fresh mini-league fixtures check real lazy builders, service/HTTP parity, all
identity paths and lookup priorities, game/year/team isolation, unmatched rows,
historical team mapping, scoring names/order, averages, empty snaps, exact 404s,
optional scoring fallback and required query/builder failures. Parity comparisons
normalize only adjacent rotation rows tied on every selection priority; ordering
between distinct priorities and all other lists remains checked. No model runs.

Player-chart checks are `uv run --locked pytest tests/test_game_player_chart_service.py
tests/test_lineup_endpoints.py tests/test_game_players.py tests/test_ratings_power.py`.
They cover actual lazy ratings, service/HTTP parity, duplicate-stat aggregation
and roster priorities, negative EPA/tackles, role-count ties and fallback roles,
event outcomes/lanes/order/caps, roster-only and stats-only profiles, both exact
404 mappings and short-circuits, optional snap fallback and failures at each
required query and the builder. No model runs or production-freshness claims.

These extractions compared the complete OpenAPI document before and after,
and compared the moved logic's Python syntax tree. These were unchanged. No
frontend types needed regeneration. The intentional error-policy changes have
separate coverage in `test_optional_data_errors.py`: known missing data, invalid
SQL/aliases/functions, runtime failures, independent season feeds, all builder
reads, metadata-cache recovery, quarter-query errors and transaction rollback.
Profile and granular-play service tests verify shared caller results and provenance.
Data rebuilding, database write ownership and assistant execution remain separate
milestones. Model-free tests do not establish live freshness or answer quality.
