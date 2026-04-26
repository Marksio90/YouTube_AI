from __future__ import annotations

from time import perf_counter

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import text

from app.db.session import engine

HTTP_REQUESTS_TOTAL = Counter(
    "api_requests_total",
    "Total HTTP requests handled by FastAPI",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_LATENCY_SECONDS = Histogram(
    "api_request_latency_seconds",
    "Latency of HTTP requests in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

DB_HEALTH = Gauge(
    "db_health_status",
    "Database health status (1=healthy, 0=unhealthy)",
)

DB_QUERY_LATENCY_SECONDS = Histogram(
    "db_healthcheck_latency_seconds",
    "Latency of DB health-check query",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)


async def metrics_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    start = perf_counter()
    response: Response = await call_next(request)
    duration = perf_counter() - start

    route = request.scope.get("route")
    endpoint = (
        getattr(route, "path_format", None)
        or getattr(route, "path", None)
        or "unmatched"
    )
    method = request.method
    status_code = str(response.status_code)

    HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
    HTTP_REQUEST_LATENCY_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)

    return response


async def update_db_health_metric() -> None:
    start = perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        DB_HEALTH.set(1)
    except Exception:
        DB_HEALTH.set(0)
    finally:
        DB_QUERY_LATENCY_SECONDS.observe(perf_counter() - start)


async def metrics_response() -> Response:
    await update_db_health_metric()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
