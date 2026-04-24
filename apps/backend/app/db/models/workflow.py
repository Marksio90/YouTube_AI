"""
Workflow ORM models.

Three tables:
  workflow_runs        — one row per pipeline execution
  workflow_jobs        — one row per step per run
  workflow_audit_events — append-only event log (never updated)

These replace the simpler pipeline_runs / pipeline_step_results tables with
full state-machine tracking, retry history, and audit trail.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.user import User


# ── Status enums (mirror worker.workflow.types — kept separate to avoid dep) ──

class RunStatus(str, enum.Enum):
    pending   = "pending"
    running   = "running"
    paused    = "paused"
    completed = "completed"
    failed    = "failed"
    cancelled = "cancelled"


class JobStatus(str, enum.Enum):
    pending   = "pending"
    scheduled = "scheduled"
    running   = "running"
    completed = "completed"
    failed    = "failed"
    retrying  = "retrying"
    skipped   = "skipped"
    cancelled = "cancelled"


# ── WorkflowRun ───────────────────────────────────────────────────────────────

class WorkflowRun(Base, UUIDMixin, TimestampMixin):
    """One execution of a named pipeline."""

    __tablename__ = "workflow_runs"

    # ── Identity ──────────────────────────────────────────────────────────────
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_name:    Mapped[str] = mapped_column(String(200), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(50),  nullable=False, default="1.0")

    # ── Status ────────────────────────────────────────────────────────────────
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="workflow_run_status"),
        nullable=False,
        default=RunStatus.pending,
        index=True,
    )
    triggered_by: Mapped[str] = mapped_column(
        String(100), nullable=False, default="manual"
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # ── Shared context (grows as jobs complete) ───────────────────────────────
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timing ────────────────────────────────────────────────────────────────
    started_at:   Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at:    Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Re-run lineage ────────────────────────────────────────────────────────
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    jobs: Mapped[list["WorkflowJob"]] = relationship(
        "WorkflowJob",
        back_populates="run",
        lazy="select",
        order_by="WorkflowJob.created_at",
    )
    audit_events: Mapped[list["WorkflowAuditEvent"]] = relationship(
        "WorkflowAuditEvent",
        back_populates="run",
        lazy="select",
        order_by="WorkflowAuditEvent.occurred_at",
    )

    def __repr__(self) -> str:
        return f"<WorkflowRun {self.id} {self.pipeline_name} {self.status.value}>"


# ── WorkflowJob ───────────────────────────────────────────────────────────────

class WorkflowJob(Base, UUIDMixin, TimestampMixin):
    """One step execution within a WorkflowRun."""

    __tablename__ = "workflow_jobs"

    # ── Identity ──────────────────────────────────────────────────────────────
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id:   Mapped[str] = mapped_column(String(100), nullable=False)
    step_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # ── Status ────────────────────────────────────────────────────────────────
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="workflow_job_status"),
        nullable=False,
        default=JobStatus.pending,
        index=True,
    )

    # ── Retry tracking ────────────────────────────────────────────────────────
    attempt:      Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)

    # ── Per-attempt history (append-only list of {attempt, error, ...} dicts)─
    attempt_history: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # ── Celery integration ────────────────────────────────────────────────────
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Data ─────────────────────────────────────────────────────────────────
    input:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error:  Mapped[str | None]  = mapped_column(Text,  nullable=True)

    # ── Manual override flags ─────────────────────────────────────────────────
    is_manual_result: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    manual_actor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Timing ────────────────────────────────────────────────────────────────
    scheduled_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_after:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms:   Mapped[int | None]      = mapped_column(Integer, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="jobs")

    def __repr__(self) -> str:
        return (
            f"<WorkflowJob {self.step_id} "
            f"attempt={self.attempt}/{self.max_attempts} "
            f"{self.status.value}>"
        )


# ── WorkflowAuditEvent ────────────────────────────────────────────────────────

class WorkflowAuditEvent(Base, UUIDMixin):
    """
    Append-only audit trail.  Rows are NEVER updated — only inserted.
    occurred_at is set at insert time via server default.
    """

    __tablename__ = "workflow_audit_events"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor:      Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    data:       Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="audit_events"
    )

    def __repr__(self) -> str:
        return f"<WorkflowAuditEvent {self.event_type} run={self.run_id}>"
