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

## LLM provider/model configuration (startup validated)

Worker startup now validates `LLM_PROVIDER` + `LLM_DEFAULT_MODEL` and fails fast on invalid combinations.

Supported matrix:

- `openai` → model must start with: `gpt-`, `o1-`, `o3-`, or `chatgpt-`
- `local` → any non-empty model (OpenAI-style aliases are auto-mapped to `LLM_LOCAL_MODEL`)
- `mock` → any non-empty model (testing/dev)

Recommended production defaults:

```env
LLM_PROVIDER=openai
LLM_DEFAULT_MODEL=gpt-4o-mini
```

Example local setup:

```env
LLM_PROVIDER=local
LLM_DEFAULT_MODEL=gpt-4o-mini
LLM_LOCAL_BASE_URL=http://ollama:11434/v1
LLM_LOCAL_MODEL=llama3.2
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

## Logging (ELK)

Kustomize now includes an ELK stack:
- Elasticsearch (`elasticsearch:9200`)
- Logstash (`logstash:5044`)
- Kibana (`kibana:5601`)
- Filebeat DaemonSet for pod log shipping

Collected logs (operational scope):
- backend logs
- worker logs
- API errors
- workflow events

### Structured logging and correlation
- Backend and worker logs are emitted as structured JSON in production mode.
- Backend middleware injects `X-Correlation-ID` and propagates `correlation_id` to Celery headers.
- Worker binds `correlation_id`, `task_id`, and `task_name` into task log context.

### Kibana usage

Port-forward Kibana:

```bash
kubectl -n ai-media-os port-forward svc/kibana 5601:5601
```

Create data view in Kibana:
- Index pattern: `ai-media-os-logs-*`
- Time field: `@timestamp`

Useful KQL filters:
- Backend only: `service : "backend"`
- Worker only: `service : "worker"`
- API errors: `service : "backend" and log_level : ("error" or "warning")`
- Workflow events: `event_name : "workflow.*"`
- Correlated trace: `correlation_id : "<id>"`

Search examples:
- Full-text: `message : "timeout"`
- By pod: `pod : "worker-"*`

Operational dashboard: use Kibana Lens / Dashboard with charts by
`service`, `log_level`, and `event_name` over time.

## Autoscaling (HPA + queue pressure)

This repo now ships production-oriented HPA with custom/external metrics:

- **backend HPA**: CPU + per-pod request rate (`api_requests_per_second`)
- **worker HPA**: CPU + queue pressure (`celery_queue_messages`)

To support request/queue metrics in HPA, `prometheus-adapter` is deployed and
registered as `custom.metrics.k8s.io` and `external.metrics.k8s.io`.

### Verify autoscaling

```bash
kubectl -n ai-media-os get hpa backend worker
kubectl get apiservices | grep metrics.k8s.io
kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 | jq
kubectl get --raw /apis/external.metrics.k8s.io/v1beta1 | jq
```

### Runtime behavior

- Backend scales quickly on load spikes (CPU or high RPS) and scales down gradually.
- Worker scales aggressively when queue depth grows and scales down conservatively
  to avoid interrupting long-running jobs.

### Tuning knobs

- Backend threshold: `averageValue: 20` req/s per pod.
- Worker threshold: `averageValue: 30` queue messages per replica.
- Min/max replicas are set in each HPA manifest and should be tuned per plan/SLO.
