---
name: start-stack
description: Bring up the full QtoV stack (backend + frontend + Postgres + Langfuse), wait until it's healthy, report the URLs, and tail the logs. Use when asked to "start / bring up / launch / spin up the app (or stack)" or "run everything and watch the logs".
---

# Start the stack & monitor logs

Builds and runs the whole stack with the observability overlay, waits for the backend to come up,
prints the endpoints, then streams logs. (For root-causing a *specific* bad query once it's running,
use the `debug-traces` skill instead.)

## Prereqs
- Docker is running. If `docker info` fails, tell the user to start Docker Desktop and stop.

## Steps

1. **Guard the env.** Creates `.env` from the template if missing and fails fast if the key is unset:
   ```
   make ensure-env
   ```
   If it exits non-zero, relay the message (set `OPENAI_API_KEY` in `.env`) and stop — don't continue.

2. **Build + start the full stack, detached** (returns once containers are up; first run pulls images
   and builds, so it can take a few minutes):
   ```
   docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
   ```
   Run this with the Bash tool's normal (foreground) mode — `-d` makes it return on its own.

3. **Wait for the backend to be healthy** (poll up to ~60s):
   ```
   for i in $(seq 1 30); do curl -fs localhost:8000/api/health && break; sleep 2; done; echo
   ```
   If it never returns `{"status":"ok",...}`, dump recent backend logs to diagnose:
   `docker compose logs --since 3m backend | tail -40`.

4. **Report the endpoints** to the user:
   - Frontend (UI): http://localhost:5173
   - API docs (Swagger): http://localhost:8000/docs
   - Health: http://localhost:8000/api/health
   - Langfuse (traces): http://localhost:3001 — login `admin@example.com` / `changeme123`

5. **Monitor logs.** Tail the app logs (backend/frontend/db; not the noisy Langfuse internals) using the
   Bash tool's **`run_in_background: true`** so new lines stream without blocking the session:
   ```
   make logs
   ```
   - For a one-shot scan of recent problems instead:
     `docker compose logs --since 5m | grep -iE 'error|warning|failed' | tail -30`.
   - Key healthy-path events to expect: `db.ready`, `Application startup complete`, then per query
     `agent.interpreted` → `agent.fetched` → `cache.miss/hit` → `query.completed`.

## Stop
- `make down` stops the whole stack. Add `ARGS=-v` to also wipe the data volumes (fresh DB + Langfuse).

## Notes
- `make up` does the same build+run but in the **foreground** (blocks); this skill uses `-d` so it can
  return and then tail logs.
- The overlay adds ~5 heavy containers (Langfuse web/worker + Postgres + ClickHouse + Redis + MinIO), so
  first boot is slow. To run **app-only** (no Langfuse): `docker compose up -d --build` (base file only).
