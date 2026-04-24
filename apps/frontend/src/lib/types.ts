// ── Shared API response shapes ────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

// ── Channel ───────────────────────────────────────────────────────────────────

export type ChannelStatus = "active" | "inactive" | "suspended" | "pending_auth";

export interface Channel {
  id: string;
  name: string;
  niche: string;
  youtube_channel_id: string | null;
  subscriber_count: number;
  avg_views: number;
  monetization_enabled: boolean;
  status: ChannelStatus;
  thumbnail_url: string | null;
  created_at: string;
  updated_at: string;
}

// ── Topic ─────────────────────────────────────────────────────────────────────

export type TopicStatus = "new" | "researching" | "briefed" | "rejected" | "archived";
export type TopicSource = "manual" | "trending" | "competitor" | "ai_suggested";

export interface Topic {
  id: string;
  channel_id: string;
  title: string;
  description: string | null;
  keywords: string[];
  trend_score: number | null;
  status: TopicStatus;
  source: TopicSource;
  created_at: string;
  updated_at: string;
}

// ── Brief ─────────────────────────────────────────────────────────────────────

export type BriefStatus = "draft" | "approved" | "rejected" | "archived";

export interface Brief {
  id: string;
  channel_id: string;
  topic_id: string;
  title: string;
  target_audience: string | null;
  key_points: string[];
  seo_keywords: string[];
  estimated_duration_seconds: number | null;
  tone: string | null;
  status: BriefStatus;
  created_at: string;
}

// ── Script ────────────────────────────────────────────────────────────────────

export type ScriptStatus = "draft" | "review" | "approved" | "rejected" | "archived";

export interface Script {
  id: string;
  brief_id: string | null;
  channel_id: string;
  title: string;
  hook: string | null;
  body: string | null;
  cta: string | null;
  keywords: string[];
  tone: string | null;
  seo_score: number | null;
  compliance_score: number | null;
  status: ScriptStatus;
  duration_seconds: number | null;
  audio_url: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

// ── Publication ───────────────────────────────────────────────────────────────

export type PublicationStatus =
  | "draft"
  | "rendering"
  | "review"
  | "scheduled"
  | "published"
  | "failed";

export interface Publication {
  id: string;
  channel_id: string;
  script_id: string | null;
  title: string;
  description: string | null;
  tags: string[];
  youtube_video_id: string | null;
  thumbnail_url: string | null;
  status: PublicationStatus;
  view_count: number;
  like_count: number;
  comment_count: number;
  revenue_usd: number;
  scheduled_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export interface AnalyticsSnapshot {
  id: string;
  channel_id: string;
  publication_id: string | null;
  snapshot_date: string;
  views: number;
  impressions: number;
  ctr: number;
  watch_time_hours: number;
  avg_view_duration_seconds: number;
  like_count: number;
  comment_count: number;
  subscribers_gained: number;
  subscribers_lost: number;
  revenue_usd: number;
  rpm: number;
  cpm: number;
  created_at: string;
}

export interface ChannelAnalytics {
  channel_id: string;
  period_days: number;
  total_views: number;
  total_revenue_usd: number;
  avg_ctr: number;
  avg_view_duration_seconds: number;
  subscribers_net: number;
  snapshots: AnalyticsSnapshot[];
}

// ── Workflow ──────────────────────────────────────────────────────────────────

export type RunStatus = "pending" | "running" | "paused" | "completed" | "failed" | "cancelled";
export type JobStatus =
  | "pending"
  | "scheduled"
  | "running"
  | "completed"
  | "failed"
  | "retrying"
  | "skipped"
  | "cancelled";

export interface WorkflowJob {
  id: string;
  run_id: string;
  step_id: string;
  step_type: string;
  status: JobStatus;
  attempt: number;
  max_attempts: number;
  celery_task_id: string | null;
  output: Record<string, unknown> | null;
  error: string | null;
  is_manual_result: boolean;
  manual_actor: string | null;
  attempt_history: AttemptRecord[];
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  retry_after: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
}

export interface AttemptRecord {
  attempt: number;
  error: string;
  started_at: string;
  failed_at: string;
}

export interface WorkflowRun {
  id: string;
  channel_id: string | null;
  owner_id: string;
  pipeline_name: string;
  pipeline_version: string;
  status: RunStatus;
  triggered_by: string;
  context: Record<string, unknown>;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  paused_at: string | null;
  parent_run_id: string | null;
  created_at: string;
  updated_at: string;
  jobs: WorkflowJob[];
}

export interface WorkflowAuditEvent {
  id: string;
  run_id: string;
  job_id: string | null;
  event_type: string;
  actor: string;
  data: Record<string, unknown>;
  occurred_at: string;
}
