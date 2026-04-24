.PHONY: help dev build test lint clean migrate seed logs ps shell-backend shell-worker

COMPOSE = docker compose
BACKEND = $(COMPOSE) exec backend
WORKER  = $(COMPOSE) exec worker

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ──────────────────────────────────────────────────────────────
dev: ## Start all services in development mode
	$(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml up

build: ## Build all Docker images
	$(COMPOSE) build

stop: ## Stop all services
	$(COMPOSE) down

clean: ## Stop and remove all containers, volumes, and images
	$(COMPOSE) down -v --rmi local

ps: ## Show running containers
	$(COMPOSE) ps

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

logs-backend: ## Tail backend logs
	$(COMPOSE) logs -f backend

logs-worker: ## Tail worker logs
	$(COMPOSE) logs -f worker

# ── Database ─────────────────────────────────────────────────────────────────
migrate: ## Run Alembic migrations
	$(BACKEND) alembic upgrade head

migrate-create: ## Create new migration (MSG="description")
	$(BACKEND) alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback one migration
	$(BACKEND) alembic downgrade -1

seed: ## Seed database with initial data
	$(BACKEND) python -m app.db.seed

# ── Shells ───────────────────────────────────────────────────────────────────
shell-backend: ## Open Python shell in backend container
	$(BACKEND) python

shell-worker: ## Open bash in worker container
	$(WORKER) bash

shell-db: ## Open psql in postgres container
	$(COMPOSE) exec postgres psql -U $$POSTGRES_USER -d $$POSTGRES_DB

# ── Testing ───────────────────────────────────────────────────────────────────
test: ## Run all tests
	$(BACKEND) pytest -x -v

test-frontend: ## Run frontend tests
	pnpm --filter frontend test

lint: ## Lint all code
	pnpm lint
	$(BACKEND) ruff check .

typecheck: ## Run TypeScript type checking
	pnpm typecheck

# ── Setup ─────────────────────────────────────────────────────────────────────
setup: ## First-time setup: copy env, install deps, start infra
	cp -n .env.example .env || true
	pnpm install
	$(COMPOSE) up -d postgres redis
	sleep 3
	$(MAKE) migrate
	@echo "\n✓ Setup complete. Run 'make dev' to start all services."
