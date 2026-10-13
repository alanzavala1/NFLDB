# Frontend data flow

Standings is the first feature moved to the shared data pattern. Other pages
are being migrated individually; some still use manual fetching.

Scores/Schedule now uses this pattern for seasons, schedule, standings, league
leaders, and power rankings. It waits for metadata to confirm a readable season,
then starts the four season-specific queries independently. Loaded and scheduled
seasons are readable here; standings selection still requires loaded statistics.
Each section has its own error/retry state. Cached results stay visible with a
warning when a background refresh fails. The live scoreboard continues using
its existing provider and polling/ordering safeguards.

Scores lives in `frontend/src/features/scores/`. `ScoresPage.tsx` owns query
state, season/week URL choices, and layout. `WeekNavigator.tsx`, `SeasonCard.tsx`,
`FeaturedGame.tsx`, `GameList.tsx`, `SidebarPanels.tsx`, `Storylines.tsx`, and
`SeasonRecap.tsx` own their visible sections. `selectors.ts` chooses the displayed
week, featured game, and kickoff groups; `presentation.ts` contains shared labels
and formatting. Cards receive data and callbacks through props. Game-list rows
also read the shared live provider, so moving them creates no additional pollers.

Leaders now lives in `frontend/src/features/leaders/`. Its page coordinates
metadata, player-stat queries, URL choices, and local sort state. Tables,
column definitions, awards, the dashboard, and the podium have separate owners.
`WpaPanel.tsx` mounts its query only when WPA is selected. Its typed resource
module is `src/api/wpaLeaders.ts`; the existing API method and hook delegate it.
Statistics and WPA failures have separate retries and retain successful cached
results on refresh failures. Shared loaded-season selection is in
`src/utils/seasons.ts`, used by both Standings and Leaders. Scores also permits
scheduled seasons because published fixtures can precede statistics.

The two sortable Leaders views share `LeaderTable.tsx`, backed by TanStack
Table 9. It receives the existing NFL column definitions and exposes their
numeric accessors to the sorting engine. Formatting remains separate, so
`5,000` displays with commas but sorts as `5000`. The page stores a controlled
sorting state for each tab, preserving that tab's choice when switching views.
Only row sorting and its numeric comparator are enabled. Header buttons support
keyboard activation and expose their sort direction through `aria-sort`.
Qualification rules, formulas, grouped labels, colors, and links remain
application-owned. Simple Standings tables and the fixed WPA table remain HTML.

The Table pilot replaced duplicated renderers and handwritten sorting with one
138-line renderer. Its measured cost is roughly 10 KB of additional compressed
JavaScript across the production build. Browser checks preserve numeric sorting,
ties, tab state, keyboard controls, and mobile scrolling; captured desktop,
position-view, and mobile layouts match their pre-pilot screenshots exactly.

Player profiles now read the returned profile without starting season ingestion,
polling ingestion status, or invalidating the profile for years without games.
A known player without game records keeps their biography and shows an empty
state. Request failures show an error and retry; a failed refresh preserves the
cached profile.

Profile and similar-player requests now live in `src/api/players.ts`, using the
shared typed client and canonical query options. Cache keys include the player
ID, and each request consumes Query's cancellation signal. The Player page uses
these options directly; Splits uses the same profile options for its dynamic
queries. Legacy API methods/hooks delegate to the same definitions. Both profile
and comparables now inherit the normal five-minute freshness policy instead of
keeping comparables or Splits profiles permanently fresh.

The profile, league-rank context, and similar-player section have independent
errors and retries. Successful cached results stay visible on refresh failures,
including cached empty comparables. Empty comparables have an explicit message;
their loading message describes fetching rather than implying preparation runs
in the browser. Rank context waits for the profile's latest regular-season year
and shares the existing leaders cache.

