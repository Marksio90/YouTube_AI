"""Multi-user SaaS foundations: organizations + auth roles.

Revision ID: 0004_multi_tenant_auth
Revises: 0003_compliance
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_multi_tenant_auth"
down_revision = "0003_compliance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.add_column("users", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("channels", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))

    # Backfill: one personal organization per existing user.
    op.execute(
        """
        INSERT INTO organizations (id, created_at, updated_at, name, slug, description)
        SELECT
          id,
          now(), now(),
          COALESCE(name, split_part(email, '@', 1)) || ' Workspace',
          regexp_replace(lower(COALESCE(split_part(email, '@', 1), 'org') || '-' || substr(id::text, 1, 8)), '[^a-z0-9-]', '-', 'g'),
          NULL
        FROM users
        """
    )

    # Organizations were INSERTed with id = users.id, so join directly on id.
    op.execute(
        """
        UPDATE users u
        SET organization_id = o.id
        FROM organizations o
        WHERE o.id = u.id
        """
    )

    # Validate every user received an organization before making the column NOT NULL.
    op.execute(
        """
        DO $$
        DECLARE missing_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO missing_count FROM users WHERE organization_id IS NULL;
            IF missing_count > 0 THEN
                RAISE EXCEPTION 'Backfill incomplete: % user(s) without organization_id', missing_count;
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        UPDATE channels c
        SET organization_id = u.organization_id
        FROM users u
        WHERE c.owner_id = u.id
        """
    )

    op.alter_column("users", "organization_id", nullable=False)
    op.alter_column("channels", "organization_id", nullable=False)

    op.create_foreign_key(
        "fk_users_organization_id",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_channels_organization_id",
        "channels",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_channels_organization_id", "channels", ["organization_id"])

    # Normalize role system to admin/user.
    op.execute("ALTER TYPE user_role RENAME TO user_role_old")
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'user')")
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE user_role
        USING (
          CASE
            WHEN role::text IN ('owner', 'admin') THEN 'admin'
            ELSE 'user'
          END
        )::user_role
        """
    )
    op.execute("DROP TYPE user_role_old")


def downgrade() -> None:
    op.execute("CREATE TYPE user_role_old AS ENUM ('owner', 'admin', 'editor', 'viewer')")
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE user_role_old
        USING (
          CASE
            WHEN role::text = 'admin' THEN 'admin'
            ELSE 'editor'
          END
        )::user_role_old
        """
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_old RENAME TO user_role")

    op.drop_index("ix_channels_organization_id", table_name="channels")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_constraint("fk_channels_organization_id", "channels", type_="foreignkey")
    op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")

    op.drop_column("channels", "organization_id")
    op.drop_column("users", "organization_id")

    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
