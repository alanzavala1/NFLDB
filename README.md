# NFLDB — NFL Analytics, Game Ratings & Situational Splits

A full-stack NFL analytics platform built on nflfastR play-by-play data. It
provides **per-game player ratings** (EPA-based, percentile-calibrated across
27 seasons) rendered on a **matchup lineup view**, a **situational splits
engine** that conditions any player's or team's stat line on one dimension at
a time, and **Ask NFLDB**, an agent that answers plain-English questions
through the platform's typed queries. All of it is free to access, and every
derived number is verified to reconcile with official NFL stats.

**[Deployment guide →](./DEPLOY.md)** &nbsp;·&nbsp; one-container deploy to Cloud Run (free tier)

![Game lineup — matchup field view with per-player EPA game ratings](docs/img/lineup.png)

---

## Features

- **Per-game player ratings, free.** Every skill player, defender, and kicker
  gets a 3.0–10.0 grade per game, computed from play-by-play EPA and defensive
  event stats and percentile-calibrated over 436,000+ player-games, so a 9.0
  is a top-2% performance. Comparable per-game grades are usually behind a
  subscription; here they cost nothing. Offensive lines get a unit grade
  (public data records nothing per-blocker, so nothing per-blocker is
  invented).
- **The lineup view.** Each game renders one team's offense against the
  other's defense in their actual personnel packages, with rating badges on
  every player and popups charting each passer/receiver's targets by lane and
  depth and each back's carries by gap — exact counts at the data's real
  resolution.
- **Situational splits.** Compare players or teams head-to-head, then break
  any one of them down across 18 dimensions — down, pass depth, pressure,
  play-action, blitz, red zone, dome, competitive-snaps-only, per-opponent,
  and more — with a panel that surfaces where they stand out. Works for
  offense and defense, players and teams.
- **Ask NFLDB.** A tool-calling agent that answers questions through the same
  typed endpoints the site uses. It does not write SQL and cannot invent
  numbers; each answer shows the chain of database lookups behind it. Details
  below.
- **Verified accuracy.** The play-by-play–derived splits reconcile exactly
  with official weekly stats (0 mismatches on attempts / carries / targets,
  league-wide), enforced by automated reconciliation tests that gate every
  deploy.
- **Performance.** gzip (payloads 10–20× smaller), HTTP caching, point-lookup
  indexes, per-request cursors for lock-free concurrent reads, and a pruned
  columnar store.

| Splits explorer — head-to-head, then 18 dimensions at once | Ask NFLDB — verified stats, with receipts |
|---|---|
| ![Splits explorer](docs/img/splits.png) | ![Ask](docs/img/ask.png) |

| Game page — scoring, win probability, team stats | Home — scores, power rankings, storylines |
|---|---|
| ![Game page](docs/img/game.png) | ![Home](docs/img/home.png) |

---

## Engineering notes

### Data accuracy
- Official `weekly_player_stats` is the source of truth for counting stats;
  the situational splits are computed from raw play-by-play yet reconcile to
  it exactly. Getting there meant matching the NFL's own definitions — e.g. a
  pass attempt is a completion/incompletion/interception (not nflfastR's
  `pass_attempt`, which counts sacks in some seasons), and carries include QB
  kneels.
- EPA is standardized across every page. nflfastR's weekly `passing_epa` is
  `SUM(qb_epa)` over dropbacks; the platform reproduces that definition so
  "EPA/att" means the identical number on the Splits, Leaders, and Player
  pages.
- [`api/tests/test_reconciliation.py`](api/tests/test_reconciliation.py)
  enforces all of this against the real database, and the deploy is gated on
  it passing inside the shipped image — a release is blocked if the data
  doesn't reconcile.

