"""
Content pipeline workflow: Topic → Brief → Script → Publication.

Each step can be used individually or as part of the full pipeline.
The workflow is orchestrated from the API layer; heavy AI work is
dispatched as Celery tasks so the workflow itself is lightweight.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.brief import BriefStatus
from app.db.models.script import ScriptStatus
from app.db.models.topic import TopicStatus
from app.tasks.ai import enqueue_generate_brief, enqueue_generate_script
from app.workflows.base import BaseWorkflow, WorkflowContext, WorkflowStep

logger = structlog.get_logger(__name__)


class MarkTopicResearching(WorkflowStep):
    name = "mark_topic_researching"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run(self, ctx: WorkflowContext) -> WorkflowContext:
        from app.repositories.topic import TopicRepository
        topic_id = ctx.get("topic_id")
        if not topic_id:
            ctx.fail("topic_id missing from context")
            return ctx

        repo = TopicRepository(self.db)
        topic = await repo.get(uuid.UUID(topic_id))
        if not topic:
            ctx.fail(f"Topic {topic_id} not found")
            return ctx

        topic.status = TopicStatus.researching
        await repo.save(topic)
        ctx.set("topic_title", topic.title)
        ctx.set("topic_keywords", topic.keywords)
        logger.info("workflow.mark_topic_researching", topic_id=topic_id)
        return ctx


class DispatchBriefGeneration(WorkflowStep):
    name = "dispatch_brief_generation"

    async def run(self, ctx: WorkflowContext) -> WorkflowContext:
        task_id = enqueue_generate_brief(
            channel_id=ctx.channel_id,
            topic_id=ctx.get("topic_id"),
        )
        ctx.set("brief_task_id", task_id)
        logger.info("workflow.brief_dispatched", task_id=task_id)
        return ctx


class DispatchScriptGeneration(WorkflowStep):
    name = "dispatch_script_generation"

    async def run(self, ctx: WorkflowContext) -> WorkflowContext:
        task_id = enqueue_generate_script(
            channel_id=ctx.channel_id,
            topic=ctx.get("topic_title", ""),
            tone=ctx.input.get("tone", "educational"),
            target_duration_seconds=ctx.input.get("target_duration_seconds", 600),
            keywords=ctx.get("topic_keywords", []),
        )
        ctx.set("script_task_id", task_id)
        logger.info("workflow.script_dispatched", task_id=task_id)
        return ctx


class TopicToBriefWorkflow(BaseWorkflow):
    """Marks topic as researching, then dispatches async brief generation."""

    def __init__(self, db: AsyncSession) -> None:
        self._steps = [
            MarkTopicResearching(db),
            DispatchBriefGeneration(),
        ]

    @property
    def steps(self) -> list[WorkflowStep]:
        return self._steps


class TopicToScriptWorkflow(BaseWorkflow):
    """Full pipeline: topic → brief → script dispatched as async tasks."""

    def __init__(self, db: AsyncSession) -> None:
        self._steps = [
            MarkTopicResearching(db),
            DispatchBriefGeneration(),
            DispatchScriptGeneration(),
        ]

    @property
    def steps(self) -> list[WorkflowStep]:
        return self._steps
