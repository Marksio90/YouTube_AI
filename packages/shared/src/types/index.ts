// Domain entity types shared between frontend, backend API contracts, and worker

export type UUID = string;
export type ISODateString = string;

// ── Pagination ────────────────────────────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface User {
  id: UUID;
  email: string;
  name: string;
  role: UserRole;
  avatar_url: string | null;
  created_at: ISODateString;
}

export type UserRole = "owner" | "admin" | "editor" | "viewer";

// ── Channel ───────────────────────────────────────────────────────────────────
export interface Channel {
  id: UUID;
  youtube_channel_id: string;
  name: string;
  handle: string;
  thumbnail_url: string | null;
  niche: string;
  status: ChannelStatus;
  subscriber_count: number;
  view_count: number;
  video_count: number;
  monetization_enabled: boolean;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export type ChannelStatus = "active" | "inactive" | "suspended" | "pending_auth";

// ── Video ─────────────────────────────────────────────────────────────────────
export interface Video {
  id: UUID;
  channel_id: UUID;
  youtube_video_id: string | null;
  title: string;
  description: string | null;
  status: VideoStatus;
  visibility: VideoVisibility;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  scheduled_at: ISODateString | null;
  published_at: ISODateString | null;
  script_id: UUID | null;
  pipeline_run_id: UUID | null;
  view_count: number;
  like_count: number;
  comment_count: number;
  revenue_usd: number;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export type VideoStatus =
  | "draft"
  | "scripting"
  | "producing"
  | "rendering"
  | "review"
  | "scheduled"
  | "published"
  | "failed";

export type VideoVisibility = "public" | "unlisted" | "private";

// ── Script ────────────────────────────────────────────────────────────────────
export interface Script {
  id: UUID;
  channel_id: UUID;
  video_id: UUID | null;
  title: string;
  hook: string;
  body: string;
  cta: string;
  keywords: string[];
  target_duration_seconds: number;
  tone: ScriptTone;
  status: ScriptStatus;
  seo_score: number | null;
  compliance_score: number | null;
  version: number;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export type ScriptTone = "educational" | "entertaining" | "inspirational" | "controversial" | "news";
export type ScriptStatus = "draft" | "review" | "approved" | "rejected" | "archived";

// ── Pipeline ──────────────────────────────────────────────────────────────────
export interface Pipeline {
  id: UUID;
  name: string;
  description: string | null;
  channel_id: UUID | null;
  steps: PipelineStep[];
  is_active: boolean;
  schedule_cron: string | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export interface PipelineStep {
  id: string;
  type: PipelineStepType;
  name: string;
  config: Record<string, unknown>;
  depends_on: string[];
  retry_limit: number;
  timeout_seconds: number;
}

export type PipelineStepType =
  | "research_topic"
  | "generate_script"
  | "review_compliance"
  | "generate_thumbnail"
  | "render_video"
  | "upload_youtube"
  | "schedule_post"
  | "notify";

export interface PipelineRun {
  id: UUID;
  pipeline_id: UUID;
  status: PipelineRunStatus;
  triggered_by: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: string | null;
  step_results: PipelineStepResult[];
  started_at: ISODateString;
  completed_at: ISODateString | null;
}

export type PipelineRunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface PipelineStepResult {
  step_id: string;
  status: PipelineRunStatus;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: ISODateString | null;
  completed_at: ISODateString | null;
  retry_count: number;
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export interface ChannelAnalytics {
  channel_id: UUID;
  period: AnalyticsPeriod;
  views: number;
  watch_time_hours: number;
  subscribers_gained: number;
  subscribers_lost: number;
  revenue_usd: number;
  rpm: number;
  cpm: number;
  ctr: number;
  avg_view_duration_seconds: number;
  impressions: number;
}

export type AnalyticsPeriod = "7d" | "28d" | "90d" | "365d" | "lifetime";

// ── Tasks (async) ─────────────────────────────────────────────────────────────
export interface AsyncTask {
  task_id: string;
  status: AsyncTaskStatus;
  progress: number;
  result: unknown;
  error: string | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export type AsyncTaskStatus = "pending" | "started" | "progress" | "success" | "failure" | "revoked";

// ── API Responses ─────────────────────────────────────────────────────────────
export interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
}

export interface ApiResponse<T> {
  data: T;
  meta?: Record<string, unknown>;
}
