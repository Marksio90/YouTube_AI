"""Thumbnail variants with A/B scoring.

Revision ID: 0007_thumbnails
Revises: 0006_video_render_jobs
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_thumbnails"
down_revision = "0006_video_render_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thumbnails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ab_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("image_provider", sa.String(20), nullable=False, server_default="mock"),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("concept_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("headline_text", sa.String(200), nullable=False, server_default=""),
        sa.Column("sub_text", sa.String(100), nullable=True),
        sa.Column("layout", sa.String(50), nullable=False, server_default="bold_text"),
        sa.Column(
            "color_scheme",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("composition", sa.Text(), nullable=True),
        sa.Column(
            "visual_elements",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("ai_image_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "predicted_ctr_score",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column("channel_style", sa.String(50), nullable=False, server_default="clean_modern"),
        # A/B scoring
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_winner", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        # Job tracking
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_thumbnails_publication_id", "thumbnails", ["publication_id"])
    op.create_index("ix_thumbnails_channel_id", "thumbnails", ["channel_id"])
    op.create_index("ix_thumbnails_ab_group_id", "thumbnails", ["ab_group_id"])
    op.create_index("ix_thumbnails_status", "thumbnails", ["status"])
    op.create_index("ix_thumbnails_task_id", "thumbnails", ["task_id"])
    op.create_index("ix_thumbnails_is_active", "thumbnails", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_thumbnails_is_active", table_name="thumbnails")
    op.drop_index("ix_thumbnails_task_id", table_name="thumbnails")
    op.drop_index("ix_thumbnails_status", table_name="thumbnails")
    op.drop_index("ix_thumbnails_ab_group_id", table_name="thumbnails")
    op.drop_index("ix_thumbnails_channel_id", table_name="thumbnails")
    op.drop_index("ix_thumbnails_publication_id", table_name="thumbnails")
    op.drop_table("thumbnails")
