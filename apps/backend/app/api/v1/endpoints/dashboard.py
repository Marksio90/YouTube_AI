from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import DashboardService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DASHBOARD_TIMEOUT_SECONDS = 10.0


@router.get(
    "",
    response_model=DashboardSummary,
    summary="Get aggregated dashboard data for the current user",
)
async def get_dashboard(
    current_user: CurrentUser,
    db: DB,
) -> DashboardSummary:
    service = DashboardService(db)

    start_time = time.perf_counter()

    try:
        summary = await service.get_summary(current_user.id)

    except TimeoutError:
        logger.error(
            "dashboard.timeout",
            user_id=str(current_user.id),
            timeout_seconds=DASHBOARD_TIMEOUT_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Dashboard request timed out",
        )

    except Exception:
        logger.exception(
            "dashboard.fetch_failed",
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load dashboard",
        )

    duration = time.perf_counter() - start_time

    logger.info(
        "dashboard.fetched",
        user_id=str(current_user.id),
        duration_ms=round(duration * 1000, 2),
    )

    return summary
