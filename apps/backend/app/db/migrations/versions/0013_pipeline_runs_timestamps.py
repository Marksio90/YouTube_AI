"""Change pipeline_runs.started_at / completed_at from String(64) to TIMESTAMPTZ.

Revision ID: 0013_pipeline_runs_timestamps
Revises: 0012_analytics_composite_index
Create Date: 2026-04-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_pipeline_runs_timestamps"
down_revision = "0012_analytics_composite_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "pipeline_runs",
        "started_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="started_at::TIMESTAMP WITH TIME ZONE",
        existing_nullable=True,
    )
    op.alter_column(
        "pipeline_runs",
        "completed_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="completed_at::TIMESTAMP WITH TIME ZONE",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "pipeline_runs",
        "completed_at",
        type_=sa.String(64),
        postgresql_using="completed_at::TEXT",
        existing_nullable=True,
    )
    op.alter_column(
        "pipeline_runs",
        "started_at",
        type_=sa.String(64),
        postgresql_using="started_at::TEXT",
        existing_nullable=True,
    )
