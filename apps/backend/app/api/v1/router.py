from fastapi import APIRouter

from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.compliance import router as compliance_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.briefs import router as briefs_router
from app.api.v1.endpoints.channels import router as channels_router
from app.api.v1.endpoints.dashboard import router as dashboard_router
from app.api.v1.endpoints.monetization import router as monetization_router
from app.api.v1.endpoints.pipelines import router as pipelines_router
from app.api.v1.endpoints.publications import router as publications_router
from app.api.v1.endpoints.scripts import router as scripts_router
from app.api.v1.endpoints.topics import router as topics_router
from app.api.v1.endpoints.workflows import router as workflows_router
from app.api.v1.endpoints.optimization import router as optimization_router
from app.api.v1.endpoints.thumbnails import router as thumbnails_router
from app.api.v1.endpoints.youtube import router as youtube_router
from app.api.v1.endpoints.affiliate import router as affiliate_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(channels_router)
api_router.include_router(topics_router)
api_router.include_router(briefs_router)
api_router.include_router(scripts_router)
api_router.include_router(publications_router)
api_router.include_router(analytics_router)
api_router.include_router(monetization_router)
api_router.include_router(compliance_router)
api_router.include_router(dashboard_router)
api_router.include_router(pipelines_router)
api_router.include_router(workflows_router)
api_router.include_router(thumbnails_router)
api_router.include_router(optimization_router)
api_router.include_router(youtube_router)
api_router.include_router(affiliate_router)
