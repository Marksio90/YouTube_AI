import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class PipelineRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Pipeline(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "pipelines"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)

    runs: Mapped[list["PipelineRun"]] = relationship(
        "PipelineRun", back_populates="pipeline", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Pipeline {self.name}>"


class PipelineRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "pipeline_runs"

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(PipelineRunStatus, name="pipeline_run_status"),
        nullable=False,
        default=PipelineRunStatus.pending,
        index=True,
    )
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    input: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_results: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    pipeline: Mapped["Pipeline"] = relationship("Pipeline", back_populates="runs")
    step_result_records: Mapped[list["PipelineStepResult"]] = relationship(
        "PipelineStepResult", back_populates="run", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<PipelineRun {self.id} {self.status}>"


class PipelineStepResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "pipeline_step_results"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(PipelineRunStatus, name="pipeline_run_status"),
        nullable=False,
        default=PipelineRunStatus.pending,
    )
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="step_result_records")