Player now lives in `src/features/players/`. `PlayerPage.tsx` coordinates route
state, profile/rank queries, section navigation, and layout. `ProfileHeader.tsx`,
`BackgroundCard.tsx`, `HighlightsBar.tsx`, `CareerTrajectory.tsx`, `CareerTable.tsx`,
`TeamSplits.tsx`, `GameLog.tsx`, and `ComparablesSection.tsx` own their sections.
`selectors.ts` groups returned games into regular-season, postseason, and game-log
views. `stats.ts`, `rankings.ts`, and `careerColumns.ts` keep totals, formatting,
rank qualifications, and column definitions separate from page composition.
Components receive data through props; only Similar Players owns an additional
query. `src/types/navigation.ts` describes the originating-game context shared by
game/player navigation. These route-state types are separate from API schemas.
The old Player page entry is removed; the router imports the feature page.

Team now reads the five newest loaded seasons from server metadata, with controls
to reveal older loaded years. It does not guess five calendar years, queue season
jobs, poll preparation status, or show a preparation spinner. Empty publication
lists have an explicit empty state. Each profile has independent pending/error/
retry feedback; a failed selected year never falls back to another year's detail.
Cached results stay visible with a warning if a refresh fails. Revealing an older
year changes which profile queries are observed and only reads published data.

Team profile, roster, depth-chart, injury, and split requests/options now live in
`src/api/teams.ts`. League-wide analytics live in `src/api/teamAnalytics.ts`.
Each request uses the shared typed client and consumes an `AbortSignal`.
Team-specific cache keys include team/year and, for depth/injuries, optional week.
League analytics use one key per year because a response contains every team.
Legacy methods/hooks delegate to these definitions. Team uses them directly;
Splits reuses canonical team-split and analytics options. These resources inherit
the normal five-minute freshness policy, replacing permanent freshness for splits
and their duplicate Splits-page observers.

Each section distinguishes pending, successful-empty, and failed requests and has
its own retry. Failed refreshes preserve successful cached data and warn, including
empty arrays or an analytics response with no matching team. The roster query
mounts only while its modal is open; closing it cancels unfinished work, and fresh
results are reused on reopening. Analytics derives the focal team from Query data
instead of keeping fetched/loading state in an effect. Unknown roster positions
remain visible under Other.
The selected detail is keyed by team/year so local UI state resets between profiles.
There are no frontend season-loading callers; obsolete `api.loadSeason` is removed.
Backend admin endpoints and generated contract types are unchanged.

Team now lives in `src/features/teams/`. Its small page coordinates publication
metadata, dynamic profile queries, selected/revealed years, and the layout.
`SeasonSidebar.tsx` and `SeasonDetail.tsx` compose the existing sections;
summary, schedule/chart, leaders, analytics, situational splits, injury/lineup,
and roster/full-stat modals each have focused components. `columns.ts`, `stats.ts`,
`selectors.ts`, `analyticsMetrics.ts`, and `splitDefinitions.ts` own presentation
definitions and calculations, while `types.ts` describes their local props/configs.
The router imports this feature directly and the old large Team entry is removed.
The largest feature file is the 210-line column definitions module.

The team-game response now includes `game_type` from schedules, declared in the
backend's TeamGame schema and regenerated frontend contract. Schedule/chart labels
can name playoff rounds, and full-stat summaries count regular-season and playoff
games separately. Previously the UI tried to read this missing field through
untyped casts. The tooltip now uses the chart library's inferred parameter types.

Team's full-stat tables now use TanStack Table 9 for interactive sorting, matching
Leaders. The existing numeric `sortVal` functions become column accessors; display
formatting, share bars, summary strips, and team-total footers remain application
code. The modal keeps independent controlled sorting state for every section in
regular season and postseason. Header buttons support keyboard activation and
expose direction through `aria-sort`, with one column sorted at a time and a
descending/ascending cycle. Section preparation retains the established tie order.
Scrimmage/defense reveal limits apply after sorting; totals include every qualifying
player regardless of visible row count. Existing Table code is shared in the
production bundle; this migration adds no dependency.

