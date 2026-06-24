/* eslint-disable react-refresh/only-export-components -- app entry point; fast-refresh component-export rules don't apply here */
import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'

// Code-split each route so the homepage doesn't ship 1000+ lines of
// PlayerPage / TeamPage code that the user may never visit. Each importer is
// kept in `routeImporters` so we can *prefetch* the chunks during idle time
// (below) — that turns first navigation to a page from "wait for a JS chunk"
// into "instant", which is the main source of perceived nav slowness. The
// chart pages (Game/Team/Player) also pull the large Recharts chunk, so
// warming them up front is the biggest single win.
const routeImporters = {
  schedule:  () => import('./pages/SchedulePage'),
  game:      () => import('./pages/GamePage'),
  team:      () => import('./pages/TeamPage'),
  player:    () => import('./pages/PlayerPage'),
  leaders:   () => import('./pages/LeadersPage'),
  standings: () => import('./pages/StandingsPage'),
  splits:    () => import('./pages/SplitsPage'),
  ask:       () => import('./pages/AskPage'),
}

const SchedulePage  = lazy(routeImporters.schedule)
const GamePage      = lazy(routeImporters.game)
const TeamPage      = lazy(routeImporters.team)
const PlayerPage    = lazy(routeImporters.player)
const LeadersPage   = lazy(routeImporters.leaders)
const StandingsPage = lazy(routeImporters.standings)
const SplitsPage    = lazy(routeImporters.splits)
const AskPage       = lazy(routeImporters.ask)

// After the initial page is interactive, quietly warm the other route chunks
// during idle time. requestIdleCallback yields to anything more important, so
// this never competes with the visible page; it just means that by the time
// the user clicks through, the code is already loaded. Failures are ignored
// (a prefetch that loses a race is harmless — the lazy() will fetch on demand).
function prefetchRoutes() {
  const warm = () => { for (const load of Object.values(routeImporters)) load().catch(() => {}) }
  const ric = (window as unknown as { requestIdleCallback?: (cb: () => void) => void }).requestIdleCallback
  if (ric) ric(warm)
  else setTimeout(warm, 1500)
}

// Past seasons are immutable, so cache them aggressively.
// Current season can mutate but only on a weekly cadence, so 5 minutes
// is a safe staleness window for the in-flight tab.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,         // 5 min — refetch if data older than this
      gcTime:    30 * 60 * 1000,        // 30 min — keep in cache after unmount
      refetchOnWindowFocus: false,      // stats don't change while tab is open
      retry: 1,
    },
  },
})

function RouteLoading() {
  // Minimal skeleton — keeps the visual area reserved while the chunk loads.
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-gray-600 text-sm">Loading…</div>
    </div>
  )
}

prefetchRoutes()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<RouteLoading />}>
          <Routes>
            <Route path="/teams/:teamAbbrev"  element={<TeamPage />} />
            <Route path="/"                   element={<SchedulePage />} />
            <Route path="/games/:gameId"      element={<GamePage />} />
            <Route path="/players/:playerId"  element={<PlayerPage />} />
            <Route path="/leaders"            element={<LeadersPage />} />
            <Route path="/standings"          element={<StandingsPage />} />
            <Route path="/splits"             element={<SplitsPage />} />
            <Route path="/ask"                element={<AskPage />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
