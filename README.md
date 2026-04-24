# AI Media OS

**Enterprise-grade AI Media Operating System for no-face YouTube monetization.**

## Architecture

```
ai-media-os/
├── apps/
│   ├── frontend/          # Next.js 15 — App Router, TypeScript, Tailwind
│   ├── backend/           # FastAPI — async, SQLAlchemy 2.0, Alembic
│   └── worker/            # Celery — AI tasks, pipeline orchestration
├── packages/
│   └── shared/            # Shared TypeScript types + constants
└── infra/
    └── docker/            # Nginx, PostgreSQL init
```

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, TanStack Query, Zustand, Tailwind |
| Backend | FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2 |
| Worker | Celery 5, RedBeat scheduler, Flower monitoring |
| Database | PostgreSQL 16 |
| Cache / Broker | Redis 7 |
| AI | Anthropic Claude (claude-sonnet-4-6), OpenAI fallback |
| Storage | S3-compatible |
| Proxy | Nginx |

## Quick Start

```bash
cp .env.example .env        # fill in secrets
make setup                  # install, start infra, migrate
make dev                    # start all services
```

Services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/docs
- Flower: http://localhost:5555

## Modules

- [x] Monorepo scaffold (Turborepo, pnpm workspaces)
- [x] Database models (User, Channel, Video, Script, Pipeline, PipelineRun)
- [x] REST API v1 (auth, channels, videos, scripts, pipelines)
- [x] Agent layer (ScriptWriter, SEOAnalyzer, ComplianceChecker)
- [x] Celery workers (AI tasks, pipeline orchestration, YouTube upload)
- [x] Frontend shell (dashboard layout, sidebar, routing, API client)
- [ ] Analytics module
- [ ] Monetization tracking
- [ ] YouTube OAuth flow
- [ ] Thumbnail generation agent
- [ ] Video rendering pipeline