Team season selection now belongs to React Router's `season` search parameter,
using the shared loaded-season validator. A bare URL selects the newest published
year; a valid old-year bookmark also reveals that year beyond the initial five
sidebar entries. Invalid or unpublished explicit years show an availability
message and start no profile/section queries until a loaded year is chosen.
Changing the year preserves unrelated query parameters and creates a history
entry, so back/forward restores the view using Query's cache. Re-selecting the
same explicit year does not create a duplicate entry. Revealed sidebar rows
remain local UI state; there is no effect synchronizing a second selected year.

Games now uses the shared typed client and canonical definitions in
`src/api/games.ts` for detail, lineup, and player charts. Its season schedule
uses the existing `src/api/schedule.ts` definition, sharing the same cache as
Scores and Standings. Detail and lineup start independently; schedule waits for
the detail response's season, and a chart starts only when a player is selected.
Chart keys include both game ID and player ID, so one player's different games
cannot share a chart result. Requests consume Query's cancellation signal;
an in-flight shared schedule can remain needed by another observer, while a gap
between observers can cancel and restart it. Fresh completed results are reused.

All four resources expose pending, error, and retry states. Cached successful
results remain visible on refresh failures, including empty lineups, schedules,
and charts. Empty data is distinguished from pending requests; a lineup failure
no longer displays permanent loading, and a missing canonical player ID starts
no chart request. Switching game routes resets the local tab and selected player
while separate query keys prevent late responses from replacing the new game.
Existing game/player origin state, statistical formatting, and live score
overlays remain in place. The live provider still owns pacing and ordering.

Ordinary game queries inherit the normal five-minute freshness policy. The
compatibility API methods and `useGame` hook delegate to the new definitions;
the hook no longer treats an uncharted game as permanently fresh.

Games now lives in `src/features/games/`. `GamePage.tsx` is 107 lines and owns
queries, route context, tab choice, and composition. Header, quarter scores,
team box score, game leaders, player-stat sections, scoring summary, key plays,
and win probability have separate components. `GameLineupView.tsx` coordinates
the lineup's ball choice, rating help, and selected player; field rendering,
player nodes/rotation, the chart modal, passing zones, rushing gaps, and the rail
have their own files. The largest feature file is 183 lines.

Components receive game data and navigation origin through explicit props; the
former game context is removed. `selectors.ts` selects related schedule games
and sums team statistics, `playSelection.ts` identifies key plays, and
`lineupPlacement.ts` arranges players and explains missing grades. Formatting,
chart stat labels, and existing lineup CSS have separate owners. The CSS is
still installed by the Game page, preserving its existing scope and order.
The router imports the feature directly; both former large files are removed.

Nested stat bars, stat sections, player links, and leader sides are now stable
module-level components. Independent request updates preserve keyboard focus
instead of recreating those component types. The win-probability tooltip uses
Recharts' existing types. All 29 former Game lint errors are resolved without
suppressions or new dependencies. Browser checks preserve displayed statistics,
qualification/order, ratios, plays, tooltips, formations/grades, role-specific
maps, and modal closing. Eight desktop/mobile captures match their pre-move
screenshots pixel for pixel; a source audit also verifies unchanged calculations,
constants, and CSS.

Splits now uses `src/api/playerSplits.ts` for typed offensive and defensive
player-splits requests and their canonical query options. Offensive categories
share `['player-splits', playerId]` because that response contains every offensive
category and season; the page filters and aggregates returned rows locally.
Defense uses `['player-def-splits', playerId]`, a separate dataset and cache.
Compatibility API methods and `usePlayerSplits` delegate to the same definitions.
The former permanent freshness override is removed; normal five-minute freshness
and thirty-minute cache retention apply. Requests consume Query's abort signal.

Only the active comparison mode observes data: player mode observes selected
players' splits/profiles, while team mode observes selected team/season splits.
Offense and defense observe only the selected dataset. Removing an entity,
changing mode/category, or leaving the page cancels unneeded requests; separate
cache keys isolate members and team seasons. Profiles and team splits reuse their
previously migrated resource modules. Opponent ranks reuse league analytics only
for a non-career offensive player comparison with at least one selected player.

