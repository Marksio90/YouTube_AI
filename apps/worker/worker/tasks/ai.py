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
from worker.agents.compliance import ComplianceAgent, ComplianceInput
from worker.agents.metadata import MetadataAgent, MetadataInput
from worker.agents.scriptwriter import ScriptwriterAgent, ScriptwriterInput, ScriptwriterOutput

log = structlog.get_logger(__name__)


# ── Shared base task with lazy agent singletons ───────────────────────────────

class AITask(Task):
    abstract = True
    _scriptwriter: ScriptwriterAgent | None = None
    _metadata: MetadataAgent | None = None
    _compliance: ComplianceAgent | None = None

    @property
    def scriptwriter(self) -> ScriptwriterAgent:
        if self._scriptwriter is None:
            self._scriptwriter = ScriptwriterAgent()
        return self._scriptwriter

    @property
    def metadata(self) -> MetadataAgent:
        if self._metadata is None:
            self._metadata = MetadataAgent()
        return self._metadata

    @property
    def compliance(self) -> ComplianceAgent:
        if self._compliance is None:
            self._compliance = ComplianceAgent()
        return self._compliance


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
    script_out = await task.scriptwriter.run(
        ScriptwriterInput(
            topic=topic,
            niche=channel_info.get("niche", "general"),
            tone=tone,
            target_duration_seconds=target_duration_seconds,
            keywords=keywords,
            style_notes=additional_context or "",
        )
    )
    async with get_db_session() as db:
        await registry.record_progress(db, task_id=task_id, progress=40, step="seo_analysis")

    # Step 2 — SEO analysis
    self_update(task, "seo_analysis", 40)
    metadata_out = await task.metadata.run(
        MetadataInput(
            title=script_out.title,
            script=script_out.body,
            niche=channel_info.get("niche", "general"),
            target_keywords=keywords,
            language="en",
        )
    )
    seo_data = _metadata_output_to_seo(metadata_out)

    async with get_db_session() as db:
        await registry.record_progress(db, task_id=task_id, progress=70, step="compliance_check")

    # Step 3 — Compliance
    self_update(task, "compliance_check", 70)
    compliance_out = await task.compliance.run(
        ComplianceInput(
            title=script_out.title,
            script=f"{script_out.hook} {script_out.body}".strip(),
            niche=channel_info.get("niche", "general"),
        )
    )
    compliance_data = _compliance_output_to_legacy(compliance_out)

    # Step 4 — Persist
    self_update(task, "saving", 90)
    script_id = await _persist_script(
        channel_id=channel_id,
        script_output=script_out,
        seo_data=seo_data,
        compliance_data=compliance_data,
    )

    result = {
        "script_id": script_id,
        "title": script_out.title,
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

    brief_out = await task.scriptwriter.run(
        ScriptwriterInput(
            topic=topic_row["title"],
            niche=channel_info.get("niche", "general"),
            tone="educational",
            target_duration_seconds=600,
            keywords=list(topic_row["keywords"] or []),
            style_notes=topic_row.get("description") or "",
        )
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
                "title": brief_out.title or topic_row["title"],
                "key_points": _as_json(brief_out.keywords),
                "seo_keywords": brief_out.keywords,
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

    metadata_out = await task.metadata.run(
        MetadataInput(
            title=row["title"],
            script=row["body"],
            niche="general",
            target_keywords=list(row["keywords"] or []),
        )
    )
    seo = _metadata_output_to_seo(metadata_out)

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

    compliance_out = await task.compliance.run(
        ComplianceInput(
            title=row["title"],
            script=f"{row['hook']} {row['body']}".strip(),
            niche=row.get("niche", "general"),
        )
    )
    result = _compliance_output_to_legacy(compliance_out)

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
    script_output: ScriptwriterOutput,
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
                "title": script_output.title,
                "hook": script_output.hook,
                "body": script_output.body,
                "cta": script_output.cta,
                "keywords": script_output.keywords,
                "dur": script_output.estimated_duration_seconds,
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


def _metadata_output_to_seo(output) -> dict[str, Any]:
    keyword_values = list(output.keyword_density.values())
    keyword_coverage = round((sum(keyword_values) / len(keyword_values)) * 300, 2) if keyword_values else 0.0
    title_score = 9.0 if len(output.optimized_title) <= 100 else 6.0
    overall = round(min(10.0, max(0.0, (title_score * 0.4) + (keyword_coverage * 0.6))), 2)
    return {
        "overall_score": overall,
        "title_score": round(title_score, 2),
        "keyword_coverage": keyword_coverage,
        "suggested_title": output.optimized_title,
        "suggested_tags": output.tags,
        "improvement_notes": output.card_suggestions,
        "description": output.description,
        "hashtags": output.hashtags,
        "chapters": [c.model_dump() for c in output.chapters],
    }


def _compliance_output_to_legacy(output) -> dict[str, Any]:
    if output.risk_level in {"safe", "low"}:
        status = "PASS"
    elif output.risk_level in {"medium", "high"}:
        status = "WARNING"
    else:
        status = "BLOCK"
    return {
        "overall_status": status,
        "compliance_score": output.advertiser_friendly_score,
        "monetization_eligible": output.monetization_eligible,
        "issues": [v.model_dump() for v in output.violations],
        "summary": output.review_notes,
        "risk_level": output.risk_level,
        "warnings": output.warnings,
        "suggestions": output.suggestions,
    }
