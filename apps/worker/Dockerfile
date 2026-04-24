# syntax=docker/dockerfile:1.10
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

FROM base AS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN pip install -e ".[dev]"

FROM deps AS development
COPY . .
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=debug", "-Q", "default,ai,pipeline"]

FROM base AS production
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=deps /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
RUN addgroup --system --gid 1001 appgroup \
    && adduser --system --uid 1001 --gid 1001 appuser \
    && chown -R appuser:appgroup /app
USER appuser
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info", "--concurrency=4", "-Q", "default,ai,pipeline"]
