.PHONY: help dev prod build build-prod stop clean ps logs logs-backend logs-worker logs-frontend \
        migrate migrate-create migrate-down seed \
        shell-backend shell-worker shell-db shell-frontend \
        test test-frontend lint typecheck setup \
        k8s-apply k8s-dry-run k8s-status k8s-migrate k8s-rollout k8s-rollback

COMPOSE      = docker compose
COMPOSE_PROD = docker compose -f docker-compose.yml
BACKEND      = $(COMPOSE) exec backend
WORKER       = $(COMPOSE) exec worker

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Development (default — override.yml auto-applied) ─────────────────────────
dev: ## Start all services in dev mode (hot reload, direct ports)
	$(COMPOSE) up

dev-d: ## Start all services in dev mode (detached)
	$(COMPOSE) up -d

# ── Production ────────────────────────────────────────────────────────────────
prod: ## Start all services in production mode (skips override.yml)
	$(COMPOSE_PROD) up -d

prod-logs: ## Tail logs in production mode
	$(COMPOSE_PROD) logs -f

# ── Build ─────────────────────────────────────────────────────────────────────
build: ## Build all images (dev targets)
	$(COMPOSE) build

build-prod: ## Build all images (production targets)
	$(COMPOSE_PROD) build

# ── Lifecycle ─────────────────────────────────────────────────────────────────
stop: ## Stop all services (keep volumes)
	$(COMPOSE) down

clean: ## Stop and remove containers, volumes, and locally built images
	$(COMPOSE) down -v --rmi local

ps: ## Show running containers and health status
	$(COMPOSE) ps

# ── Logs ─────────────────────────────────────────────────────────────────────
logs: ## Tail logs from all services
	$(COMPOSE) logs -f

logs-backend: ## Tail backend logs
	$(COMPOSE) logs -f backend

logs-worker: ## Tail worker and beat logs
	$(COMPOSE) logs -f worker worker_beat

logs-frontend: ## Tail frontend logs
	$(COMPOSE) logs -f frontend

# ── Database ─────────────────────────────────────────────────────────────────
migrate: ## Run Alembic migrations (upgrade head)
	$(BACKEND) alembic upgrade head

migrate-create: ## Create new migration — MSG="description"
	$(BACKEND) alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback one migration
	$(BACKEND) alembic downgrade -1

migrate-history: ## Show migration history
	$(BACKEND) alembic history --verbose

seed: ## Seed database with initial data
	$(BACKEND) python -m app.db.seed

# ── Shells ────────────────────────────────────────────────────────────────────
shell-backend: ## Open Python shell in backend container
	$(BACKEND) python

shell-worker: ## Open bash shell in worker container
	$(WORKER) bash

shell-db: ## Open psql in postgres container
	$(COMPOSE) exec postgres psql -U $$POSTGRES_USER -d $$POSTGRES_DB

shell-frontend: ## Open sh in frontend container
	$(COMPOSE) exec frontend sh

# ── Testing ───────────────────────────────────────────────────────────────────
test: ## Run backend tests
	$(BACKEND) pytest -x -v

test-frontend: ## Run frontend tests
	pnpm --filter frontend test

lint: ## Lint backend and frontend
	$(BACKEND) ruff check .
	pnpm lint

typecheck: ## Run TypeScript type checking
	pnpm typecheck

# ── Kubernetes ───────────────────────────────────────────────────────────────
NAMESPACE    = ai-media-os
REGISTRY    ?= your-registry.io/ai-media-os
IMAGE_TAG   ?= latest

k8s-dry-run: ## Dry-run kustomize apply (validates manifests)
	kubectl kustomize infra/k8s | kubectl apply --dry-run=client -f -

k8s-apply: ## Apply all k8s manifests (ensure secrets exist first)
	kubectl kustomize infra/k8s | kubectl apply -f -

k8s-status: ## Show pod/hpa/ingress status in namespace
	@echo "── Pods ──────────────────────────────────────────────────"
	kubectl get pods -n $(NAMESPACE)
	@echo "── HPAs ──────────────────────────────────────────────────"
	kubectl get hpa -n $(NAMESPACE)
	@echo "── Ingress ───────────────────────────────────────────────"
	kubectl get ingress -n $(NAMESPACE)

k8s-migrate: ## Run Alembic migrations as a one-off Job in k8s
	kubectl run alembic-migrate-$$(date +%s) \
	  --image=$(REGISTRY)/backend:$(IMAGE_TAG) \
	  --restart=Never --rm -i \
	  -n $(NAMESPACE) \
	  --env-from=secret/ai-media-os-secrets \
	  --env-from=configmap/ai-media-os-config \
	  -- alembic upgrade head

k8s-rollout: ## IMAGE=backend|worker|frontend TAG=v1.2.3 — rolling update
	kubectl set image deployment/$(IMAGE) \
	  $(IMAGE)=$(REGISTRY)/$(IMAGE):$(TAG) \
	  -n $(NAMESPACE)
	kubectl rollout status deployment/$(IMAGE) -n $(NAMESPACE)

k8s-rollback: ## IMAGE=backend|worker|frontend — rollback last deploy
	kubectl rollout undo deployment/$(IMAGE) -n $(NAMESPACE)

# ── First-time setup ──────────────────────────────────────────────────────────
setup: ## First-time setup: copy env → start infra → run migrations
	@test -f .env || (cp .env.example .env && echo "✓ Created .env — fill in secrets before running")
	pnpm install
	$(COMPOSE) up -d postgres redis
	@echo "Waiting for postgres to be healthy…"
	@until $(COMPOSE) exec postgres pg_isready -U $${POSTGRES_USER:-media_os} -q; do sleep 1; done
	$(MAKE) migrate
	@echo ""
	@echo "✓ Setup complete. Run 'make dev' to start all services."
