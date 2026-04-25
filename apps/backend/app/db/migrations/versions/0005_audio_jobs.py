"""Audio job tracking + script audio metadata.

Revision ID: 0005_audio_jobs
Revises: 0004_multi_tenant_auth
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_audio_jobs"
down_revision = "0004_multi_tenant_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE audio_provider AS ENUM ('openai', 'elevenlabs')")
    op.execute("CREATE TYPE audio_job_status AS ENUM ('queued', 'processing', 'completed', 'failed')")

    op.add_column("scripts", sa.Column("audio_url", sa.Text(), nullable=True))
    op.add_column("scripts", sa.Column("audio_duration_seconds", sa.Numeric(8, 2), nullable=True))
    op.add_column("scripts", sa.Column("audio_provider", sa.String(32), nullable=True))
    op.add_column("scripts", sa.Column("audio_voice_id", sa.String(100), nullable=True))

    op.create_table(
        "audio_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("script_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False, unique=True),
        sa.Column("provider", sa.Enum("openai", "elevenlabs", name="audio_provider", create_type=False), nullable=False),
        sa.Column("voice_id", sa.String(100), nullable=False),
        sa.Column("tempo", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("tone", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.Enum("queued", "processing", "completed", "failed", name="audio_job_status", create_type=False), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("audio_url", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audio_jobs_script_id", "audio_jobs", ["script_id"])
    op.create_index("ix_audio_jobs_channel_id", "audio_jobs", ["channel_id"])
    op.create_index("ix_audio_jobs_task_id", "audio_jobs", ["task_id"])
    op.create_index("ix_audio_jobs_status", "audio_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_audio_jobs_status", table_name="audio_jobs")
    op.drop_index("ix_audio_jobs_task_id", table_name="audio_jobs")
    op.drop_index("ix_audio_jobs_channel_id", table_name="audio_jobs")
    op.drop_index("ix_audio_jobs_script_id", table_name="audio_jobs")
    op.drop_table("audio_jobs")

    op.drop_column("scripts", "audio_voice_id")
    op.drop_column("scripts", "audio_provider")
    op.drop_column("scripts", "audio_duration_seconds")
    op.drop_column("scripts", "audio_url")

    op.execute("DROP TYPE audio_job_status")
    op.execute("DROP TYPE audio_provider")

