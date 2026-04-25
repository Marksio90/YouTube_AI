"""
WorkflowJob implementations — one class per step_type.

Each class knows:
  • which Celery task to dispatch
  • which queue to use
  • how to extract its required inputs from WorkflowContext
  • which keys it produces and merges back into context

Adding a new step:
  1. Subclass BaseWorkflowJob
  2. Set step_type, celery_task_name, celery_queue
  3. Implement build_payload() and extract_output()
  4. Add to JOB_REGISTRY

No business logic lives here — that belongs in the Celery task itself.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from worker.workflow.context import WorkflowContext
from worker.workflow.exceptions import ContextKeyMissingError


class BaseWorkflowJob(ABC):
    """
    Adapter between the engine and a concrete Celery task.
    Stateless — instantiated fresh for each dispatch.
    """

    step_type:        ClassVar[str]
    celery_task_name: ClassVar[str]
    celery_queue:     ClassVar[str]

    @abstractmethod
    def build_payload(
        self,
        ctx: WorkflowContext,
        step_config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build the kwargs dict to send to the Celery task.
        Raise ContextKeyMissingError if a required key is absent.
        """
        ...

    @abstractmethod
    def extract_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """
        Extract the keys this job contributes to the shared context.
        Called on successful task completion.
        """
        ...


# ── Concrete job classes ──────────────────────────────────────────────────────

class BriefJob(BaseWorkflowJob):
    """Generate a content brief from a topic."""

    step_type        = "brief"
    celery_task_name = "worker.tasks.ai.generate_brief"
    celery_queue     = "ai"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        return {
            "channel_id": ctx.require("channel_id", self.step_type),
            "topic_id":   ctx.require("topic_id",   self.step_type),
        }

    def extract_output(self, result: dict) -> dict:
        return {k: result[k] for k in ("brief_id",) if k in result}


class ScriptJob(BaseWorkflowJob):
    """Write the full narration script from a brief."""

    step_type        = "script"
    celery_task_name = "worker.tasks.ai.generate_script"
    celery_queue     = "ai"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        payload: dict = {
            "channel_id": ctx.require("channel_id", self.step_type),
            "brief_id":   ctx.require("brief_id",   self.step_type),
        }
        # Optional overrides from step config or context
        for key in ("tone", "target_duration_seconds", "keywords"):
            if key in step_config:
                payload[key] = step_config[key]
            elif key in ctx:
                payload[key] = ctx.get(key)
        return payload

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("script_id", "title", "seo_score"):
            if k in result:
                out[k] = result[k]
        return out


class ComplianceJob(BaseWorkflowJob):
    """Run the compliance / brand-safety gate on the script."""

    step_type        = "compliance"
    celery_task_name = "worker.tasks.ai.check_compliance"
    celery_queue     = "high"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        return {"script_id": ctx.require("script_id", self.step_type)}

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("compliance_status", "monetization_eligible", "advertiser_friendly_score"):
            if k in result:
                out[k] = result[k]
        return out


class AudioJob(BaseWorkflowJob):
    """Generate TTS audio for the script."""

    step_type        = "audio"
    celery_task_name = "worker.tasks.media.generate_audio"
    celery_queue     = "media"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        return {
            "script_id": ctx.require("script_id", self.step_type),
            "voice_id":  step_config.get("voice_id") or ctx.get("voice_id") or "alloy",
        }

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("audio_url", "audio_duration_seconds"):
            if k in result:
                out[k] = result[k]
        return out


class VisualsJob(BaseWorkflowJob):
    """Generate background visuals / B-roll imagery for the video."""

    step_type        = "visuals"
    celery_task_name = "worker.tasks.media.generate_thumbnail"   # reuses image gen
    celery_queue     = "media"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        payload: dict = {
            "script_id": ctx.require("script_id", self.step_type),
            "mode":      "visuals",   # signals the task to produce scene images
        }
        if ctx.publication_id:
            payload["publication_id"] = ctx.publication_id
        return payload

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("visual_urls", "thumbnail_url"):
            if k in result:
                out[k] = result[k]
        return out


