"""
AuditLogger — append-only event log for every workflow state change.

Every transition, dispatch, retry, and manual override is written here.
The audit trail is never modified after insertion — only new rows are added.

All writes are fire-and-forget inside the engine: if an audit write fails,
we log the error but do not abort the run.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worker.workflow.types import EventType

log = structlog.get_logger(__name__)

_INSERT_SQL = text("""
    INSERT INTO workflow_audit_events
        (id, run_id, job_id, event_type, actor, data, occurred_at)
    VALUES
        (:id, :run_id, :job_id, :event_type, :actor, :data::jsonb, :occurred_at)
""")


class AuditLogger:
    """
    Writes WorkflowAuditEvent rows.  Never raises — failures are logged only
    so an audit write never silences the real error.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log(
        self,
        *,
        run_id: str,
        event_type: EventType,
        job_id:  str | None = None,
        actor:   str        = "system",
        data:    dict[str, Any] | None = None,
    ) -> None:
        import json
        try:
            await self._db.execute(
                _INSERT_SQL,
                {
                    "id":          str(uuid.uuid4()),
                    "run_id":      run_id,
                    "job_id":      job_id,
                    "event_type":  event_type.value,
                    "actor":       actor,
                    "data":        json.dumps(data) if data else "{}",
                    "occurred_at": _now(),
                },
            )
            await self._db.flush()
        except Exception as exc:
            log.warning(
                "audit.write_failed",
                run_id=run_id,
                event=event_type.value,
                error=str(exc),
            )


def _now() -> datetime:
    return datetime.now(timezone.utc)
