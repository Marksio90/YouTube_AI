"""
Compliance AI tasks — per-category LLM analysis.

Each task:
  1. Calls the LLM with a category-specific prompt
  2. Parses structured JSON flags
  3. Calls ComplianceService.add_ai_flags()
  4. Calls finalize_check() if all dispatched tasks are done

Task names (referenced in backend _dispatch_ai_checks):
  worker.tasks.compliance.ai_check_ad_safety
  worker.tasks.compliance.ai_check_copyright
  worker.tasks.compliance.ai_check_factual
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from sqlalchemy import select, text

from worker.celery_app import app
from worker.db import get_db_session

log = structlog.get_logger(__name__)

# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a YouTube policy compliance analyst. "
    "Analyze the content strictly and return ONLY valid JSON — no markdown, no prose."
)

_FLAG_SCHEMA = (
    '{"flags": [{'
    '"severity": "critical|high|medium|low|info", '
    '"rule_id": "category:subcategory:code", '
    '"title": "short title", '
    '"detail": "explanation", '
    '"evidence": "exact quote or null", '
    '"suggestion": "actionable fix or null"'
    '}]}'
)

_AD_SAFETY_PROMPT = """\
Check this YouTube script for AD SAFETY violations (YPP monetization policy).

Flag any: profanity/vulgarity, graphic violence, weapons/dangerous acts,
drug references, adult/sexual content, extremist ideology, gambling promotion,
shocking/disturbing imagery descriptions, hateful language.

Title: {title}
Script:
{body}

Return JSON matching this schema (empty flags array if clean):
{schema}
Rule IDs must start with "ad_safety:" — e.g. "ad_safety:profanity:a001"."""

_COPYRIGHT_PROMPT = """\
Check this YouTube script for COPYRIGHT and ATTRIBUTION risks.

Flag any: unattributed music/songs, use of copyrighted footage without license,
verbatim quotes from books/articles without attribution, brand trademarks used
in ways that could infer endorsement, phrases suggesting content is a repost
of someone else's work.

Title: {title}
Script:
{body}

Return JSON matching this schema (empty flags array if clean):
{schema}
Rule IDs must start with "copyright_risk:" — e.g. "copyright_risk:music:c001"."""

_FACTUAL_PROMPT = """\
Check this YouTube script for FACTUAL ACCURACY risks.

Flag any: specific medical/health advice without disclaimer, financial guarantees
("you WILL make money"), absolute superlative claims without evidence ("the ONLY",
"100% proven"), conspiracy theories or debunked claims, statistics cited without
source, misleading before/after comparisons.

Title: {title}
Script:
{body}

