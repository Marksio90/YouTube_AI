"""
ComplianceService — orchestrates rule checks, scoring, and DB persistence.

Scoring model
─────────────
  Category weights (must sum to 1.0):
    ad_safety        0.35
    copyright_risk   0.30
    factual_risk     0.20
    reused_content   0.10
    ai_disclosure    0.05

  Severity → raw score:
    critical 100 / high 70 / medium 40 / low 15 / info 0

  Category score = max(flag raw scores in category, 0 if no flags)
  Overall risk_score = Σ(weight × category_score), clamped 0–100

  Status decision:
    risk_score < 21   → passed
    21 ≤ score < 80   → flagged
    score ≥ 80        → blocked

AI checks
─────────
  Dispatched as Celery tasks (worker.tasks.compliance.*) after rule checks.
  Each task updates the ComplianceCheck with additional RiskFlags and
  recomputes the score.  The check stays in 'running' until all AI tasks
  have reported back (checked via ai_task_ids tracking).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.compliance import (
    CheckMode,
    CheckStatus,
    ComplianceCheck,
    FlagSource,
    RiskCategory,
    RiskFlag,
    RiskSeverity,
)
from app.db.models.channel import Channel
from app.db.models.script import Script
from app.schemas.compliance import (
    CategoryBreakdown,
    ComplianceCheckCreate,
    ComplianceCheckDetail,
    ComplianceCheckOverride,
)
from app.services.compliance_rules import RawFlag, run_rule_checks

log = structlog.get_logger(__name__)

# ── Scoring constants ─────────────────────────────────────────────────────────

_WEIGHTS: dict[RiskCategory, float] = {
    RiskCategory.ad_safety:      0.35,
    RiskCategory.copyright_risk: 0.30,
    RiskCategory.factual_risk:   0.20,
    RiskCategory.reused_content: 0.10,
    RiskCategory.ai_disclosure:  0.05,
}

_SEVERITY_SCORE: dict[RiskSeverity, float] = {
    RiskSeverity.critical: 100.0,
    RiskSeverity.high:     70.0,
    RiskSeverity.medium:   40.0,
    RiskSeverity.low:      15.0,
    RiskSeverity.info:     0.0,
}

_PASS_THRESHOLD    = 21.0
_BLOCK_THRESHOLD   = 80.0
_AD_SAFE_THRESHOLD = 50.0   # ad_safety category score above this → not monetizable


# ── Service ───────────────────────────────────────────────────────────────────

class ComplianceService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Main entry point ──────────────────────────────────────────────────────

    async def run_check(
        self,
        payload: ComplianceCheckCreate,
        *,
        channel_id: uuid.UUID,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        dispatch_ai: bool = True,
    ) -> ComplianceCheck:
        """
        Create ComplianceCheck, run rule checks synchronously, optionally
        dispatch AI tasks.  Returns the check (possibly still 'running' if
        AI dispatched).
        """
        script = None
        title = ""
        body  = ""
        ai_generated = False
        existing_titles: list[str] = []

        if payload.script_id:
            script = await self._load_script(
                payload.script_id,
                owner_id=owner_id,
                organization_id=organization_id,
            )
            if not script:
                raise ValueError(f"Script {payload.script_id} not found")
            if script.channel_id != channel_id:
                raise ValueError(f"Script {payload.script_id} does not belong to channel {channel_id}")
            title = script.title
            body  = f"{script.hook}\n{script.body}\n{script.cta}"
            ai_generated = script.seo_score is not None  # proxy: AI ran on this script

            existing_titles = await self._existing_titles(channel_id, exclude=payload.script_id)

        # Create check record
        check = ComplianceCheck(
            channel_id=channel_id,
            script_id=payload.script_id,
            publication_id=payload.publication_id,
            mode=CheckMode(payload.mode),
            status=CheckStatus.running,
            started_at=datetime.now(timezone.utc),
        )
        self._db.add(check)
        await self._db.flush()  # get check.id

        log.info("compliance_check.start", check_id=str(check.id), mode=payload.mode)

        # ── Rule-based checks (synchronous) ───────────────────────────────────
        raw_flags = run_rule_checks(
            title=title,
            body=body,
            script_was_ai_generated=ai_generated,
            existing_titles=existing_titles,
        )

        await self._persist_flags(check.id, raw_flags)
        await self._db.flush()

        # Score from rule flags only (will be updated when AI returns)
        if payload.mode == "rule" or not dispatch_ai:
            await self._finalize_check(check)
        else:
            # Partial score — AI may add more
            await self._update_score(check)
            check.status = CheckStatus.running

        # ── Dispatch AI tasks ─────────────────────────────────────────────────
        if dispatch_ai and payload.mode in ("ai", "both") and payload.script_id:
            task_ids = _dispatch_ai_checks(
                check_id=str(check.id),
                script_id=str(payload.script_id),
                title=title,
                body=body[:4000],  # truncate for LLM
            )
            check.ai_task_ids = task_ids

        return check

    # ── Finalize (called by AI tasks when all complete) ───────────────────────

    async def finalize_check(self, check_id: uuid.UUID) -> ComplianceCheck:
        check = await self._get_check(check_id)
        if not check:
            raise ValueError(f"Check {check_id} not found")
        await self._finalize_check(check)
        return check

    async def add_ai_flags(
        self,
        check_id: uuid.UUID,
        raw_flags: list[RawFlag],
    ) -> None:
        await self._persist_flags(check_id, raw_flags)
        check = await self._get_check(check_id)
        if check:
            await self._update_score(check)

    # ── Override ──────────────────────────────────────────────────────────────

    async def override_check(
        self,
        check_id: uuid.UUID,
        payload: ComplianceCheckOverride,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> ComplianceCheck:
        check = await self._get_check(
            check_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if not check:
            raise ValueError(f"Check {check_id} not found")
        if check.status != CheckStatus.blocked:
            raise ValueError("Only blocked checks can be overridden")

        check.is_overridden   = True
        check.override_by     = payload.override_by
        check.override_reason = payload.override_reason
        check.overridden_at   = datetime.now(timezone.utc)
        check.status          = CheckStatus.flagged  # downgrade from blocked
        log.warning(
            "compliance_check.overridden",
            check_id=str(check_id),
            by=payload.override_by,
        )
        return check

    # ── Dismiss flag ──────────────────────────────────────────────────────────

    async def dismiss_flag(
        self,
        flag_id: uuid.UUID,
        *,
        dismissed_by: str,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> RiskFlag:
        q = (
            select(RiskFlag)
            .join(ComplianceCheck, ComplianceCheck.id == RiskFlag.check_id)
            .join(Channel, Channel.id == ComplianceCheck.channel_id)
            .where(
                RiskFlag.id == flag_id,
                Channel.owner_id == owner_id,
            )
        )
        if organization_id is not None:
            q = q.where(Channel.organization_id == organization_id)
        flag = (await self._db.execute(q)).scalar_one_or_none()
        if not flag:
            raise ValueError(f"Flag {flag_id} not found")
        flag.is_dismissed = True
        flag.dismissed_by = dismissed_by
        flag.dismissed_at = datetime.now(timezone.utc)

        # Recompute check score excluding dismissed flags
        check = await self._get_check(
            flag.check_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if check:
            await self._update_score(check)
            await self._set_status(check)

        return flag

    # ── Queries ───────────────────────────────────────────────────────────────

    async def get_check(self, check_id: uuid.UUID) -> ComplianceCheck | None:
        return await self._get_check(check_id)

    async def get_check_detail(
        self,
        check_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> ComplianceCheckDetail | None:
        check = await self._get_check(
            check_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if not check:
            return None
        return _build_detail(check)

    async def list_checks(
        self,
        channel_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        script_id: uuid.UUID | None = None,
        status: CheckStatus | None = None,
        limit: int = 50,
    ) -> list[ComplianceCheck]:
        q = (
            select(ComplianceCheck)
            .join(Channel, Channel.id == ComplianceCheck.channel_id)
            .where(ComplianceCheck.channel_id == channel_id)
            .where(Channel.owner_id == owner_id)
            .order_by(ComplianceCheck.created_at.desc())
            .limit(limit)
        )
        if organization_id is not None:
            q = q.where(Channel.organization_id == organization_id)
        if script_id:
            q = q.where(ComplianceCheck.script_id == script_id)
        if status:
            q = q.where(ComplianceCheck.status == status)
        return list((await self._db.execute(q)).scalars().all())

    async def latest_for_script(
        self,
        script_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> ComplianceCheck | None:
        q = (
            select(ComplianceCheck)
            .join(Channel, Channel.id == ComplianceCheck.channel_id)
            .where(
                ComplianceCheck.script_id == script_id,
                Channel.owner_id == owner_id,
            )
            .order_by(ComplianceCheck.created_at.desc())
            .limit(1)
        )
        if organization_id is not None:
            q = q.where(Channel.organization_id == organization_id)
        return (await self._db.execute(q)).scalar_one_or_none()

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_check(
        self,
        check_id: uuid.UUID,
        *,
        owner_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> ComplianceCheck | None:
        q = select(ComplianceCheck).where(ComplianceCheck.id == check_id)
        if owner_id is not None or organization_id is not None:
            q = q.join(Channel, Channel.id == ComplianceCheck.channel_id)
        if owner_id is not None:
            q = q.where(Channel.owner_id == owner_id)
        if organization_id is not None:
            q = q.where(Channel.organization_id == organization_id)
        return (await self._db.execute(q)).scalar_one_or_none()

    async def _load_script(
        self,
        script_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> Script | None:
        q = (
            select(Script)
            .join(Channel, Channel.id == Script.channel_id)
            .where(
                Script.id == script_id,
                Channel.owner_id == owner_id,
            )
        )
        if organization_id is not None:
            q = q.where(Channel.organization_id == organization_id)
        return (await self._db.execute(q)).scalar_one_or_none()

    async def _existing_titles(
        self,
        channel_id: uuid.UUID,
        *,
        exclude: uuid.UUID | None = None,
    ) -> list[str]:
        q = text(
            "SELECT title FROM scripts WHERE channel_id=:ch"
            + (" AND id != :ex" if exclude else "")
        )
        params: dict = {"ch": str(channel_id)}
        if exclude:
            params["ex"] = str(exclude)
        rows = (await self._db.execute(q, params)).fetchall()
        return [r[0] for r in rows]

    async def _persist_flags(
        self, check_id: uuid.UUID, raw_flags: list[RawFlag]
    ) -> None:
        for rf in raw_flags:
            flag = RiskFlag(
                check_id=check_id,
                category=rf.category,
                severity=rf.severity,
                source=rf.source,
                rule_id=rf.rule_id,
                title=rf.title,
                detail=rf.detail,
                evidence=rf.evidence,
                suggestion=rf.suggestion,
                text_start=rf.text_start,
                text_end=rf.text_end,
            )
            self._db.add(flag)

    async def _update_score(self, check: ComplianceCheck) -> None:
        """Recompute risk_score from current (non-dismissed) flags."""
        flags_result = await self._db.execute(
            select(RiskFlag).where(
                RiskFlag.check_id == check.id,
                RiskFlag.is_dismissed.is_(False),
            )
        )
        flags = list(flags_result.scalars().all())

        category_max: dict[RiskCategory, float] = {c: 0.0 for c in RiskCategory}
        for f in flags:
            score = _SEVERITY_SCORE[f.severity]
            if score > category_max[f.category]:
                category_max[f.category] = score

        risk_score = sum(
            _WEIGHTS[cat] * cat_score
            for cat, cat_score in category_max.items()
        )
        risk_score = round(min(max(risk_score, 0.0), 100.0), 2)

        check.risk_score      = risk_score
        check.category_scores = {c.value: round(s, 2) for c, s in category_max.items()}
        check.flag_count      = len(flags)
        check.critical_count  = sum(1 for f in flags if f.severity == RiskSeverity.critical)
        check.high_count      = sum(1 for f in flags if f.severity == RiskSeverity.high)
        check.monetization_eligible  = category_max[RiskCategory.ad_safety] < _AD_SAFE_THRESHOLD
        check.ai_disclosure_required = any(
            f.rule_id.startswith("ai_disclosure:script:") for f in flags
        )

    async def _set_status(self, check: ComplianceCheck) -> None:
        if check.risk_score < _PASS_THRESHOLD:
            check.status = CheckStatus.passed
        elif check.risk_score < _BLOCK_THRESHOLD:
            check.status = CheckStatus.flagged
        else:
            check.status = CheckStatus.blocked

    async def _finalize_check(self, check: ComplianceCheck) -> None:
        await self._update_score(check)
        await self._set_status(check)
        check.completed_at = datetime.now(timezone.utc)
        log.info(
            "compliance_check.finalized",
            check_id=str(check.id),
            status=check.status.value,
            score=check.risk_score,
        )
        # Sync compliance_score back to script
        if check.script_id:
            await self._db.execute(
                text(
                    "UPDATE scripts SET compliance_score=:score, updated_at=NOW() WHERE id=:id"
                ),
                {"score": round(100 - check.risk_score, 2), "id": str(check.script_id)},
            )


# ── AI task dispatcher ────────────────────────────────────────────────────────

def _dispatch_ai_checks(
    *,
    check_id: str,
    script_id: str,
    title: str,
    body: str,
) -> dict[str, str]:
    """
    Dispatch per-category AI compliance tasks.
    Returns {category: celery_task_id}.
    """
    from worker.tasks.compliance import (
        ai_check_ad_safety,
        ai_check_copyright,
        ai_check_factual,
    )

    task_ids: dict[str, str] = {}

    t1 = ai_check_ad_safety.apply_async(
        kwargs={"check_id": check_id, "title": title, "body": body},
        queue="high",
    )
    task_ids["ad_safety"] = t1.id

    t2 = ai_check_copyright.apply_async(
        kwargs={"check_id": check_id, "title": title, "body": body},
        queue="high",
    )
    task_ids["copyright_risk"] = t2.id

    t3 = ai_check_factual.apply_async(
        kwargs={"check_id": check_id, "title": title, "body": body},
        queue="high",
    )
    task_ids["factual_risk"] = t3.id

    return task_ids


# ── Detail builder ────────────────────────────────────────────────────────────

def _build_detail(check: ComplianceCheck) -> ComplianceCheckDetail:
    from app.schemas.compliance import ComplianceCheckDetail, RiskFlagRead

    flags_by_category: dict[RiskCategory, list[RiskFlag]] = {c: [] for c in RiskCategory}
    for f in check.flags:
        flags_by_category[f.category].append(f)

    categories: list[CategoryBreakdown] = []
    for cat in RiskCategory:
        cat_flags = flags_by_category[cat]
        worst = max(
            (f.severity for f in cat_flags if not f.is_dismissed),
            key=lambda s: _SEVERITY_SCORE[s],
            default=None,
        )
        categories.append(CategoryBreakdown(
            category=cat.value,          # type: ignore[arg-type]
            score=check.category_scores.get(cat.value, 0.0),
            flag_count=len(cat_flags),
            worst_severity=worst.value if worst else None,  # type: ignore[arg-type]
            flags=[RiskFlagRead.model_validate(f) for f in cat_flags],
        ))

    return ComplianceCheckDetail(
        **{
            k: v for k, v in check.__dict__.items()
            if not k.startswith("_")
        },
        flags=[RiskFlagRead.model_validate(f) for f in check.flags],
        categories=categories,
    )
