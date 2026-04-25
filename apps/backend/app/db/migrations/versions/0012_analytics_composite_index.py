"""Add composite index on analytics_snapshots (channel_id, snapshot_date, snapshot_type).

Revision ID: 0012_analytics_composite_index
Revises: 0011_refresh_token_sessions
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op

revision = "0012_analytics_composite_index"
down_revision = "0011_refresh_token_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_analytics_snapshots_channel_date_type",
        "analytics_snapshots",
        ["channel_id", "snapshot_date", "snapshot_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_snapshots_channel_date_type", table_name="analytics_snapshots")
