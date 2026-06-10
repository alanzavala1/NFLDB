# syntax=docker/dockerfile:1
# Single-image deploy: build the React frontend, then serve it + the FastAPI API
# + the baked DuckDB file from one Python process. Targets Cloud Run / any
# container host. Build from the repo root: `docker build -t nfldb .`

# ---- Stage 1: build the frontend ----
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY frontend/ ./
RUN npm run build            # -> /app/frontend/dist

# ---- Stage 2: backend + static frontend + database ----
FROM python:3.12-slim
WORKDIR /app/api
COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# backend source + the baked DuckDB file (api/data/nfl.duckdb)
COPY api/ ./
# the built frontend, served by FastAPI at / (see main.py)
COPY --from=frontend /app/frontend/dist ./static

# Cloud Run provides $PORT (8080); single worker (DuckDB is single-writer).
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