class ThumbnailJob(BaseWorkflowJob):
    """Generate the final CTR-optimised thumbnail."""

    step_type        = "thumbnail"
    celery_task_name = "worker.tasks.media.generate_thumbnail"
    celery_queue     = "media"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        payload: dict = {"script_id": ctx.require("script_id", self.step_type)}
        if ctx.publication_id:
            payload["publication_id"] = ctx.publication_id
        return payload

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("thumbnail_url",):
            if k in result:
                out[k] = result[k]
        return out


class MetadataJob(BaseWorkflowJob):
    """Generate SEO-optimised YouTube metadata (title, description, tags)."""

    step_type        = "metadata"
    celery_task_name = "worker.tasks.ai.analyze_seo"
    celery_queue     = "ai"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        return {"script_id": ctx.require("script_id", self.step_type)}

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("seo_score", "metadata_id", "optimized_title", "optimized_description", "tags"):
            if k in result:
                out[k] = result[k]
        return out


class PublishJob(BaseWorkflowJob):
    """Upload the video to YouTube and create the Publication record."""

    step_type        = "publication"
    celery_task_name = "worker.tasks.youtube.publish_video_pipeline"
    celery_queue     = "default"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        pub_id = ctx.publication_id
        if not pub_id:
            raise ContextKeyMissingError("publication_id", self.step_type)
        payload: dict = {
            "publication_id": pub_id,
            "media_url": step_config.get("media_url") or ctx.get("media_url") or ctx.require("audio_url", self.step_type),
            "visibility": step_config.get("privacy_status", "private"),
        }
        for k in ("audio_url", "thumbnail_url", "optimized_title", "optimized_description", "tags"):
            if ctx.get(k):
                payload[k.replace("optimized_", "")] = ctx.get(k)
        return payload

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("youtube_video_id", "youtube_video_url", "publication_id"):
            if k in result:
                out[k] = result[k]
        return out


class AnalyticsJob(BaseWorkflowJob):
    """Trigger an analytics sync immediately after publication."""

    step_type        = "analytics"
    celery_task_name = "worker.tasks.analytics.sync_channel_metrics"
    celery_queue     = "analytics"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        return {
            "channel_id":     ctx.require("channel_id",     self.step_type),
            "publication_id": ctx.get("publication_id"),
        }

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("analytics_snapshot_id", "views", "impressions"):
            if k in result:
                out[k] = result[k]
        return out


class OptimizationJob(BaseWorkflowJob):
    """Generate AI optimisation recommendations for the published video."""

    step_type        = "optimization"
    celery_task_name = "worker.tasks.recommendations.generate_recommendations"
    celery_queue     = "ai"

    def build_payload(self, ctx: WorkflowContext, step_config: dict) -> dict:
        return {
            "channel_id":     ctx.require("channel_id",     self.step_type),
            "publication_id": ctx.get("publication_id"),
        }

    def extract_output(self, result: dict) -> dict:
        out = {}
        for k in ("recommendations", "optimization_id"):
            if k in result:
                out[k] = result[k]
        return out


# ── Registry ──────────────────────────────────────────────────────────────────

JOB_REGISTRY: dict[str, type[BaseWorkflowJob]] = {
    "brief":       BriefJob,
    "script":      ScriptJob,
    "compliance":  ComplianceJob,
    "audio":       AudioJob,
    "visuals":     VisualsJob,
    "thumbnail":   ThumbnailJob,
    "metadata":    MetadataJob,
    "publication": PublishJob,
    "analytics":   AnalyticsJob,
    "optimization": OptimizationJob,
}


def get_job(step_type: str) -> BaseWorkflowJob:
    """Return a fresh job instance for the given step_type."""
    cls = JOB_REGISTRY.get(step_type)
    if cls is None:
        raise KeyError(
            f"No job registered for step_type='{step_type}'. "
            f"Available: {sorted(JOB_REGISTRY)}"
        )
    return cls()
