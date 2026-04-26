"""
Database and Redis access for the worker process.

Rules:
- DB access is always async (asyncio.run() wraps at task boundary).
- Redis access is sync (Celery tasks are sync; redis-py sync client).
- Both clients are module-level singletons — created once per worker process.
"""

import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis as redis_sync
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from worker.config import settings

# ── PostgreSQL ────────────────────────────────────────────────────────────────
_engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_recycle=1800,
)

_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Redis (sync) ──────────────────────────────────────────────────────────────
_redis_client: redis_sync.Redis | None = None
_redis_lock = threading.Lock()


def get_redis() -> redis_sync.Redis:
    global _redis_client
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:
                _redis_client = redis_sync.Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                )
    return _redis_client
