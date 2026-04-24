import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.core.exceptions import NotFoundError
from app.db.models.compliance import CheckStatus
from app.schemas.compliance import (
    ComplianceCheckCreate,
    ComplianceCheckDetail,
    ComplianceCheckOverride,
    ComplianceCheckRead,
    ComplianceSummary,
    RiskFlagDismiss,
    RiskFlagRead,
)
from app.services.compliance import ComplianceService

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _svc(db: DB) -> ComplianceService:
    return ComplianceService(db)


# ── Run a check ───────────────────────────────────────────────────────────────

@router.post(
    "/channels/{channel_id}/checks",
    response_model=ComplianceCheckRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a compliance check for a script or publication",
)
async def run_check(
    channel_id: uuid.UUID,
    payload: ComplianceCheckCreate,
    current_user: CurrentUser,
    db: DB,
) -> ComplianceCheckRead:
    check = await _svc(db).run_check(payload, channel_id=channel_id)
    await db.commit()
    await db.refresh(check)
    return check


# ── Get detail ────────────────────────────────────────────────────────────────

@router.get(
    "/checks/{check_id}",
    response_model=ComplianceCheckDetail,
    summary="Full compliance check result with per-category breakdown",
)
async def get_check(
    check_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> ComplianceCheckDetail:
    detail = await _svc(db).get_check_detail(check_id)
    if not detail:
        raise NotFoundError(f"Compliance check {check_id} not found")
    return detail


# ── List checks ───────────────────────────────────────────────────────────────

@router.get(
    "/channels/{channel_id}/checks",
    response_model=list[ComplianceSummary],
    summary="List compliance checks for a channel",
)
async def list_checks(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    script_id: uuid.UUID | None = Query(None),
    check_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
) -> list[ComplianceSummary]:
    status_filter: CheckStatus | None = None
    if check_status:
        try:
            status_filter = CheckStatus(check_status)
        except ValueError:
            pass
    checks = await _svc(db).list_checks(
        channel_id,
        script_id=script_id,
        status=status_filter,
        limit=limit,
    )
    return checks


# ── Latest check for a script ─────────────────────────────────────────────────

@router.get(
    "/scripts/{script_id}/latest-check",
    response_model=ComplianceCheckRead | None,
    summary="Most recent compliance check for a script",
)
async def latest_for_script(
    script_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> ComplianceCheckRead | None:
    return await _svc(db).latest_for_script(script_id)


# ── Override a blocked check ──────────────────────────────────────────────────

@router.post(
    "/checks/{check_id}/override",
    response_model=ComplianceCheckRead,
    summary="Override a blocked compliance check (requires human justification)",
)
async def override_check(
    check_id: uuid.UUID,
    payload: ComplianceCheckOverride,
    current_user: CurrentUser,
    db: DB,
) -> ComplianceCheckRead:
    check = await _svc(db).override_check(check_id, payload)
    await db.commit()
    return check


# ── Dismiss a flag ────────────────────────────────────────────────────────────

@router.post(
    "/flags/{flag_id}/dismiss",
    response_model=RiskFlagRead,
    summary="Mark a risk flag as a false positive and recompute score",
)
async def dismiss_flag(
    flag_id: uuid.UUID,
    payload: RiskFlagDismiss,
    current_user: CurrentUser,
    db: DB,
) -> RiskFlagRead:
    flag = await _svc(db).dismiss_flag(flag_id, dismissed_by=payload.dismissed_by)
    await db.commit()
    return flag