Return JSON matching this schema (empty flags array if clean):
{schema}
Rule IDs must start with "factual_risk:" — e.g. "factual_risk:medical:f001"."""


# ── Shared helpers ────────────────────────────────────────────────────────────

async def _call_llm(prompt: str) -> list[dict]:
    """Call LLM, parse JSON flags array. Returns [] on any parse failure."""
    from worker.config import settings
    from worker.llm import Message, ModelConfig, Role, get_provider

    provider = get_provider()
    config = ModelConfig(
        model=settings.llm_default_model,
        temperature=0.1,
        max_tokens=1500,
    )
    raw = await provider.complete(
        messages=[Message(role=Role.user, content=prompt)],
        system=_SYSTEM,
        config=config,
    )
    try:
        data = json.loads(raw)
        return data.get("flags", [])
    except (json.JSONDecodeError, AttributeError):
        log.warning("compliance_ai.parse_failed", raw=raw[:200])
        return []


def _raw_flags_from_json(category: str, flags_json: list[dict]) -> list[dict]:
    """Convert LLM JSON flags to RawFlag-compatible dicts."""
    from app.db.models.compliance import FlagSource, RiskCategory, RiskSeverity

    valid_severities = {s.value for s in RiskSeverity}
    result = []
    for f in flags_json:
        severity = f.get("severity", "info")
        if severity not in valid_severities:
            severity = "info"
        result.append({
            "category": category,
            "severity": severity,
            "source": "ai",
            "rule_id": f.get("rule_id", f"{category}:ai:a000"),
            "title": f.get("title", "AI-detected issue")[:300],
            "detail": f.get("detail", "")[:2000],
            "evidence": (f.get("evidence") or "")[:1000] or None,
            "suggestion": (f.get("suggestion") or "")[:500] or None,
            "text_start": None,
            "text_end": None,
        })
    return result


async def _persist_and_maybe_finalize(
    check_id: str,
    category: str,
    raw_flags_dicts: list[dict],
) -> None:
    """Add AI flags and finalize check if all AI tasks completed."""
    import sys
    import os
    # Ensure backend app is importable from worker context
    sys.path.insert(0, "/app/backend") if "/app/backend" not in sys.path else None

    from app.services.compliance import ComplianceService
    from app.services.compliance_rules import RawFlag
    import uuid

    check_uuid = uuid.UUID(check_id)
    raw_flags = [
        RawFlag(
            category=d["category"],
            severity=d["severity"],
            source=d["source"],
            rule_id=d["rule_id"],
            title=d["title"],
            detail=d["detail"],
            evidence=d["evidence"],
            suggestion=d["suggestion"],
            text_start=d["text_start"],
            text_end=d["text_end"],
        )
        for d in raw_flags_dicts
    ]

    async with get_db_session() as db:
        svc = ComplianceService(db)
        await svc.add_ai_flags(check_uuid, raw_flags)

        # Check if all dispatched AI tasks have completed
        check = await svc.get_check(check_uuid)
        if check and check.ai_task_ids:
            remaining = _count_pending_tasks(check.ai_task_ids, completed_category=category)
            if remaining == 0:
                await svc.finalize_check(check_uuid)

        await db.commit()


def _count_pending_tasks(ai_task_ids: dict, completed_category: str) -> int:
    """Count how many AI tasks are still pending (not counting current)."""
    from celery.result import AsyncResult

    pending = 0
    for cat, task_id in ai_task_ids.items():
        if cat == completed_category:
            continue
        result = AsyncResult(task_id)
        if result.state not in ("SUCCESS", "FAILURE", "REVOKED"):
            pending += 1
    return pending


# ── Tasks ─────────────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.compliance.ai_check_ad_safety",
    queue="high",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=150,
)
def ai_check_ad_safety(
    self,
    *,
    check_id: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    log_ = log.bind(task_id=self.request.id, check_id=check_id)
    log_.info("ai_check_ad_safety.start")
    try:
        prompt = _AD_SAFETY_PROMPT.format(title=title, body=body, schema=_FLAG_SCHEMA)
        flags_json = asyncio.run(_call_llm(prompt))
        raw_flags = _raw_flags_from_json("ad_safety", flags_json)
        asyncio.run(_persist_and_maybe_finalize(check_id, "ad_safety", raw_flags))
        log_.info("ai_check_ad_safety.done", flag_count=len(raw_flags))
        return {"check_id": check_id, "category": "ad_safety", "flags": len(raw_flags)}
    except Exception as exc:
        log_.error("ai_check_ad_safety.failed", error=str(exc))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@app.task(
    bind=True,
    name="worker.tasks.compliance.ai_check_copyright",
    queue="high",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=150,
)
def ai_check_copyright(
    self,
    *,
    check_id: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    log_ = log.bind(task_id=self.request.id, check_id=check_id)
    log_.info("ai_check_copyright.start")
    try:
        prompt = _COPYRIGHT_PROMPT.format(title=title, body=body, schema=_FLAG_SCHEMA)
        flags_json = asyncio.run(_call_llm(prompt))
        raw_flags = _raw_flags_from_json("copyright_risk", flags_json)
        asyncio.run(_persist_and_maybe_finalize(check_id, "copyright_risk", raw_flags))
        log_.info("ai_check_copyright.done", flag_count=len(raw_flags))
        return {"check_id": check_id, "category": "copyright_risk", "flags": len(raw_flags)}
    except Exception as exc:
        log_.error("ai_check_copyright.failed", error=str(exc))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@app.task(
    bind=True,
    name="worker.tasks.compliance.ai_check_factual",
    queue="high",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=150,
)
def ai_check_factual(
    self,
    *,
    check_id: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    log_ = log.bind(task_id=self.request.id, check_id=check_id)
    log_.info("ai_check_factual.start")
    try:
        prompt = _FACTUAL_PROMPT.format(title=title, body=body, schema=_FLAG_SCHEMA)
        flags_json = asyncio.run(_call_llm(prompt))
        raw_flags = _raw_flags_from_json("factual_risk", flags_json)
        asyncio.run(_persist_and_maybe_finalize(check_id, "factual_risk", raw_flags))
        log_.info("ai_check_factual.done", flag_count=len(raw_flags))
        return {"check_id": check_id, "category": "factual_risk", "flags": len(raw_flags)}
    except Exception as exc:
        log_.error("ai_check_factual.failed", error=str(exc))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