### Performance
- Responses gzip ~10–20× (a veteran's splits payload: 570KB → 46KB) — the
  dominant transfer cost.
- HTTP caching: completed seasons are immutable → cached a week; live data →
  5 min.
- ART point-lookup indexes on the large per-request tables, and per-request
  DuckDB cursors (MVCC-isolated) so concurrent reads never serialize on a
  lock.
- The play-by-play store is pruned from 396 to 169 columns, cutting the
  database 872MB → 400MB with no loss of functionality (every builder and
  query re-verified against the slim schema).

### The ratings engine
- Per-game grades from raw play-by-play: QB/RB/WR/TE rate on total EPA over
  their plays; defenders on a weighted event score (sacks, TFLs, INTs,
  PBUs…); kickers on made-vs-expected by distance. Raw scores map through a
  piecewise percentile curve calibrated across all 27 seasons: 6.5 average,
  8+ great, 9+ elite (~top 2%).
- Validated against history: the all-time top-rated QB games are
  Roethlisberger's perfect-rating 2014 game, Brady 2007, and Foles's 7-TD
  game; team power rankings (net EPA/play, early-season shrinkage) put the
  actual Super Bowl teams at the top of each season.
- Known limits are stated: O-lines are graded as a unit on what they allow
  together (sack/QB-hit rate + stuffed-run rate) because public data
  attributes nothing to individual blockers; the UI says so.
- A layered ID crosswalk joins snap counts (PFR ids) to play-by-play (GSIS
  ids) at ~98%+ per game — PFR id → id-map table → normalized name+position —
  so lineups, snaps, and ratings agree on who's who.

### The splits engine
- Long-format materialized tables (`player_splits`, `defense_splits`,
  `team_splits`): one row per `(entity, season, category, dimension, value)`,
  so "overall" always reconciles with the sum of its splits — one source of
  truth.
- Single-dimension by design — no combinatorial explosion of cross-products.
- FTN charting (play-action, blitz, defenders-in-box) joined to the
  play-by-play for 2022+; defensive splits built by unioning 20 per-defender
  credit columns into an events stream.

### Full-stack, typed end-to-end
- FastAPI + Pydantic → OpenAPI → `openapi-typescript` codegen → a fully typed
  React/TypeScript client. A schema change flows to the frontend types
  automatically; no hand-written, drift-prone interfaces.

## Ask NFLDB — the question-answering agent

Ask NFLDB answers natural-language questions about NFL statistics — "How many
rushing yards did Derrick Henry have against stacked boxes in 2023?" — using
only the platform's verified data. It is a Claude tool-calling agent with ~16
typed tools. To answer a question, the model first resolves any player or
team name to a database ID (`resolve_entity`), then calls tools that return
verified numbers: season and career stats, game logs and box scores,
standings, leaders, situational splits, power rankings, and player
comparables. A `query_plays` tool covers granular situations the shaped tools
can't express (for example, a team's red-zone rushing touchdowns): the model
submits structured filters and the server composes the SQL from a whitelist —
the model never writes SQL itself. Answers stream over SSE, follow-up
questions carry text context, sampling is disabled (temperature 0), and each
question has a hard 10-tool-call budget and per-IP rate limiting.

The design constraint throughout is that statistical definitions live in
code, not in the prompt. Official totals are reconciled regular-season-only
numbers; terms like "pressure," "deep," and "success rate" mean the
platform's charted definitions; a vocabulary contract maps everyday football
phrasing onto exact split values. The model can choose which tools to call,
but it cannot redefine what a statistic means.

The agent is evaluated on a 56-question gold set whose expected answers are
computed live from the same verified query layer. The eval grades both tool
routing and the written answer, and is opt-in because it makes billed model
calls. It has caught a real regression: during development, a broken tool
chain scored 88%; the eval isolated the cause, and the fix was re-verified at
100%.

To test whether the typed-tool design is actually necessary, the repository
also contains a text-to-SQL baseline: the same model given the full database
schema and asked to write SQL directly, evaluated on the identical questions
and graders. It was measured twice — first with the raw schema, then again
after adding an accurate data dictionary (table grain, join recipes, name
formats, value vocabularies) to remove documentation gaps as an excuse.

| Architecture | Accuracy | Avg latency | Tokens/question |
|---|---:|---:|---:|
| Typed tools + semantic layer | 56/56 (100%) | 3.7s | ~18,100 |
| Text-to-SQL v2 (with data dictionary) | 37/56 (66%) | 2.6s | ~8,200 |
| Text-to-SQL v1 (raw schema) | 21/56 (38%) | 3.1s | ~7,800 |

All arms run claude-haiku-4-5 (~$0.27 per eval run for the typed agent, with
88% of its input tokens served from prompt cache; ~$0.50 for the baseline).
The typed agent spends more tokens and latency per question on its tool loop;
that is the cost of the accuracy gap above.

