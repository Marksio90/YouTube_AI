"""
AI task module — all LLM-heavy jobs.

Task names must match backend dispatchers in apps/backend/app/tasks/ai.py.
All tasks use IdempotencyGuard + TaskRegistry for safe re-execution and tracking.
"""

import asyncio
import hashlib
import uuid
from typing import Any

import structlog
from celery import Task

from worker.celery_app import app
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker import registry
from worker.agents.compliance_checker import ComplianceCheckerAgent
from worker.agents.script_writer import ScriptWriterAgent
from worker.agents.seo_analyzer import SEOAnalyzerAgent

log = structlog.get_logger(__name__)


# ── Shared base task with lazy agent singletons ───────────────────────────────

class AITask(Task):
    abstract = True
    _script_writer: ScriptWriterAgent | None = None
    _seo_analyzer: SEOAnalyzerAgent | None = None
    _compliance_checker: ComplianceCheckerAgent | None = None

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


def _short_hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


# ── generate_script ───────────────────────────────────────────────────────────

@app.task(
    bind=True,
    base=AITask,
    name="worker.tasks.ai.generate_script",
    queue="ai",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=480,
    time_limit=600,
)
def generate_script(
    self,
    *,
    channel_id: str,
    topic: str,
    tone: str = "educational",
    target_duration_seconds: int = 600,
    keywords: list[str] | None = None,
    additional_context: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id
    kws = keywords or []
    log_ = log.bind(task_id=task_id, channel_id=channel_id, topic=topic[:60])
    log_.info("generate_script.start")

    idp_key = f"gen_script:{channel_id}:{_short_hash(topic, tone, str(target_duration_seconds))}"

    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("generate_script.cache_hit", idp_key=idp_key)
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(
                _run_generate_script(
                    self,
                    task_id=task_id,
                    channel_id=channel_id,
                    topic=topic,
                    tone=tone,
                    target_duration_seconds=target_duration_seconds,
                    keywords=kws,
                    additional_context=additional_context,
                    idp_key=idp_key,
                )
            )
    except Exception as exc:
        log_.error("generate_script.failed", error=str(exc), retries=self.request.retries)
        asyncio.run(_mark_task_failure(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _run_generate_script(
    task,
    *,
    task_id: str,
    channel_id: str,
    topic: str,
    tone: str,
    target_duration_seconds: int,
    keywords: list[str],
    additional_context: str | None,
    idp_key: str,
) -> dict:
    async with get_db_session() as db:
        channel_info = await _load_channel(db, channel_id)
        await registry.record_start(
            db,
            task_id=task_id,
            task_name="generate_script",
            entity_type="channel",
            entity_id=channel_id,
            input_data={"topic": topic, "tone": tone},
        )

    # Step 1 — Generate script
    self_update(task, "generating_script", 10)
    script_data = await task.script_writer.generate(
        topic=topic,
        tone=tone,
        target_duration_seconds=target_duration_seconds,
        keywords=keywords,
        channel_niche=channel_info.get("niche", "general"),
        additional_context=additional_context,
    )

    async with get_db_session() as db:
        await registry.record_progress(db, task_id=task_id, progress=40, step="seo_analysis")

    # Step 2 — SEO analysis
    self_update(task, "seo_analysis", 40)
    seo_data = await task.seo_analyzer.analyze(
        title=script_data["title"],
        script_body=script_data["body"],
        keywords=keywords,
        niche=channel_info.get("niche", "general"),
    )

    async with get_db_session() as db:
        await registry.record_progress(db, task_id=task_id, progress=70, step="compliance_check")

    # Step 3 — Compliance
    self_update(task, "compliance_check", 70)
    compliance_data = await task.compliance_checker.check(
        title=script_data["title"],
        script=f"{script_data.get('hook', '')} {script_data.get('body', '')}",
        channel_niche=channel_info.get("niche", "general"),
    )

    # Step 4 — Persist
    self_update(task, "saving", 90)
    script_id = await _persist_script(
        channel_id=channel_id,
        script_data=script_data,
        seo_data=seo_data,
        compliance_data=compliance_data,
    )

    result = {
        "script_id": script_id,
        "title": script_data.get("title"),
        "seo_score": seo_data.get("overall_score"),
        "compliance_status": compliance_data.get("overall_status"),
        "monetization_eligible": compliance_data.get("monetization_eligible", True),
    }

    async with get_db_session() as db:
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=3600)
    log.info("generate_script.complete", script_id=script_id, task_id=task_id)
    return result


# ── generate_brief ────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    base=AITask,
    name="worker.tasks.ai.generate_brief",
    queue="ai",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=400,
)
def generate_brief(self, *, channel_id: str, topic_id: str) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id, topic_id=topic_id)
    log_.info("generate_brief.start")

    idp_key = f"gen_brief:{topic_id}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("generate_brief.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_generate_brief(self, task_id, channel_id, topic_id, idp_key))
    except Exception as exc:
        log_.error("generate_brief.failed", error=str(exc))
        asyncio.run(_mark_task_failure(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _run_generate_brief(task, task_id, channel_id, topic_id, idp_key) -> dict:
    from sqlalchemy import text

    async with get_db_session() as db:
        topic_row = (
            await db.execute(
                text("SELECT title, description, keywords, niche FROM topics t "
                     "JOIN channels c ON c.id=t.channel_id "
                     "WHERE t.id=:id"),
                {"id": topic_id},
            )
        ).mappings().one_or_none()

        if not topic_row:
            raise ValueError(f"Topic {topic_id} not found")

        channel_info = await _load_channel(db, channel_id)
        await registry.record_start(
            db, task_id=task_id, task_name="generate_brief",
            entity_type="topic", entity_id=topic_id,
        )

    self_update(task, "generating_brief", 20)

    brief_data = await task.script_writer.generate(
        topic=topic_row["title"],
        tone="educational",
        target_duration_seconds=600,
        keywords=list(topic_row["keywords"] or []),
        channel_niche=channel_info.get("niche", "general"),
        additional_context=topic_row.get("description"),
    )

    brief_id = str(uuid.uuid4())
    async with get_db_session() as db:
        await db.execute(
            text("""
                INSERT INTO briefs
                    (id, channel_id, topic_id, title, target_audience, key_points,
                     seo_keywords, estimated_duration_seconds, tone, status)
                VALUES
                    (:id, :channel_id, :topic_id, :title, '', :key_points,
                     :seo_keywords, 600, 'educational', 'draft')
                ON CONFLICT DO NOTHING
            """),
            {
                "id": brief_id,
                "channel_id": channel_id,
                "topic_id": topic_id,
                "title": brief_data.get("title", topic_row["title"]),
                "key_points": _as_json(brief_data.get("keywords", [])),
                "seo_keywords": list(brief_data.get("keywords", [])),
            },
        )
        await db.execute(
            text("UPDATE topics SET status='briefed', updated_at=NOW() WHERE id=:id"),
            {"id": topic_id},
        )
        await registry.record_success(db, task_id=task_id, result={"brief_id": brief_id})

    result = {"brief_id": brief_id, "topic_id": topic_id}
    idp.set_result(idp_key, result, ttl=3600)
    return result


# ── analyze_seo ───────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    base=AITask,
    name="worker.tasks.ai.analyze_seo",
    queue="ai",
    max_retries=2,
    default_retry_delay=20,
    soft_time_limit=180,
    time_limit=240,
)
def analyze_seo(self, *, script_id: str) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, script_id=script_id)
    log_.info("analyze_seo.start")

    idp_key = f"seo:{script_id}"
    if (cached := idp.get_result(idp_key)) is not None:
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_analyze_seo(self, task_id, script_id, idp_key))
    except Exception as exc:
        log_.error("analyze_seo.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _run_analyze_seo(task, task_id, script_id, idp_key) -> dict:
    from sqlalchemy import text

    async with get_db_session() as db:
        row = (
            await db.execute(
                text("SELECT title, body, keywords FROM scripts WHERE id=:id"),
                {"id": script_id},
            )
        ).mappings().one_or_none()
        if not row:
            raise ValueError(f"Script {script_id} not found")

        await registry.record_start(db, task_id=task_id, task_name="analyze_seo",
                                    entity_type="script", entity_id=script_id)

    seo = await task.seo_analyzer.analyze(
        title=row["title"],
        script_body=row["body"],
        keywords=list(row["keywords"] or []),
    )

    async with get_db_session() as db:
        await db.execute(
            text("UPDATE scripts SET seo_score=:score, updated_at=NOW() WHERE id=:id"),
            {"id": script_id, "score": seo.get("overall_score")},
        )
        await registry.record_success(db, task_id=task_id, result=seo)

    idp.set_result(idp_key, seo, ttl=3600)
    return seo


# ── check_compliance ──────────────────────────────────────────────────────────

@app.task(
    bind=True,
    base=AITask,
    name="worker.tasks.ai.check_compliance",
    queue="high",
    max_retries=2,
    default_retry_delay=15,
    soft_time_limit=180,
    time_limit=240,
)
def check_compliance(self, *, script_id: str) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, script_id=script_id)
    log_.info("check_compliance.start")

    idp_key = f"compliance:{script_id}"
    if (cached := idp.get_result(idp_key)) is not None:
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_check_compliance(self, task_id, script_id, idp_key))
    except Exception as exc:
        log_.error("check_compliance.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _run_check_compliance(task, task_id, script_id, idp_key) -> dict:
    from sqlalchemy import text

    async with get_db_session() as db:
        row = (
            await db.execute(
                text("""
                    SELECT s.title, s.hook, s.body, s.channel_id, c.niche
                    FROM scripts s JOIN channels c ON c.id=s.channel_id
                    WHERE s.id=:id
                """),
                {"id": script_id},
            )
        ).mappings().one_or_none()
        if not row:
            raise ValueError(f"Script {script_id} not found")

        await registry.record_start(db, task_id=task_id, task_name="check_compliance",
                                    entity_type="script", entity_id=script_id)

    result = await task.compliance_checker.check(
        title=row["title"],
        script=f"{row['hook']} {row['body']}",
        channel_niche=row.get("niche", "general"),
    )

    new_status = "review" if result.get("overall_status") == "PASS" else "draft"
    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE scripts
                SET compliance_score=:score, status=:status, updated_at=NOW()
                WHERE id=:id
            """),
            {
                "id": script_id,
                "score": result.get("compliance_score"),
                "status": new_status,
            },
        )
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=3600)
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def self_update(task, step: str, progress: int) -> None:
    task.update_state(state="PROGRESS", meta={"step": step, "progress": progress})


async def _load_channel(db, channel_id: str) -> dict:
    from sqlalchemy import text
    row = (
        await db.execute(
            text("SELECT name, niche FROM channels WHERE id=:id"), {"id": channel_id}
        )
    ).mappings().one_or_none()
    return dict(row) if row else {}


async def _persist_script(
    channel_id: str,
    script_data: dict,
    seo_data: dict,
    compliance_data: dict,
) -> str:
    from sqlalchemy import text
    script_id = str(uuid.uuid4())
    async with get_db_session() as db:
        await db.execute(
            text("""
                INSERT INTO scripts
                    (id, channel_id, title, hook, body, cta, keywords,
                     target_duration_seconds, tone, seo_score, compliance_score, status, version)
                VALUES
                    (:id, :channel_id, :title, :hook, :body, :cta, :keywords,
                     :dur, :tone, :seo, :compliance, 'draft', 1)
            """),
            {
                "id": script_id,
                "channel_id": channel_id,
                "title": script_data.get("title", ""),
                "hook": script_data.get("hook", ""),
                "body": script_data.get("body", ""),
                "cta": script_data.get("cta", ""),
                "keywords": list(script_data.get("keywords", [])),
                "dur": script_data.get("estimated_duration_seconds", 600),
                "tone": "educational",
                "seo": seo_data.get("overall_score"),
                "compliance": compliance_data.get("compliance_score"),
            },
        )
    return script_id


async def _mark_task_failure(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass  # registry failure must never mask the original error


def _as_json(v) -> str:
    import json
    return json.dumps(v)
