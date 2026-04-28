import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import SchedulePage from './pages/SchedulePage'
import GamePage from './pages/GamePage'
import TeamPage from './pages/TeamPage'
import PlayerPage from './pages/PlayerPage'


createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/teams/:teamAbbrev" element={<TeamPage />} />
        <Route path="/" element={<SchedulePage />} />
        <Route path="/games/:gameId" element={<GamePage />} />
        <Route path="/players/:playerId" element={<PlayerPage />} />

      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
