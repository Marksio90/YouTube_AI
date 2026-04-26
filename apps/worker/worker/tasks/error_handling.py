from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from worker.idempotency import IdempotencyError

log = structlog.get_logger(__name__)

NON_RETRYABLE_TASK_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    LookupError,
    KeyError,
    TypeError,
    IdempotencyError,
)

RETRYABLE_TASK_ERRORS: tuple[type[Exception], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    OSError,
    httpx.TransportError,
    httpx.HTTPStatusError,
)

TASK_FAILURE_EXCEPTIONS: tuple[type[Exception], ...] = (
    *NON_RETRYABLE_TASK_ERRORS,
    *RETRYABLE_TASK_ERRORS,
)


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, NON_RETRYABLE_TASK_ERRORS):
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, RETRYABLE_TASK_ERRORS)


def log_task_failure(
    logger: Any,
    *,
    task_name: str,
    entity_id: str | None,
    exc: Exception,
    retryable: bool,
) -> None:
    logger.error(
        f"{task_name}.failed",
        task_name=task_name,
        entity_id=entity_id,
        error_type=type(exc).__name__,
        retryable=retryable,
        error=str(exc),
    )
