"""
Redis-based idempotency guard for Celery tasks.

Usage pattern in tasks:
    guard = IdempotencyGuard()
    idp_key = f"channel:{channel_id}:topic:{topic[:40]}"

    if (cached := guard.get_result(idp_key)) is not None:
        log.info("idempotency.cache_hit", key=idp_key)
        return cached

    with guard.lock(idp_key, task_id=self.request.id):
        result = _do_work(...)
        guard.set_result(idp_key, result, ttl=3600)
    return result
"""

import json
from contextlib import contextmanager
from typing import Any

import structlog

from worker.db import get_redis

log = structlog.get_logger(__name__)

_RESULT_PREFIX = "idp:result:"
_LOCK_PREFIX = "idp:lock:"
_LOCK_TTL = 300  # 5 min — max time a lock is held before auto-release

# Atomically delete the lock only if the caller still owns it.
_RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


class IdempotencyError(RuntimeError):
    """Raised when a lock cannot be acquired (duplicate in-flight task)."""


class IdempotencyGuard:
    """
    Two-layer idempotency:
    1. Result cache — if a previous run completed, return the cached result.
    2. Processing lock — prevents two workers from processing the same key.
    """

    def get_result(self, key: str) -> dict | None:
        raw = get_redis().get(f"{_RESULT_PREFIX}{key}")
        if raw:
            return json.loads(raw)
        return None

    def set_result(self, key: str, result: dict, *, ttl: int) -> None:
        get_redis().setex(f"{_RESULT_PREFIX}{key}", ttl, json.dumps(result))

    def invalidate(self, key: str) -> None:
        """Force re-execution by clearing the cached result."""
        get_redis().delete(f"{_RESULT_PREFIX}{key}")

    def acquire_lock(self, key: str, *, task_id: str) -> bool:
        return bool(
            get_redis().set(f"{_LOCK_PREFIX}{key}", task_id, nx=True, ex=_LOCK_TTL)
        )

    def release_lock(self, key: str, task_id: str) -> None:
        get_redis().eval(_RELEASE_SCRIPT, 1, f"{_LOCK_PREFIX}{key}", task_id)

    @contextmanager
    def lock(self, key: str, *, task_id: str):
        acquired = self.acquire_lock(key, task_id=task_id)
        if not acquired:
            holder = get_redis().get(f"{_LOCK_PREFIX}{key}")
            log.warning("idempotency.lock_contention", key=key, holder=holder)
            raise IdempotencyError(
                f"Idempotency lock held by {holder} for key={key!r}"
            )
        try:
            yield
        except Exception:
            self.release_lock(key, task_id)
            raise
        else:
            self.release_lock(key, task_id)


guard = IdempotencyGuard()
