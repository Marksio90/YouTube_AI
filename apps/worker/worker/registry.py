"""
Task run registry — tracks lifecycle of every task execution in the DB.

The `task_runs` table is worker-owned and created idempotently on startup.
Backend can read it via raw SQL for the /tasks/{task_id}/status endpoint.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# ── DDL (worker-owned table) ──────────────────────────────────────────────────
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         VARCHAR(255) NOT NULL,
    task_name       VARCHAR(255) NOT NULL,
    entity_type     VARCHAR(100),
    entity_id       UUID,
    status          VARCHAR(50)  NOT NULL DEFAULT 'pending',
    progress        INTEGER      NOT NULL DEFAULT 0,
    step            VARCHAR(100),
    input           JSONB,
    result          JSONB,
    error           TEXT,
    retry_count     INTEGER      NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_task_runs_task_id ON task_runs (task_id);
CREATE INDEX IF NOT EXISTS idx_task_runs_entity ON task_runs (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_task_runs_status  ON task_runs (status);
"""


async def ensure_table(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id         VARCHAR(255) NOT NULL,
            task_name       VARCHAR(255) NOT NULL,
            entity_type     VARCHAR(100),
            entity_id       UUID,
            status          VARCHAR(50)  NOT NULL DEFAULT 'pending',
            progress        INTEGER      NOT NULL DEFAULT 0,
            step            VARCHAR(100),
            input           JSONB,
            result          JSONB,
            error           TEXT,
            retry_count     INTEGER      NOT NULL DEFAULT 0,
            started_at      TIMESTAMPTZ,
            completed_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """))
    await db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_task_runs_task_id ON task_runs (task_id)"
    ))
    await db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_task_runs_entity ON task_runs (entity_type, entity_id)"
    ))
    await db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_task_runs_status ON task_runs (status)"
    ))
    await db.commit()


# ── Tracker ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsondump(v: Any) -> str | None:
    if v is None:
        return None
    return json.dumps(v)


async def record_start(
    db: AsyncSession,
    *,
    task_id: str,
    task_name: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    input_data: dict | None = None,
) -> None:
    await db.execute(
        text("""
            INSERT INTO task_runs
                (id, task_id, task_name, entity_type, entity_id,
                 status, progress, input, started_at)
            VALUES
                (:id, :task_id, :task_name, :entity_type, :entity_id,
                 'running', 0, :input, :now)
            ON CONFLICT (task_id) DO UPDATE
                SET status='running', started_at=:now, updated_at=:now
        """),
        {
            "id": str(uuid.uuid4()),
            "task_id": task_id,
            "task_name": task_name,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "input": _jsondump(input_data),
            "now": _now(),
        },
    )


async def record_progress(
    db: AsyncSession,
    *,
    task_id: str,
    progress: int,
    step: str | None = None,
) -> None:
    await db.execute(
        text("""
            UPDATE task_runs
            SET progress=:progress, step=:step, status='running', updated_at=:now
            WHERE task_id=:task_id
        """),
        {"task_id": task_id, "progress": progress, "step": step, "now": _now()},
    )


async def record_success(
    db: AsyncSession,
    *,
    task_id: str,
    result: dict | None = None,
) -> None:
    await db.execute(
        text("""
            UPDATE task_runs
            SET status='success', progress=100, result=:result,
                completed_at=:now, updated_at=:now
            WHERE task_id=:task_id
        """),
        {"task_id": task_id, "result": _jsondump(result), "now": _now()},
    )


async def record_failure(
    db: AsyncSession,
    *,
    task_id: str,
    error: str,
    retry_count: int = 0,
) -> None:
    await db.execute(
        text("""
            UPDATE task_runs
            SET status='failure', error=:error, retry_count=:retry_count,
                completed_at=:now, updated_at=:now
            WHERE task_id=:task_id
        """),
        {
            "task_id": task_id,
            "error": error[:2000],
            "retry_count": retry_count,
            "now": _now(),
        },
    )


async def record_retry(
    db: AsyncSession,
    *,
    task_id: str,
    retry_count: int,
    error: str,
) -> None:
    await db.execute(
        text("""
            UPDATE task_runs
            SET status='retrying', retry_count=:retry_count, error=:error, updated_at=:now
            WHERE task_id=:task_id
        """),
        {
            "task_id": task_id,
            "retry_count": retry_count,
            "error": error[:2000],
            "now": _now(),
        },
    )
