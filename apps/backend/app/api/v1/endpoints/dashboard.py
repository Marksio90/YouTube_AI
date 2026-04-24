from fastapi import APIRouter

from app.api.v1.deps import CurrentUser, DB
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardSummary)
async def get_dashboard(current_user: CurrentUser, db: DB) -> DashboardSummary:
    svc = DashboardService(db)
    return await svc.get_summary(current_user.id)
