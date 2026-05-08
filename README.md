# NFL Platform

A personal NFL statistics platform. Browse schedules, game box scores, player career stats, team season breakdowns, standings, league leaders, and advanced analytics — all sourced from `nfl_data_py` and stored locally in DuckDB.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python, FastAPI, DuckDB |
| Data | `nfl_data_py` (play-by-play, rosters, NGS, snap counts) |
| Frontend | React, TypeScript, Vite, Tailwind CSS, Recharts |

## Project Structure

```
nfl-platform/
├── api/
│   ├── main.py          # FastAPI server + season loading queue
│   ├── ingest.py        # Data pipeline (play-by-play → player_game_stats)
│   ├── database.py      # DuckDB singleton
│   ├── data/nfl.duckdb  # Local database (~35MB/season)
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/       # SchedulePage, GamePage, PlayerPage, TeamPage,
        │                #   LeadersPage, StandingsPage
        ├── components/  # Nav
        ├── utils/       # Team logos, names
        └── api.ts       # Typed API client
```

## Setup

**Backend**
```bash
cd api
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn main:app --reload    # runs on :8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                  # runs on :5173
```

On first startup the API auto-queues the 5 most recent seasons to load. Loading a season takes a few minutes (downloads ~35MB of play-by-play data). Status is visible in the UI.

## Loading Data

Seasons load automatically as you browse. You can also trigger a load manually:

```bash
# Route through the running API (preferred — avoids DB lock)
python api/ingest.py --seasons 2024

# Or load multiple seasons
python api/ingest.py --seasons 2022 2023 2024
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/seasons` | All seasons with load status |
| `POST` | `/seasons/{year}/load` | Queue a season for loading |
| `GET` | `/seasons/{year}/progress` | SSE stream of ingest logs |
| `GET` | `/schedule?season=` | Full schedule grouped by week |
| `GET` | `/games/{game_id}` | Game detail with player stats, quarter scores, win probability |
| `GET` | `/players/{player_id}` | Player profile + career game log + NGS + WPA |
| `GET` | `/teams/{abbrev}?season=` | Team schedule + season leaders |
| `GET` | `/leaders?season=` | League leaders (passing, rushing, receiving, defense) |
| `GET` | `/wpa-leaders?season=` | Win Probability Added leaders by category |
| `GET` | `/standings?season=` | Division standings with full records |
| `GET` | `/search?q=` | Player and team search |

## Features

**Schedule & Games**
- Season schedule grouped by week with live record tracking
- Game box scores with quarter-by-quarter scoring
- Win probability chart — full-game arc from play-by-play `home_wp` data, with TD and turnover markers

**Players**
- Career stats table with traditional, advanced (EPA), Next Gen Stats (CPOE, aDOT, separation, etc.), snap counts, and situational stats (red zone, 3rd down)
- Win Probability Added (WPA) per season in the Advanced Stats section
  - Passers: `air_wpa` (throw credit, including incompletions)
  - Receivers: `yac_wpa` (yards-after-catch credit)
  - Rushers: total `wpa` on rush plays
- Game log per season (expandable)
- Career splits by team

**League Leaders**
- Passing, Rushing, Receiving, Defense tabs — sortable, with traditional + advanced columns
- WPA tab with Passing / Rushing / Receiving sub-tabs, showing top contributors by win probability added

**Standings**
- Full AFC/NFC division standings: W/L/T, PCT, PF, PA, home/away/division records, streak, games back

**Teams**
- Season schedule with entry records
- Regular season and playoff stat leaders

## Data Notes

- **Coverage:** 1999–2025 regular season and playoffs
- **NGS stats** (CPOE, TTT, aDOT, separation, etc.) available from 2016 onward
- **Snap counts** available from ~2012 onward
- **Win probability / WPA** sourced from nflverse play-by-play `home_wp`, `air_wpa`, `yac_wpa`, `wpa` columns
- **Team attribution:** roster table is used as the authoritative team source; play-by-play `posteam`/`defteam` is a fallback only
