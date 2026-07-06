.DEFAULT_GOAL := help
# Full stack = app (backend/frontend/db) + the self-hosted Langfuse observability overlay.
# up/down/watch use this so everything starts and stops together.
COMPOSE := docker compose -f docker-compose.yml -f docker-compose.observability.yml
# Base app only (no overlay) — used by host-dev helpers like `make db`.
COMPOSE_BASE := docker compose

.PHONY: help install ensure-env db backend frontend dev up watch down logs test lint seed evals mcp

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install backend (uv) + frontend (npm) dependencies
	cd backend && uv sync --extra dev --extra mcp
	cd frontend && npm install

db:  ## Start only Postgres (for host development)
	$(COMPOSE_BASE) up -d db

backend:  ## Run the backend with hot reload on :8000 (host)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:  ## Run the Vite dev server on :5173 (host)
	npm --prefix frontend run dev

dev: db  ## Run backend + frontend together (host); Ctrl-C stops both
	@echo "Backend :8000  |  Frontend :5173  — Ctrl-C to stop both"
	@trap 'kill 0' INT TERM EXIT; \
		( cd backend && uv run uvicorn app.main:app --reload --port 8000 ) & \
		( npm --prefix frontend run dev ) & \
		wait

ensure-env:  ## Create .env from the template if missing; require OPENAI_API_KEY
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "→ Created .env from .env.example."; \
	fi
	@if ! grep -qE '^OPENAI_API_KEY=.+' .env; then \
		echo ""; \
		echo "✗ OPENAI_API_KEY is not set in .env."; \
		echo "  Open .env, set OPENAI_API_KEY=sk-..., then re-run this command."; \
		echo ""; \
		exit 1; \
	fi

up: ensure-env  ## Build + run the full stack (app + Langfuse observability) in Docker
	$(COMPOSE) up --build

watch: ensure-env  ## Run the full Docker stack with file sync
	$(COMPOSE) watch

down:  ## Stop and remove the full stack (add ARGS=-v to also wipe data volumes)
	$(COMPOSE) down $(ARGS)

logs:  ## Tail app logs (backend/frontend/db; not the observability overlay)
	$(COMPOSE_BASE) logs -f

test:  ## Run backend tests
	cd backend && uv run pytest -q

lint:  ## Lint + typecheck backend and frontend
	cd backend && uv run ruff check . && uv run mypy app
	npm --prefix frontend run typecheck

seed:  ## Warm the trial cache by sending the demo queries (stack must be up)
	cd backend && uv run python evals/seed.py

evals:  ## Run the agent classification eval (needs OPENAI_API_KEY)
	cd backend && uv run python evals/run_evals.py

mcp:  ## Run the MCP server over stdio (backend API must be up — see app/mcp_server.py)
	cd backend && uv run --extra mcp python -m app.mcp_server
