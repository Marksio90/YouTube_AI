"""Video render pipeline foundation.

Revision ID: 0006_video_render_jobs
Revises: 0005_audio_jobs
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_video_render_jobs"
down_revision = "0005_audio_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE video_render_status AS ENUM ('queued', 'planning', 'rendering', 'completed', 'failed')")

    op.add_column("videos", sa.Column("render_url", sa.Text(), nullable=True))

    op.create_table(
        "video_render_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("script_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_id", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.Enum("queued", "planning", "rendering", "completed", "failed", name="video_render_status", create_type=False), nullable=False),
        sa.Column("engine", sa.String(64), nullable=False),
        sa.Column("input_audio_url", sa.Text(), nullable=False),
        sa.Column("scene_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timeline", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_video_url", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_video_render_jobs_video_id", "video_render_jobs", ["video_id"])
    op.create_index("ix_video_render_jobs_channel_id", "video_render_jobs", ["channel_id"])
    op.create_index("ix_video_render_jobs_script_id", "video_render_jobs", ["script_id"])
    op.create_index("ix_video_render_jobs_task_id", "video_render_jobs", ["task_id"])
    op.create_index("ix_video_render_jobs_status", "video_render_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_video_render_jobs_status", table_name="video_render_jobs")
    op.drop_index("ix_video_render_jobs_task_id", table_name="video_render_jobs")
    op.drop_index("ix_video_render_jobs_script_id", table_name="video_render_jobs")
    op.drop_index("ix_video_render_jobs_channel_id", table_name="video_render_jobs")
    op.drop_index("ix_video_render_jobs_video_id", table_name="video_render_jobs")
    op.drop_table("video_render_jobs")

    op.drop_column("videos", "render_url")
    op.execute("DROP TYPE video_render_status")

