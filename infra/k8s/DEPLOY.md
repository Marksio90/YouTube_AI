# AI Media OS — Kubernetes Deployment Guide

## Prerequisites

- `kubectl` configured against target cluster
- `kustomize` ≥ 5.x (or `kubectl` ≥ 1.27 with built-in kustomize)
- `cert-manager` installed (for TLS)
- `nginx-ingress-controller` installed
- Container images built and pushed to your registry

## Quick Start

### 1. Build and push images

```bash
# Backend
docker build --target production -t your-registry.io/ai-media-os/backend:latest apps/backend/
docker push your-registry.io/ai-media-os/backend:latest

# Worker
docker build --target production -t your-registry.io/ai-media-os/worker:latest apps/worker/
docker push your-registry.io/ai-media-os/worker:latest

# Frontend (build context = repo root)
docker build --target production -f apps/frontend/Dockerfile \
  -t your-registry.io/ai-media-os/frontend:latest .
docker push your-registry.io/ai-media-os/frontend:latest
```

### 2. Update config

Edit `infra/k8s/configmap.yaml` — replace `yourdomain.com` with actual domain.

### 3. Create secrets

**Option A — kubectl (manual):**

```bash
kubectl create namespace ai-media-os

kubectl create secret generic ai-media-os-secrets \
  -n ai-media-os \
  --from-literal=POSTGRES_USER=media_os \
  --from-literal=POSTGRES_PASSWORD='<strong-password>' \
  --from-literal=DATABASE_URL='postgresql+asyncpg://media_os:<password>@postgres:5432/ai_media_os' \
  --from-literal=DATABASE_URL_SYNC='postgresql://media_os:<password>@postgres:5432/ai_media_os' \
  --from-literal=REDIS_PASSWORD='<strong-password>' \
  --from-literal=REDIS_URL='redis://:<redis-password>@redis:6379/0' \
  --from-literal=CELERY_BROKER_URL='redis://:<redis-password>@redis:6379/1' \
  --from-literal=CELERY_RESULT_BACKEND='redis://:<redis-password>@redis:6379/2' \
  --from-literal=REDBEAT_REDIS_URL='redis://:<redis-password>@redis:6379/3' \
  --from-literal=SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=NEXTAUTH_SECRET="$(openssl rand -hex 32)" \
  --from-literal=OPENAI_API_KEY='sk-...' \
  --from-literal=ANTHROPIC_API_KEY='sk-ant-...' \
  --from-literal=YOUTUBE_CLIENT_ID='' \
  --from-literal=YOUTUBE_CLIENT_SECRET='' \
  --from-literal=S3_ENDPOINT_URL='' \
  --from-literal=S3_ACCESS_KEY_ID='' \
  --from-literal=S3_SECRET_ACCESS_KEY='' \
  --from-literal=SENTRY_DSN='' \
  --from-literal=FLOWER_BASIC_AUTH='admin:<password>' \
  --from-literal=POSTGRES_EXPORTER_DSN='postgresql://media_os:<password>@postgres:5432/ai_media_os?sslmode=disable' \
  --from-literal=GRAFANA_ADMIN_USER='admin' \
  --from-literal=GRAFANA_ADMIN_PASSWORD='<strong-password>'
```

**Option B — External Secrets Operator (recommended for prod):**

Use `ExternalSecret` resources pointing to AWS Secrets Manager / Vault / GCP Secret Manager.

### 4. Deploy

```bash
# Dry-run first
kubectl kustomize infra/k8s | kubectl apply --dry-run=client -f -

# Apply
kubectl kustomize infra/k8s | kubectl apply -f -

# Or with kubectl kustomize built-in
kubectl apply -k infra/k8s/
```

### 5. Run database migrations

```bash
kubectl run alembic-migrate \
  --image=your-registry.io/ai-media-os/backend:latest \
  --restart=Never \
  --rm -i \
  -n ai-media-os \
  --env-from=secret/ai-media-os-secrets \
  --env-from=configmap/ai-media-os-config \
  -- alembic upgrade head
```

### 6. Verify

```bash
kubectl get pods -n ai-media-os
kubectl get ingress -n ai-media-os
kubectl get hpa -n ai-media-os
```

## Architecture

```
Internet
   │
   ▼
nginx-ingress (TLS termination)
   ├─ /api/*  ──────────────────► backend:8000 (FastAPI, 2–10 pods)
   ├─ /ws/*   ──────────────────► backend:8000 (WebSocket)
   ├─ /flower/* ────────────────► flower:5555  (basic-auth)
   └─ /*      ──────────────────► frontend:3000 (Next.js, 2–6 pods)

backend ──► postgres (StatefulSet, 20Gi PVC)
backend ──► redis    (StatefulSet, 5Gi PVC)
worker  ──► postgres
worker  ──► redis
beat    ──► redis (RedBeat schedule persistence)
flower  ──► redis
```

## Scaling

Workers scale automatically via HPA (CPU 80%, mem 85%). For task-queue-aware
scaling, install KEDA and use the `celery` scaler targeting queue depths.

## Secrets management

Do **not** apply `secrets.yaml` from this repo directly in production.
Use one of:
- **Sealed Secrets** (`kubeseal`) — encrypted secrets committed to git
- **External Secrets Operator** — syncs from Vault / AWS SM / GCP SM
- **SOPS** — GitOps-friendly encrypted secrets

## Updating images

```bash
# Rolling update backend to a new tag
kubectl set image deployment/backend \
  backend=your-registry.io/ai-media-os/backend:v1.2.3 \
  -n ai-media-os

# Watch rollout
kubectl rollout status deployment/backend -n ai-media-os

# Rollback
kubectl rollout undo deployment/backend -n ai-media-os
```

## Monitoring (Prometheus + Grafana)

The kustomization now deploys:
- Prometheus (`prometheus:9090`)
- Grafana (`grafana:3000`)
- Redis exporter (`redis-exporter:9121`)
- Postgres exporter (`postgres-exporter:9187`)
- Worker metrics service (`worker-metrics:9108`)

Collected metrics:
- API latency + request count (`/metrics` on backend)
- Worker job status (Celery success/failure counters)
- Queue size per Celery queue
- DB health (`db_health_status`)
- Memory usage (`process_resident_memory_bytes`)

Alert rules included:
- `WorkerDown`
- `QueueStuck`
- `HighApiLatency`
- `DatabaseIssues`

Port-forward examples:

```bash
kubectl -n ai-media-os port-forward svc/prometheus 9090:9090
kubectl -n ai-media-os port-forward svc/grafana 3000:3000
```
