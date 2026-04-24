export const VIDEO_STATUSES = [
  "draft",
  "scripting",
  "producing",
  "rendering",
  "review",
  "scheduled",
  "published",
  "failed",
] as const;

export const PIPELINE_STEP_TYPES = [
  "research_topic",
  "generate_script",
  "review_compliance",
  "generate_thumbnail",
  "render_video",
  "upload_youtube",
  "schedule_post",
  "notify",
] as const;

export const SCRIPT_TONES = [
  "educational",
  "entertaining",
  "inspirational",
  "controversial",
  "news",
] as const;

export const ANALYTICS_PERIODS = ["7d", "28d", "90d", "365d", "lifetime"] as const;

export const MAX_SCRIPT_LENGTH_CHARS = 15_000;
export const MAX_TITLE_LENGTH = 100;
export const MAX_DESCRIPTION_LENGTH = 5_000;

export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;

export const CELERY_QUEUES = {
  DEFAULT: "default",
  AI: "ai",
  PIPELINE: "pipeline",
} as const;
