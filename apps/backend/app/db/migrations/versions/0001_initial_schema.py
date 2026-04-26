"""Initial schema — all tables.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'user')")
    op.execute("CREATE TYPE channel_status AS ENUM ('active', 'inactive', 'suspended', 'pending_auth')")
    op.execute("CREATE TYPE topic_source AS ENUM ('manual', 'trending', 'competitor', 'ai_suggested')")
    op.execute("CREATE TYPE topic_status AS ENUM ('new', 'researching', 'briefed', 'rejected', 'archived')")
    op.execute("CREATE TYPE brief_status AS ENUM ('draft', 'approved', 'rejected', 'archived')")
    op.execute("CREATE TYPE script_tone AS ENUM ('educational', 'entertaining', 'inspirational', 'controversial', 'news')")
    op.execute("CREATE TYPE script_status AS ENUM ('draft', 'review', 'approved', 'rejected', 'archived')")
    op.execute("CREATE TYPE publication_status AS ENUM ('draft', 'rendering', 'review', 'scheduled', 'published', 'failed')")
    op.execute("CREATE TYPE publication_visibility AS ENUM ('public', 'unlisted', 'private')")
    op.execute("CREATE TYPE video_status AS ENUM ('draft', 'scripting', 'producing', 'rendering', 'review', 'scheduled', 'published', 'failed')")
    op.execute("CREATE TYPE video_visibility AS ENUM ('public', 'unlisted', 'private')")
    op.execute("CREATE TYPE snapshot_type AS ENUM ('channel', 'publication')")
    op.execute("CREATE TYPE pipeline_run_status AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled')")
    op.execute("CREATE TYPE workflow_run_status AS ENUM ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')")
    op.execute("CREATE TYPE workflow_job_status AS ENUM ('pending', 'scheduled', 'running', 'completed', 'failed', 'retrying', 'skipped', 'cancelled')")
    op.execute("CREATE TYPE recommendation_type AS ENUM ('improve_thumbnail', 'improve_hook', 'repeat_format', 'kill_topic', 'scale_topic', 'localize')")
    op.execute("CREATE TYPE recommendation_priority AS ENUM ('critical', 'high', 'medium', 'low')")
    op.execute("CREATE TYPE recommendation_status AS ENUM ('pending', 'applied', 'dismissed', 'snoozed')")
    op.execute("CREATE TYPE recommendation_source AS ENUM ('rule', 'ai')")

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("role", sa.Enum("admin", "user", name="user_role", create_type=False), nullable=False),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── channels ──────────────────────────────────────────────────────────────
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("youtube_channel_id", sa.String(64), unique=True, nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("handle", sa.String(100), nullable=True),
        sa.Column("thumbnail_url", sa.Text, nullable=True),
        sa.Column("niche", sa.String(100), nullable=False, server_default="general"),
        sa.Column("status", sa.Enum("active", "inactive", "suspended", "pending_auth", name="channel_status", create_type=False), nullable=False),
        sa.Column("subscriber_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("view_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("video_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("monetization_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("access_token_enc", sa.Text, nullable=True),
        sa.Column("refresh_token_enc", sa.Text, nullable=True),
        sa.Column("token_expiry", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_channels_owner_id", "channels", ["owner_id"])
    op.create_index("ix_channels_youtube_channel_id", "channels", ["youtube_channel_id"])

    # ── topics ────────────────────────────────────────────────────────────────
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("trend_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("source", sa.Enum("manual", "trending", "competitor", "ai_suggested", name="topic_source", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("new", "researching", "briefed", "rejected", "archived", name="topic_status", create_type=False), nullable=False),
        sa.Column("research_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_topics_channel_id", "topics", ["channel_id"])
    op.create_index("ix_topics_status", "topics", ["status"])

    # ── briefs ────────────────────────────────────────────────────────────────
    op.create_table(
        "briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("target_audience", sa.Text, nullable=False, server_default=""),
        sa.Column("key_points", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("seo_keywords", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("competitor_urls", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("estimated_duration_seconds", sa.Integer, nullable=False, server_default="600"),
        sa.Column("tone", sa.String(50), nullable=False, server_default="educational"),
        sa.Column("status", sa.Enum("draft", "approved", "rejected", "archived", name="brief_status", create_type=False), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_briefs_channel_id", "briefs", ["channel_id"])
    op.create_index("ix_briefs_topic_id", "briefs", ["topic_id"])
    op.create_index("ix_briefs_status", "briefs", ["status"])

    # ── scripts ───────────────────────────────────────────────────────────────
    op.create_table(
        "scripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brief_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("briefs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("hook", sa.Text, nullable=False, server_default=""),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("cta", sa.Text, nullable=False, server_default=""),
        sa.Column("keywords", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("target_duration_seconds", sa.Integer, nullable=False, server_default="600"),
        sa.Column("tone", sa.Enum("educational", "entertaining", "inspirational", "controversial", "news", name="script_tone", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("draft", "review", "approved", "rejected", "archived", name="script_status", create_type=False), nullable=False),
        sa.Column("seo_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("compliance_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_scripts_channel_id", "scripts", ["channel_id"])
    op.create_index("ix_scripts_brief_id", "scripts", ["brief_id"])
    op.create_index("ix_scripts_status", "scripts", ["status"])

    # ── publications ──────────────────────────────────────────────────────────
    op.create_table(
        "publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("script_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("brief_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("briefs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("youtube_video_id", sa.String(20), unique=True, nullable=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("status", sa.Enum("draft", "rendering", "review", "scheduled", "published", "failed", name="publication_status", create_type=False), nullable=False),
        sa.Column("visibility", sa.Enum("public", "unlisted", "private", name="publication_visibility", create_type=False), nullable=False),
        sa.Column("thumbnail_url", sa.Text, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("like_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("comment_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("revenue_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_publications_channel_id", "publications", ["channel_id"])
    op.create_index("ix_publications_youtube_video_id", "publications", ["youtube_video_id"])
    op.create_index("ix_publications_status", "publications", ["status"])

    # ── videos ────────────────────────────────────────────────────────────────
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("script_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("youtube_video_id", sa.String(20), unique=True, nullable=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.Enum("draft", "scripting", "producing", "rendering", "review", "scheduled", "published", "failed", name="video_status", create_type=False), nullable=False),
        sa.Column("visibility", sa.Enum("public", "unlisted", "private", name="video_visibility", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_videos_channel_id", "videos", ["channel_id"])
    op.create_index("ix_videos_youtube_video_id", "videos", ["youtube_video_id"])
    op.create_index("ix_videos_status", "videos", ["status"])

    # ── analytics_snapshots ───────────────────────────────────────────────────
    op.create_table(
        "analytics_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("snapshot_type", sa.Enum("channel", "publication", name="snapshot_type", create_type=False), nullable=False),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("views", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ctr", sa.Float, nullable=False, server_default="0"),
        sa.Column("watch_time_hours", sa.Float, nullable=False, server_default="0"),
        sa.Column("avg_view_duration_seconds", sa.Float, nullable=False, server_default="0"),
        sa.Column("like_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("comment_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("subscribers_gained", sa.Integer, nullable=False, server_default="0"),
        sa.Column("subscribers_lost", sa.Integer, nullable=False, server_default="0"),
        sa.Column("revenue_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("rpm", sa.Float, nullable=False, server_default="0"),
        sa.Column("cpm", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("channel_id", "publication_id", "snapshot_date", "snapshot_type", name="uq_analytics_channel_pub_date_type"),
    )
    op.create_index("ix_analytics_snapshots_channel_id", "analytics_snapshots", ["channel_id"])
    op.create_index("ix_analytics_snapshots_publication_id", "analytics_snapshots", ["publication_id"])
    op.create_index("ix_analytics_snapshots_snapshot_date", "analytics_snapshots", ["snapshot_date"])

    # ── pipelines ─────────────────────────────────────────────────────────────
    op.create_table(
        "pipelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("steps", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("schedule_cron", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_pipelines_owner_id", "pipelines", ["owner_id"])

    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "completed", "failed", "cancelled", name="pipeline_run_status", create_type=False), nullable=False),
        sa.Column("triggered_by", sa.String(100), nullable=False, server_default="manual"),
        sa.Column("input", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("output", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("step_results", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("started_at", sa.String(64), nullable=True),
        sa.Column("completed_at", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_pipeline_runs_pipeline_id", "pipeline_runs", ["pipeline_id"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])

    op.create_table(
        "pipeline_step_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.String(100), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "completed", "failed", "cancelled", name="pipeline_run_status", create_type=False), nullable=False),
        sa.Column("output", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_pipeline_step_results_run_id", "pipeline_step_results", ["run_id"])

    # ── workflow_runs ─────────────────────────────────────────────────────────
    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pipeline_name", sa.String(200), nullable=False),
        sa.Column("pipeline_version", sa.String(50), nullable=False, server_default="1.0"),
        sa.Column("status", sa.Enum("pending", "running", "paused", "completed", "failed", "cancelled", name="workflow_run_status", create_type=False), nullable=False),
        sa.Column("triggered_by", sa.String(100), nullable=False, server_default="manual"),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_workflow_runs_channel_id", "workflow_runs", ["channel_id"])
    op.create_index("ix_workflow_runs_owner_id", "workflow_runs", ["owner_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    op.create_table(
        "workflow_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.String(100), nullable=False),
        sa.Column("step_type", sa.String(100), nullable=False),
        sa.Column("status", sa.Enum("pending", "scheduled", "running", "completed", "failed", "retrying", "skipped", "cancelled", name="workflow_job_status", create_type=False), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="4"),
        sa.Column("attempt_history", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("input", postgresql.JSONB, nullable=True),
        sa.Column("output", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("is_manual_result", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("manual_actor", sa.String(255), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_workflow_jobs_run_id", "workflow_jobs", ["run_id"])
    op.create_index("ix_workflow_jobs_status", "workflow_jobs", ["status"])

    op.create_table(
        "workflow_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False, server_default="system"),
        sa.Column("data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_workflow_audit_events_run_id", "workflow_audit_events", ["run_id"])
    op.create_index("ix_workflow_audit_events_job_id", "workflow_audit_events", ["job_id"])
    op.create_index("ix_workflow_audit_events_event_type", "workflow_audit_events", ["event_type"])
    op.create_index("ix_workflow_audit_events_occurred_at", "workflow_audit_events", ["occurred_at"])

    # ── performance_scores ────────────────────────────────────────────────────
    op.create_table(
        "performance_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=True),
        sa.Column("period_days", sa.Integer, nullable=False),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("view_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("ctr_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("retention_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("revenue_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("growth_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_views", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw_ctr", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_retention", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_rpm", sa.Float, nullable=False, server_default="0"),
        sa.Column("raw_revenue", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("raw_subs_net", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rank_in_channel", sa.Integer, nullable=True),
        sa.Column("rank_overall", sa.Integer, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("channel_id", "publication_id", "period_days", name="uq_perf_channel_pub_period"),
    )
    op.create_index("ix_perf_channel_period", "performance_scores", ["channel_id", "period_days"])
    op.create_index("ix_perf_pub_period", "performance_scores", ["publication_id", "period_days"])

    # ── recommendations ───────────────────────────────────────────────────────
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("publications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rec_type", sa.Enum("improve_thumbnail", "improve_hook", "repeat_format", "kill_topic", "scale_topic", "localize", name="recommendation_type", create_type=False), nullable=False),
        sa.Column("priority", sa.Enum("critical", "high", "medium", "low", name="recommendation_priority", create_type=False), nullable=False),
        sa.Column("status", sa.Enum("pending", "applied", "dismissed", "snoozed", name="recommendation_status", create_type=False), nullable=False),
        sa.Column("source", sa.Enum("rule", "ai", name="recommendation_source", create_type=False), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("metric_key", sa.String(50), nullable=True),
        sa.Column("metric_current", sa.Float, nullable=True),
        sa.Column("metric_target", sa.Float, nullable=True),
        sa.Column("impact_label", sa.String(100), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_recommendations_channel_id", "recommendations", ["channel_id"])
    op.create_index("ix_rec_channel_status", "recommendations", ["channel_id", "status"])
    op.create_index("ix_rec_channel_type", "recommendations", ["channel_id", "rec_type"])
    op.create_index("ix_recommendations_rec_type", "recommendations", ["rec_type"])
    op.create_index("ix_recommendations_status", "recommendations", ["status"])


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("performance_scores")
    op.drop_table("workflow_audit_events")
    op.drop_table("workflow_jobs")
    op.drop_table("workflow_runs")
    op.drop_table("pipeline_step_results")
    op.drop_table("pipeline_runs")
    op.drop_table("pipelines")
    op.drop_table("analytics_snapshots")
    op.drop_table("videos")
    op.drop_table("publications")
    op.drop_table("scripts")
    op.drop_table("briefs")
    op.drop_table("topics")
    op.drop_table("channels")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS recommendation_source")
    op.execute("DROP TYPE IF EXISTS recommendation_status")
    op.execute("DROP TYPE IF EXISTS recommendation_priority")
    op.execute("DROP TYPE IF EXISTS recommendation_type")
    op.execute("DROP TYPE IF EXISTS workflow_job_status")
    op.execute("DROP TYPE IF EXISTS workflow_run_status")
    op.execute("DROP TYPE IF EXISTS pipeline_run_status")
    op.execute("DROP TYPE IF EXISTS snapshot_type")
    op.execute("DROP TYPE IF EXISTS video_visibility")
    op.execute("DROP TYPE IF EXISTS video_status")
    op.execute("DROP TYPE IF EXISTS publication_visibility")
    op.execute("DROP TYPE IF EXISTS publication_status")
    op.execute("DROP TYPE IF EXISTS script_status")
    op.execute("DROP TYPE IF EXISTS script_tone")
    op.execute("DROP TYPE IF EXISTS brief_status")
    op.execute("DROP TYPE IF EXISTS topic_status")
    op.execute("DROP TYPE IF EXISTS topic_source")
    op.execute("DROP TYPE IF EXISTS channel_status")
    op.execute("DROP TYPE IF EXISTS user_role CASCADE")
