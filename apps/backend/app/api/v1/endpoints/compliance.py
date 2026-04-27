from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.core.exceptions import NotFoundError
from app.db.models.compliance import CheckStatus
from app.repositories.channel import ChannelRepository
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

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/compliance", tags=["compliance"])

DEFAULT_CHECK_LIMIT = 50
MAX_CHECK_LIMIT = 200


def _svc(db: DB) -> ComplianceService:
    return ComplianceService(db)


async def _ensure_owned_channel(
    *,
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    channel = await ChannelRepository(db).get_owned(
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not channel:
        raise NotFoundError(f"Channel {channel_id} not found")


def _validate_check_target(payload: ComplianceCheckCreate) -> None:
    if payload.script_id is None and payload.publication_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either script_id or publication_id",
        )

    if payload.script_id is not None and payload.publication_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide only one target: script_id or publication_id",
        )


def _parse_check_status(raw_status: str | None) -> CheckStatus | None:
    if raw_status is None:
        return None

    try:
        return CheckStatus(raw_status)
    except ValueError as exc:
        allowed = ", ".join(status_item.value for status_item in CheckStatus)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Allowed values: {allowed}",
        ) from exc


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
    _validate_check_target(payload)
    await _ensure_owned_channel(channel_id=channel_id, current_user=current_user, db=db)

    service = _svc(db)

    try:
        check = await service.run_check(
            payload,
            channel_id=channel_id,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        await db.commit()
        await db.refresh(check)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception:
        await db.rollback()
        logger.exception(
            "compliance.run_check_failed",
            channel_id=str(channel_id),
            owner_id=str(current_user.id),
            script_id=str(payload.script_id) if payload.script_id else None,
            publication_id=str(payload.publication_id) if payload.publication_id else None,
            mode=payload.mode,
        )
        raise

    logger.info(
        "compliance.run_check_accepted",
        check_id=str(check.id),
        channel_id=str(channel_id),
        owner_id=str(current_user.id),
        status=check.status.value,
        risk_score=check.risk_score,
    )

    return ComplianceCheckRead.model_validate(check)


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
    detail = await _svc(db).get_check_detail(
        check_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not detail:
        raise NotFoundError(f"Compliance check {check_id} not found")

    return detail


@router.get(
    "/channels/{channel_id}/checks",
    response_model=list[ComplianceSummary],
    summary="List compliance checks for a channel",
)
async def list_checks(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    script_id: uuid.UUID | None = Query(default=None),
    check_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(DEFAULT_CHECK_LIMIT, ge=1, le=MAX_CHECK_LIMIT),
) -> list[ComplianceSummary]:
    await _ensure_owned_channel(channel_id=channel_id, current_user=current_user, db=db)

    status_filter = _parse_check_status(check_status)

    checks = await _svc(db).list_checks(
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
        script_id=script_id,
        status=status_filter,
        limit=limit,
    )

    return [ComplianceSummary.model_validate(check) for check in checks]


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
    check = await _svc(db).latest_for_script(
        script_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    if check is None:
        return None

    return ComplianceCheckRead.model_validate(check)


@router.post(
    "/checks/{check_id}/override",
    response_model=ComplianceCheckRead,
    summary="Override a blocked compliance check",
)
async def override_check(
    check_id: uuid.UUID,
    payload: ComplianceCheckOverride,
    current_user: CurrentUser,
    db: DB,
) -> ComplianceCheckRead:
    service = _svc(db)

    try:
        check = await service.override_check(
            check_id,
            payload,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        await db.commit()
        await db.refresh(check)
    except ValueError as exc:
        await db.rollback()
        message = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in message.lower()
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=status_code, detail=message) from exc
    except Exception:
        await db.rollback()
        logger.exception(
            "compliance.override_failed",
            check_id=str(check_id),
            owner_id=str(current_user.id),
            override_by=payload.override_by,
        )
        raise

    logger.warning(
        "compliance.override_applied",
        check_id=str(check_id),
        owner_id=str(current_user.id),
        override_by=payload.override_by,
    )

    return ComplianceCheckRead.model_validate(check)


@router.post(
    "/flags/{flag_id}/dismiss",
    response_model=RiskFlagRead,
    summary="Mark a risk flag as false positive and recompute score",
)
async def dismiss_flag(
    flag_id: uuid.UUID,
    payload: RiskFlagDismiss,
    current_user: CurrentUser,
    db: DB,
) -> RiskFlagRead:
    service = _svc(db)

    try:
        flag = await service.dismiss_flag(
            flag_id,
            dismissed_by=payload.dismissed_by,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        await db.commit()
        await db.refresh(flag)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception:
        await db.rollback()
        logger.exception(
            "compliance.flag_dismiss_failed",
            flag_id=str(flag_id),
            owner_id=str(current_user.id),
            dismissed_by=payload.dismissed_by,
        )
        raise

    logger.info(
        "compliance.flag_dismissed",
        flag_id=str(flag_id),
        owner_id=str(current_user.id),
        dismissed_by=payload.dismissed_by,
        has_reason=bool(payload.reason),
    )

    return RiskFlagRead.model_validate(flag)
