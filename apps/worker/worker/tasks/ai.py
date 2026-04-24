import asyncio
import json
import uuid

import structlog
from celery import Task

from worker.celery_app import app
from worker.db import get_db_session
from worker.agents.script_writer import ScriptWriterAgent
from worker.agents.seo_analyzer import SEOAnalyzerAgent
from worker.agents.compliance_checker import ComplianceCheckerAgent

logger = structlog.get_logger(__name__)


class AITask(Task):
    abstract = True
    _script_writer = None
    _seo_analyzer = None
    _compliance_checker = None

    @property
    def script_writer(self) -> ScriptWriterAgent:
        if self._script_writer is None:
            self._script_writer = ScriptWriterAgent()
        return self._script_writer

    @property
    def seo_analyzer(self) -> SEOAnalyzerAgent:
        if self._seo_analyzer is None:
            self._seo_analyzer = SEOAnalyzerAgent()
        return self._seo_analyzer

    @property
    def compliance_checker(self) -> ComplianceCheckerAgent:
        if self._compliance_checker is None:
            self._compliance_checker = ComplianceCheckerAgent()
        return self._compliance_checker


@app.task(
    bind=True,
    base=AITask,
    name="worker.tasks.ai.generate_script",
    queue="ai",
    max_retries=2,
    default_retry_delay=30,
)
def generate_script_task(
    self,
    *,
    channel_id: str,
    topic: str,
    tone: str = "educational",
    target_duration_seconds: int = 600,
    keywords: list[str] | None = None,
    additional_context: str | None = None,
) -> dict:
    log = logger.bind(channel_id=channel_id, topic=topic[:60], task_id=self.request.id)
    log.info("generate_script.start")

    try:
        self.update_state(state="PROGRESS", meta={"step": "generating_script", "progress": 10})

        script_result = asyncio.run(
            self.script_writer.generate(
                topic=topic,
                tone=tone,
                target_duration_seconds=target_duration_seconds,
                keywords=keywords or [],
                additional_context=additional_context,
            )
        )

        self.update_state(state="PROGRESS", meta={"step": "seo_analysis", "progress": 50})

        seo_result = asyncio.run(
            self.seo_analyzer.analyze(
                title=script_result["title"],
                script_body=script_result["body"],
                keywords=keywords or [],
            )
        )

        self.update_state(state="PROGRESS", meta={"step": "compliance_check", "progress": 75})

        compliance_result = asyncio.run(
            self.compliance_checker.check(
                title=script_result["title"],
                script=script_result["hook"] + " " + script_result["body"],
            )
        )

        self.update_state(state="PROGRESS", meta={"step": "saving", "progress": 90})

        asyncio.run(_persist_script(
            channel_id=channel_id,
            script_data=script_result,
            seo_data=seo_result,
            compliance_data=compliance_result,
        ))

        log.info("generate_script.complete", title=script_result.get("title", "")[:60])
        return {
            "script": script_result,
            "seo": seo_result,
            "compliance": compliance_result,
        }

    except Exception as exc:
        log.error("generate_script.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _persist_script(
    channel_id: str,
    script_data: dict,
    seo_data: dict,
    compliance_data: dict,
) -> None:
    async with get_db_session() as db:
        from sqlalchemy import text
        await db.execute(
            text("""
                INSERT INTO scripts (id, channel_id, title, hook, body, cta, keywords,
                    target_duration_seconds, tone, seo_score, compliance_score, status, version)
                VALUES (:id, :channel_id, :title, :hook, :body, :cta, :keywords,
                    :target_duration_seconds, :tone, :seo_score, :compliance_score, 'draft', 1)
            """),
            {
                "id": str(uuid.uuid4()),
                "channel_id": channel_id,
                "title": script_data.get("title", ""),
                "hook": script_data.get("hook", ""),
                "body": script_data.get("body", ""),
                "cta": script_data.get("cta", ""),
                "keywords": script_data.get("keywords", []),
                "target_duration_seconds": script_data.get("estimated_duration_seconds", 600),
                "tone": "educational",
                "seo_score": seo_data.get("overall_score"),
                "compliance_score": compliance_data.get("compliance_score"),
            },
        )
