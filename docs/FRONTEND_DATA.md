# Frontend data flow: the Standings pilot

Standings is the first feature moved to the shared data pattern. Other pages
are being migrated individually; some still use manual fetching.

Scores/Schedule now uses this pattern for seasons, schedule, standings, league
leaders, and power rankings. It waits for metadata to confirm a readable season,
then starts the four season-specific queries independently. Loaded and scheduled
seasons are readable here; standings selection still requires loaded statistics.
Each section has its own error/retry state. Cached results stay visible with a
warning when a background refresh fails. The live scoreboard continues using
its existing provider and polling/ordering safeguards.

## Follow one request

1. `frontend/src/features/standings/StandingsPage.tsx` reads the season from
   the URL and asks TanStack Query for the loaded season list.
2. `season.ts` selects the newest loaded season when the URL has no season.
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
`src/api/schedule.ts`; leaders and power rankings have matching resource modules.
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
