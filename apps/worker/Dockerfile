# syntax=docker/dockerfile:1.10
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1
WORKDIR /app

# ── Builder: compile PRODUCTION deps into isolated venv ───────────────────────
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip && \
    python3 -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); open('/tmp/r.txt','w').write('\n'.join(d['project']['dependencies']))" && \
    /venv/bin/pip install --no-cache-dir -r /tmp/r.txt

# ── Development: prod + dev deps (watchmedo for hot reload) ───────────────────
FROM base AS development
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN mkdir -p worker && touch worker/__init__.py
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
CMD ["celery", "-A", "worker.celery_app", "worker", \
     "--loglevel=debug", "--concurrency=2", \
     "-Q", "default,high,ai,media,analytics,pipeline"]

# ── Production: slim runtime + prod venv only ─────────────────────────────────
FROM python:3.12-slim AS production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/venv/bin:$PATH"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /venv /venv
COPY . .
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser && \
    chown -R appuser:appgroup /app
USER appuser
EXPOSE 9108
CMD ["celery", "-A", "worker.celery_app", "worker", \
     "--loglevel=info", "--concurrency=4", \
     "-Q", "default,high,ai,media,analytics,pipeline"]
