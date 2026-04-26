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

// ── Performance Scores ────────────────────────────────────────────────────────

export interface DimensionalScores {
  view_score: number;
  ctr_score: number;
  retention_score: number;
  revenue_score: number;
  growth_score: number;
}

export interface PerformanceScore {
  id: string;
  channel_id: string;
  publication_id: string | null;
  period_days: number;
  score: number;
  dimensions: DimensionalScores;
  raw_views: number;
  raw_ctr: number;
  raw_retention: number;
  raw_rpm: number;
  raw_revenue: number;
  raw_subs_net: number;
  rank_in_channel: number | null;
  rank_overall: number | null;
  computed_at: string;
}

// ── Rankings ──────────────────────────────────────────────────────────────────

export type TopicRecommendation = "pursue" | "consider" | "monitor" | "kill";

export interface TopicRankEntry {
  topic_id: string;
  title: string;
  score: number;
  trend_score: number | null;
  publication_count: number;
  avg_views: number;
  avg_perf_score: number;
  total_revenue: number;
  recommendation: TopicRecommendation;
}

export interface ChannelRankEntry {
  channel_id: string;
  name: string;
  niche: string;
  score: number;
  rank: number;
  total_views: number;
  total_revenue: number;
  avg_ctr: number;
  net_subscribers: number;
}

export interface TopicRankingResponse {
  period_days: number;
  entries: TopicRankEntry[];
}

export interface ChannelRankingResponse {
  period_days: number;
  entries: ChannelRankEntry[];
}

// ── Recommendations ───────────────────────────────────────────────────────────

export type RecommendationType =
  | "improve_thumbnail"
  | "improve_hook"
  | "repeat_format"
  | "kill_topic"
  | "scale_topic"
  | "localize";

export type RecommendationPriority = "critical" | "high" | "medium" | "low";
export type RecommendationStatus = "pending" | "applied" | "dismissed" | "snoozed";

export interface Recommendation {
  id: string;
  channel_id: string;
  publication_id: string | null;
  topic_id: string | null;
  rec_type: RecommendationType;
  priority: RecommendationPriority;
  status: RecommendationStatus;
  source: "rule" | "ai";
  title: string;
  body: string;
  rationale: string;
  metric_key: string | null;
  metric_current: number | null;
  metric_target: number | null;
  impact_label: string | null;
  expires_at: string | null;
  actioned_at: string | null;
  created_at: string;
}

// ── Monetization ─────────────────────────────────────────────────────────────

export type RevenueSourceType = "ads" | "affiliate" | "products" | "sponsorship";
export type AffiliatePlatformType = "amazon" | "impact" | "shareasale" | "cj" | "custom";
export type CommissionType = "percentage" | "fixed";

export interface RevenueStream {
  id: string;
  channel_id: string;
  publication_id: string | null;
  source: RevenueSourceType;
  period_start: string;
  period_end: string;
  revenue_usd: number;
  impressions: number;
  clicks: number;
  conversions: number;
  rpm: number;
  cpm: number;
  commission_rate: number | null;
  cost_usd: number;
  roi_pct: number | null;
  is_estimated: boolean;
  notes: string | null;
  created_at: string;
}

export interface AffiliateLink {
  id: string;
  channel_id: string;
  publication_id: string | null;
  platform: AffiliatePlatformType;
  name: string;
  destination_url: string;
  slug: string | null;
  tracking_id: string | null;
  commission_type: CommissionType;
  commission_value: number;
  total_clicks: number;
  total_conversions: number;
  total_revenue_usd: number;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RevenueBySource {
  source: RevenueSourceType;
  revenue_usd: number;
  share_pct: number;
  roi_pct: number | null;
}

export interface ChannelRevenueOverview {
  channel_id: string;
  period_start: string;
  period_end: string;
  total_revenue_usd: number;
  total_cost_usd: number;
  overall_roi_pct: number | null;
  by_source: RevenueBySource[];
  top_streams: RevenueStream[];
}

export interface PublicationRevenueOverview {
  publication_id: string;
  channel_id: string;
  total_revenue_usd: number;
  total_cost_usd: number;
  roi_pct: number | null;
  by_source: RevenueBySource[];
  streams: RevenueStream[];
}

export interface ROISummary {
  channel_id: string;
  period_start: string;
  period_end: string;
  total_revenue_usd: number;
  total_cost_usd: number;
  roi_pct: number | null;
  revenue_per_video: number;
  cost_per_video: number;
  best_publication_id: string | null;
  best_publication_roi: number | null;
  worst_publication_id: string | null;
  worst_publication_roi: number | null;
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

export type {
  WorkflowActionResponse,
  WorkflowAuditEvent,
  WorkflowAuditResponse,
} from "@/lib/contracts/workflows";

// ── Compliance ────────────────────────────────────────────────────────────────

export type CheckStatus   = "pending" | "running" | "passed" | "flagged" | "blocked" | "error";
export type CheckMode     = "rule" | "ai" | "both";
export type RiskCategory  = "ad_safety" | "copyright_risk" | "factual_risk" | "reused_content" | "ai_disclosure";
export type RiskSeverity  = "critical" | "high" | "medium" | "low" | "info";
export type FlagSource    = "rule" | "ai";

export interface RiskFlag {
  id: string;
  check_id: string;
  category: RiskCategory;
  severity: RiskSeverity;
  source: FlagSource;
  rule_id: string;
  title: string;
  detail: string;
  evidence: string | null;
  suggestion: string | null;
  text_start: number | null;
  text_end: number | null;
  is_dismissed: boolean;
  dismissed_by: string | null;
  dismissed_at: string | null;
  created_at: string;
}

export interface CategoryBreakdown {
  category: RiskCategory;
  score: number;
  flag_count: number;
  worst_severity: RiskSeverity | null;
  flags: RiskFlag[];
}

export interface ComplianceCheck {
  id: string;
  channel_id: string;
  script_id: string | null;
  publication_id: string | null;
  mode: CheckMode;
  status: CheckStatus;
  risk_score: number;
  category_scores: Record<string, number>;
  flag_count: number;
  critical_count: number;
  high_count: number;
  monetization_eligible: boolean;
  ai_disclosure_required: boolean;
  is_overridden: boolean;
  override_by: string | null;
  override_reason: string | null;
  overridden_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  flags: RiskFlag[];
  created_at: string;
  updated_at: string;
}

export interface ComplianceCheckDetail extends ComplianceCheck {
  categories: CategoryBreakdown[];
}

export interface ComplianceSummary {
  id: string;
  script_id: string | null;
  publication_id: string | null;
  status: CheckStatus;
  risk_score: number;
  flag_count: number;
  critical_count: number;
  monetization_eligible: boolean;
  ai_disclosure_required: boolean;
  is_overridden: boolean;
  created_at: string;
}
