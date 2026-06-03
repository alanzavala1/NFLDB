import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'

// Code-split each route so the homepage doesn't ship 1000+ lines of
// PlayerPage / TeamPage code that the user may never visit.
const SchedulePage  = lazy(() => import('./pages/SchedulePage'))
const GamePage      = lazy(() => import('./pages/GamePage'))
const TeamPage      = lazy(() => import('./pages/TeamPage'))
const PlayerPage    = lazy(() => import('./pages/PlayerPage'))
const LeadersPage   = lazy(() => import('./pages/LeadersPage'))
const StandingsPage = lazy(() => import('./pages/StandingsPage'))
const SplitsPage    = lazy(() => import('./pages/SplitsPage'))

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
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