The baseline's misses fall into four groups: schema literacy (wrong table or
column, or IDs never joined back to names), definition drift (playoff-
inclusive sums despite the regular-season join recipe stated in its prompt),
metric confusion (touchdown percentage reported as success rate), and
structural gaps (cross-dimension questions that require play-level
composition). The difference between the two systems is enforcement: the
typed agent's definitions are implemented in code, while the baseline's are
stated in its prompt and not always followed.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python, FastAPI, Pydantic, DuckDB |
| Data | `nfl_data_py` / nflfastR (play-by-play, weekly stats, NGS, FTN charting, snaps, rosters) |
| AI | Claude (tool-calling agent over the platform's typed queries — no text-to-SQL) |
| Frontend | React, TypeScript, Vite, Tailwind CSS (custom card design system), Recharts |
| Tests / CI | pytest (incl. data-reconciliation invariants), GitHub Actions |
| Deploy | Docker, Google Cloud Run |

## Architecture

```
nfl_data_py ─► DuckDB (raw play-by-play, ~169 cols)
                    │
                    ├─► materialize ─► player_splits · defense_splits · team_splits
                    │                  player_game_stats · team_season_analytics · comparables
                    │                  player_game_ratings · team_power_rankings · team_game_ol_grades
                    ▼
              FastAPI  (gzip · Cache-Control · per-request cursors)   ── /api/*
                    │                                    └── /api/ask (Claude agent → typed tools)
              OpenAPI ─► openapi-typescript ─► typed React/TS client  ── /
```

One embedded DuckDB file, one process. Concurrency is handled *inside* the
process (independent cursors per request); the DB is single-writer, so the app
runs as a single worker — see the note under [Setup](#setup).

## Project structure

```
nfl-platform/
├── Dockerfile, DEPLOY.md          # one-container deploy → Cloud Run
├── api/
│   ├── main.py                    # FastAPI app: /api routes + serves the SPA
│   ├── ingest.py                  # data pipeline (pbp → materialized tables)
│   ├── splits_core.py             # shared situational-dimension scaffolding
│   ├── splits_builder.py          # player_splits (passing/rushing/receiving)
│   ├── def_splits_builder.py      # defense_splits (event-based)
│   ├── team_splits_builder.py     # team_splits (offense/defense rate profile)
│   ├── game_ratings_builder.py    # per-game player ratings (EPA → percentile curve)
│   ├── power_rankings_builder.py  # weekly team power rankings (net EPA/play)
│   ├── ol_grades_builder.py       # O-line unit grades (pressure + stuff rate)
│   ├── routers/                   # schedule (incl. lineup/ratings), players, teams, leaders, assistant (Ask NFLDB), meta
│   ├── tests/                     # endpoints, invariants, data-reconciliation
│   └── data/nfl.duckdb            # the database (gitignored; ~400MB)
└── frontend/src/
    ├── components/GameLineupView.tsx  # matchup field view, rating badges, popup charts
    ├── pages/SplitsPage.tsx       # the splits explorer
    ├── pages/AskPage.tsx          # Ask NFLDB
    ├── pages/                     # Schedule, Game, Player, Team, Leaders, Standings
    ├── splits.ts                  # split metrics / dimensions config
    └── api.ts, types/             # typed client (codegen from OpenAPI)
```

## Setup

**Backend**
```bash
cd api
python -m venv venv && venv\Scripts\activate     # Windows
pip install -r requirements.txt
uvicorn main:app --reload                         # :8000 (API under /api)
```

**Frontend**
```bash
cd frontend
npm install
npm run dev                                        # :5173 (proxies /api → :8000)
```

On first boot the API auto-loads recent seasons (a few minutes each, downloads
play-by-play). For a full historical build, run the ingest for the seasons you want.

> **Run a single process.** DuckDB is an embedded, single-writer database, so the
> API runs as one worker — concurrency is handled inside the process (each request
> gets its own cursor; reads run in parallel). Don't run multiple workers
> (`--workers N`, `gunicorn -w N`) or a second server against the same file.

## Tests

```bash
cd api && pytest
```

Covers endpoint behavior, data-quality **invariants**, and
**data-reconciliation** against the real database (splits ⇄ official stats, EPA
consistency, defensive-sack reconciliation). The reconciliation suite skips
cleanly when the DB isn't present (CI) and runs against the baked DB at deploy time.

## Deploy

The whole app ships as one container (frontend + API + database). See
**[DEPLOY.md](./DEPLOY.md)** — fast local build, or the GitHub Actions → Cloud Run
pipeline (free tier).

## Data notes

- **Coverage:** 1999–2025, regular season + playoffs.
- **NGS** (CPOE, time-to-throw, separation) from 2016; **FTN charting**
  (play-action, blitz, box count) from 2022; **snap counts** from ~2012.
- **Known limitation:** a handful of *rushing/receiving yard totals* differ by
  1–3 yards in the pbp-derived views — nflfastR credits lateral/multi-player
  yardage differently than the official scorer. Counts are always exact; this is
  bounded and tested. Defensive *coverage* data (completion % allowed) isn't in
  nflfastR, so defensive splits are event-based (tackles / pressure / takeaways).
