# NFLDB frontend

React and TypeScript interface for NFLDB. See the [project README](../README.md)
for backend setup and the required prepared database.

## Development

```sh
npm ci --legacy-peer-deps
npm run dev
```

Vite serves the interface at `http://localhost:5173` and forwards `/api` to
`http://localhost:8000`. Start the API separately.

## Checks and API types

| Command | Purpose |
|---|---|
| `npm run build` | Check TypeScript and build production assets |
| `npm run lint` | Run ESLint |
| `npm run test:e2e` | Run Playwright browser tests with controlled API responses |
| `npm run gen-types` | Generate TypeScript types from `openapi.json` |

Run `npx playwright install chromium` before the first browser test.
When API schemas change, update `openapi.json` from the backend before regenerating
types; see [frontend data flow](../docs/FRONTEND_DATA.md).

Feature pages live in `src/features/`. Shared requests live in `src/api/`;
`src/types/api.d.ts` contains generated API types. The existing assistant's
streaming client is separate from ordinary TanStack Query requests.
