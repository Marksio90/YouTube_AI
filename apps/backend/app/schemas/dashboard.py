from pydantic import BaseModel

from app.schemas.publication import PublicationRead


class EntityCounts(BaseModel):
    total: int
    by_status: dict[str, int]


class AnalyticsSummary(BaseModel):
    period_days: int
    total_views: int
    total_revenue_usd: float
    subscribers_gained: int
    avg_rpm: float
    avg_ctr: float


class DashboardSummary(BaseModel):
    channels: dict[str, int]  # {"total": N, "active": N}
    topics: EntityCounts
    briefs: EntityCounts
    scripts: EntityCounts
    publications: EntityCounts
    analytics: AnalyticsSummary
    top_publications: list[PublicationRead]
