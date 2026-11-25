# Frontend data flow

Pages use TanStack Query and an OpenAPI-typed HTTP client. Feature components
own presentation; resource modules own requests and cache keys.

```text
Page → query options → typed client → /api route
```

## Request pattern

`src/api/client.ts` creates the shared `openapi-fetch` client. Its types come from
`src/types/api.d.ts`. Failed responses become readable errors; `requireData`
rejects a missing response body.

Most resource requests and query options live in `src/api/`. Standings keeps its
small request/options pair in `src/features/standings/`. For example,
`standingsQueryOptions(season)` uses `['standings', season]` as its cache key,
waits for a selected season and passes Query's cancellation signal to the request.
Pages consume those options rather than fetching in effects.

Defaults in `src/main.tsx` keep data fresh for five minutes, retain unused cache
entries for thirty minutes, retry once and disable refetch on window focus.
Resource-specific options can override these defaults. Live scores use server
pacing; assistant streaming uses `src/api/ask.ts` rather than ordinary query caching.

## Loading, errors and coverage

- Confirm season availability before requesting season-dependent statistics.
  Scheduled games can be displayed before that season's statistics are loaded.
- Keep successful cached data visible when a background refresh fails. Show an
  error and retry action for the affected section.
- Treat an empty result separately from loading, failure or unavailable data.
- Include the resource identity and filters in cache keys. Pass the cancellation
  signal through every request.

The Splits page uses separate passing, receiving, rushing and defense requests.
Passing/receiving totals and rate components come from their prepared responses.
Combined rates use summed components, not averages of displayed rates. Missing
components remain unknown; unclassified production stays outside the shown
breakdown. Shared coverage notes explain the affected fields.

## API changes and checks

Update the backend Pydantic schema, export its OpenAPI document to
`frontend/openapi.json`, then run `npm run gen-types` from `frontend/`.
Do not edit `src/types/api.d.ts` by hand.

From `frontend/`:

```sh
npx playwright install chromium
npm run test:e2e
npm run build
```

Browser tests use controlled API responses and cover cache reuse, cancellation,
retry, partial sections, historical availability and responsive layouts.
See [backend services](BACKEND_DATA.md) and [methodology](../api/docs/METHODOLOGY.md)
for the definitions behind the responses.
