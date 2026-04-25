from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
import structlog

CORRELATION_HEADER = "X-Correlation-ID"
logger = structlog.get_logger(__name__)


def get_correlation_id() -> str | None:
    context = structlog.contextvars.get_contextvars()
    value = context.get("correlation_id")
    return str(value) if value else None


async def correlation_id_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    correlation_id = request.headers.get(CORRELATION_HEADER, str(uuid4()))
    started = perf_counter()

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        http_method=request.method,
        http_path=request.url.path,
    )

    try:
        response: Response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        logger.exception("api.request_failed", duration_ms=duration_ms)
        structlog.contextvars.clear_contextvars()
        raise

    duration_ms = round((perf_counter() - started) * 1000, 2)
    if response.status_code >= 500:
        logger.error("api.request", status_code=response.status_code, duration_ms=duration_ms)
    elif response.status_code >= 400:
        logger.warning("api.request", status_code=response.status_code, duration_ms=duration_ms)
    else:
        logger.info("api.request", status_code=response.status_code, duration_ms=duration_ms)

    response.headers[CORRELATION_HEADER] = correlation_id
    structlog.contextvars.clear_contextvars()
    return response
