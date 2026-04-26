"""Add affiliate tracking security, idempotency and audit tables.

Revision ID: 0014_affiliate_tracking_security
Revises: 0013_pipeline_runs_timestamps
Create Date: 2026-04-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_affiliate_tracking_security"
down_revision = "0013_pipeline_runs_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliate_link_clicks", sa.Column("source", sa.String(length=64), nullable=True))
    op.add_column("affiliate_link_clicks", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column("affiliate_link_clicks", sa.Column("user_agent", sa.Text(), nullable=True))
    op.add_column("affiliate_link_clicks", sa.Column("fingerprint", sa.String(length=256), nullable=True))

    op.create_table(
        "affiliate_conversion_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revenue_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(length=256), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["link_id"], ["affiliate_links.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("link_id", "idempotency_key", name="uq_aff_conversion_link_key"),
    )
    op.create_index(
        "ix_aff_conversion_idempotency_link_id",
        "affiliate_conversion_idempotency",
        ["link_id"],
    )

    op.create_table(
        "affiliate_security_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(length=256), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["link_id"], ["affiliate_links.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aff_security_audit_link_id", "affiliate_security_audit", ["link_id"])
    op.create_index("ix_aff_security_audit_event_time", "affiliate_security_audit", ["event_time"])

    op.create_table(
        "affiliate_tracking_nonces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["link_id"], ["affiliate_links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("link_id", "event_type", "nonce", name="uq_aff_tracking_nonce"),
    )
    op.create_index("ix_aff_tracking_nonce_event_time", "affiliate_tracking_nonces", ["created_at"])


def downgrade() -> None:
    op.drop_table("affiliate_tracking_nonces")
    op.drop_table("affiliate_security_audit")
    op.drop_table("affiliate_conversion_idempotency")
    op.drop_column("affiliate_link_clicks", "fingerprint")
    op.drop_column("affiliate_link_clicks", "user_agent")
    op.drop_column("affiliate_link_clicks", "ip_address")
    op.drop_column("affiliate_link_clicks", "source")