`src/features/splits/SplitQueryFeedback.tsx` shows independent failures/retries
for each member's splits/profile and the optional rank context, with warnings
that preserve successful cached data. Season and Opponent sections follow profile
request state because their rows come from game logs; situation sections follow
split request state. Pending requests, failures, and successful empty selections
have different messages. A failed comparison member does not hide usable members
or their game logs. Season and remove-member controls have accessible labels.

This checkpoint preserves statistical definitions, sorting, game links, and
comparison/aggregation behavior. The large Splits page/configuration files,
manual search/example resolution, and existing calendar-based season/URL state
remain follow-up work. The backend's current split endpoints can still materialize
missing data on a GET; moving that work offline belongs to the backend milestone.

## Follow one request

1. `frontend/src/features/standings/StandingsPage.tsx` reads the season from
   the URL and asks TanStack Query for the loaded season list.
2. `src/utils/seasons.ts` selects the newest loaded season when the URL has no season.
   An explicit unavailable or malformed year shows a message rather than a
   different year's standings. No loaded seasons means no standings request.
3. `queries.ts` describes the standings request: its cache key is
   `['standings', season]`, and its request function calls `api.ts`.
4. The feature's `api.ts` uses `frontend/src/api/client.ts` to request
   `/api/standings?season=2023`. The backend calculates and returns standings;
   the frontend only formats them.
5. TanStack Query stores the response and exposes loading/error/data state.
   `StandingsTable.tsx` draws the division tables from the returned data.
6. `PlayoffBracket.tsx` uses the same pattern for the season's schedule.
   A playoff request failure is shown separately from the standings table.

## What the tools own

**openapi-fetch** handles HTTP requests using the generated OpenAPI types in
`src/types/api.d.ts`. TypeScript checks endpoint names, parameters, and response
types against the backend contract. These are compile-time checks, not runtime
validation of incoming JSON. Regenerate types when backend schemas change.
The shared client turns unsuccessful HTTP responses into readable errors.

**TanStack Query** manages server state: downloaded results, pending requests,
errors, retries, and cached results. A query key identifies one result. Different
seasons have different keys; requests for the same key share their cache.
The request consumes Query's `AbortSignal`, so leaving a season cancels an
unneeded request. Cancellation saves work; separate keys also keep results isolated.

**React Router** keeps the selected season in the URL. This makes a chosen year
bookmarkable and lets browser back/forward navigate between selections. Changing
the season preserves unrelated URL parameters.

**React components** arrange and display the result. They do not maintain a
second copy of fetched standings in `useState` or start requests in `useEffect`.
The simple division tables remain ordinary HTML tables.

The existing app defaults still apply: results are fresh for five minutes,
cached for thirty minutes, retried once, and not refreshed on window focus.
The season list has a shorter thirty-second freshness window. A failed background
refresh keeps the last successful result visible with a warning and retry button.

## Migration boundary

Shared season and schedule requests live in `src/api/seasons.ts` and
`src/api/schedule.ts`; games, players, teams, leaders, and power rankings have
matching resource modules.
Standings-specific requests and queries live with the
Standings feature. Existing `src/api.ts` methods and `src/queries.ts` hooks
delegate migrated resources to the new implementations so there are no
duplicate endpoint implementations or cache-key definitions for them.
Other endpoints keep their current implementation until their feature migrates.
Remove the compatibility entry points after their remaining callers move.

## Browser regression checks

From `frontend`, install dependencies with `npm ci --legacy-peer-deps`, then:

```sh
npx playwright install chromium
npm run test:e2e
```

Playwright starts Vite and drives Chromium. These tests replace API responses
with controlled fixtures: they need no running Python API, database, or model
credentials. They cover season selection, loading/empty/error/retry behavior,
cancelled late responses, cache reuse, playoff links, and mobile tables.
They verify frontend behavior, not the backend's statistical calculations.
`npm run build` also type-checks the application, test code, and configuration.
CI runs the browser checks after TypeScript. Traces and screenshots are local
test output, ignored by Git.
